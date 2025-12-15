# lib/noaa_alert_mapper.py
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

module_logger = logging.getLogger("icad_nws.noaa_alert_map_module")

# ----------------------------
# Defaults
# ----------------------------

DEFAULT_TILE_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors"

DEFAULT_MAX_ZOOM = 14
DEFAULT_MIN_ZOOM = 3

# Cache TTLs (seconds)
DEFAULT_ZONE_JSON_TTL_S = 24 * 3600          # 1 day
DEFAULT_ZONE_POLY_TTL_S = 24 * 3600          # 1 day
DEFAULT_TILE_TTL_S = 7 * 24 * 3600           # 7 days

WEB_MERCATOR_MAX_LAT = 85.05112878
TILE_SIZE = 256


# ----------------------------
# Public dataclasses
# ----------------------------

RGBA = Tuple[int, int, int, int]


@dataclass(frozen=True)
class AlertColors:
    """
    Colors for drawing the alert overlay.
    - fill_rgba: used for the interior fill
    - outline_rgba: used for the outer ring
    """
    fill_rgba: RGBA = (255, 0, 0, 25)
    outline_rgba: RGBA = (255, 0, 0, 220)
    outline_width: int = 3


@dataclass
class NOAAAlertMapConfig:
    # Basemap
    tile_template: str = DEFAULT_TILE_TEMPLATE
    attribution: str = DEFAULT_ATTRIBUTION

    # Output defaults (can be overridden per-render)
    width: int = 900
    height: int = 650

    # Zoom logic
    min_zoom: int = DEFAULT_MIN_ZOOM
    max_zoom: int = DEFAULT_MAX_ZOOM
    margin_frac: float = 0.12

    # Tile request behavior
    max_tiles: int = 64
    tile_delay_s: float = 0.0
    request_timeout_s: int = 30

    # Caching
    cache_dir: Path = field(default_factory=lambda: Path("../.cache_noaa_maps"))
    zone_json_ttl_s: int = DEFAULT_ZONE_JSON_TTL_S
    zone_poly_ttl_s: int = DEFAULT_ZONE_POLY_TTL_S
    tile_ttl_s: int = DEFAULT_TILE_TTL_S

    # Rendering modes
    zones_mode_default: str = "affected"   # "per-zone" or "affected"
    show_title_block: bool = True

    # Font options
    font_candidates: List[str] = field(default_factory=lambda: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ])

    # User Agent for NWS
    user_agent: str = "icad_nws_alerts (nws@icarey.net)"


# ----------------------------
# Geometry dataclasses
# ----------------------------

@dataclass
class PolyRings:
    outer: List[Tuple[float, float]]
    holes: List[List[Tuple[float, float]]]


@dataclass
class ZonePolys:
    url: str
    zone_id: str
    name: str
    polys: List[PolyRings]


# ----------------------------
# Small helpers
# ----------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def safe_slug(s: str, max_len: int = 80) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:max_len] or "alert"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def utc_now_ts() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def is_cache_fresh(path: Path, ttl_s: int) -> bool:
    if ttl_s <= 0:
        return False
    if not path.exists():
        return False
    age = utc_now_ts() - int(path.stat().st_mtime)
    return age >= 0 and age <= ttl_s


def _io_bytes(b: bytes):
    import io
    return io.BytesIO(b)


def rgba_from_hex(hex_color: str, alpha: int = 255) -> RGBA:
    """
    "#RRGGBB" -> (r,g,b,a)
    """
    s = (hex_color or "").strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (r, g, b, int(alpha))

# ----------------------------
# Web Mercator math
# ----------------------------

def lonlat_to_world_px(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat = clamp(lat, -WEB_MERCATOR_MAX_LAT, WEB_MERCATOR_MAX_LAT)
    x = (lon + 180.0) / 360.0
    sin_lat = math.sin(math.radians(lat))
    y = 0.5 - (math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi))
    scale = TILE_SIZE * (2 ** zoom)
    return (x * scale, y * scale)


def choose_zoom_for_bbox(
        lon_min: float, lat_min: float, lon_max: float, lat_max: float,
        out_w: int, out_h: int,
        *,
        min_zoom: int,
        max_zoom: int,
        margin_frac: float,
) -> int:
    if abs(lon_max - lon_min) < 1e-6 and abs(lat_max - lat_min) < 1e-6:
        lon_min -= 0.02
        lon_max += 0.02
        lat_min -= 0.02
        lat_max += 0.02

    usable_w = max(1, int(out_w * (1.0 - 2.0 * margin_frac)))
    usable_h = max(1, int(out_h * (1.0 - 2.0 * margin_frac)))

    best = min_zoom
    for z in range(min_zoom, max_zoom + 1):
        x1, y1 = lonlat_to_world_px(lon_min, lat_max, z)
        x2, y2 = lonlat_to_world_px(lon_max, lat_min, z)
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        if dx <= usable_w and dy <= usable_h:
            best = z
        else:
            break
    return best


# ----------------------------
# GeoJSON polygon extraction
# ----------------------------

def _pos_to_lonlat(pos: Any) -> Optional[Tuple[float, float]]:
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        try:
            return (float(pos[0]), float(pos[1]))
        except Exception:
            return None
    return None


def normalize_geometry_to_multipolygon(geom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not geom or not isinstance(geom, dict):
        return None

    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if gtype == "Polygon":
        if not isinstance(coords, list):
            return None
        return {"type": "MultiPolygon", "coordinates": [coords]}

    if gtype == "MultiPolygon":
        if not isinstance(coords, list):
            return None
        return {"type": "MultiPolygon", "coordinates": coords}

    if gtype == "GeometryCollection":
        geoms = geom.get("geometries") or []
        out_coords: List[Any] = []
        for g in geoms:
            mp = normalize_geometry_to_multipolygon(g)
            if mp:
                out_coords.extend(mp.get("coordinates") or [])
        return {"type": "MultiPolygon", "coordinates": out_coords} if out_coords else None

    return None


def extract_polyrings_from_geometry(geom: Dict[str, Any]) -> List[PolyRings]:
    mp = normalize_geometry_to_multipolygon(geom)
    if not mp:
        return []

    coords = mp.get("coordinates")
    if not isinstance(coords, list):
        return []

    polys: List[PolyRings] = []

    for poly_rings in coords:
        if not isinstance(poly_rings, list) or not poly_rings:
            continue

        outer_ring = poly_rings[0] if len(poly_rings) >= 1 else []
        hole_rings = poly_rings[1:] if len(poly_rings) >= 2 else []

        outer: List[Tuple[float, float]] = []
        if isinstance(outer_ring, list):
            for pos in outer_ring:
                ll = _pos_to_lonlat(pos)
                if ll is not None:
                    outer.append(ll)

        holes: List[List[Tuple[float, float]]] = []
        for hr in hole_rings:
            if not isinstance(hr, list):
                continue
            ring_pts: List[Tuple[float, float]] = []
            for pos in hr:
                ll = _pos_to_lonlat(pos)
                if ll is not None:
                    ring_pts.append(ll)
            if len(ring_pts) >= 3:
                holes.append(ring_pts)

        if len(outer) >= 3:
            polys.append(PolyRings(outer=outer, holes=holes))

    return polys


def bbox_from_polys(polys: List[PolyRings]) -> Optional[Tuple[float, float, float, float]]:
    if not polys:
        return None
    lon_min =  999.0
    lat_min =  999.0
    lon_max = -999.0
    lat_max = -999.0

    def absorb_ring(r: List[Tuple[float, float]]) -> None:
        nonlocal lon_min, lat_min, lon_max, lat_max
        for lon, lat in r:
            lon_min = min(lon_min, lon)
            lat_min = min(lat_min, lat)
            lon_max = max(lon_max, lon)
            lat_max = max(lat_max, lat)

    for p in polys:
        absorb_ring(p.outer)
        for h in p.holes:
            absorb_ring(h)

    return (lon_min, lat_min, lon_max, lat_max)


# ----------------------------
# Map viewport + tiles
# ----------------------------

def compute_viewport_world_px(
        lon_min: float, lat_min: float, lon_max: float, lat_max: float,
        zoom: int,
        out_w: int, out_h: int,
        margin_frac: float,
) -> Tuple[float, float, float, float]:
    center_lon = (lon_min + lon_max) / 2.0
    center_lat = (lat_min + lat_max) / 2.0
    cx, cy = lonlat_to_world_px(center_lon, center_lat, zoom)

    half_w = out_w / 2.0
    half_h = out_h / 2.0
    left = cx - half_w
    top = cy - half_h
    right = cx + half_w
    bottom = cy + half_h

    x1, y1 = lonlat_to_world_px(lon_min, lat_max, zoom)
    x2, y2 = lonlat_to_world_px(lon_max, lat_min, zoom)
    bbox_left, bbox_top = min(x1, x2), min(y1, y2)
    bbox_right, bbox_bottom = max(x1, x2), max(y1, y2)

    pad_x = out_w * margin_frac
    pad_y = out_h * margin_frac

    if bbox_left < left + pad_x:
        dx = (left + pad_x) - bbox_left
        left -= dx
        right -= dx
    if bbox_right > right - pad_x:
        dx = bbox_right - (right - pad_x)
        left += dx
        right += dx
    if bbox_top < top + pad_y:
        dy = (top + pad_y) - bbox_top
        top -= dy
        bottom -= dy
    if bbox_bottom > bottom - pad_y:
        dy = bbox_bottom - (bottom - pad_y)
        top += dy
        bottom += dy

    return (left, top, right, bottom)


def tile_range_for_viewport(left: float, top: float, right: float, bottom: float, zoom: int) -> Tuple[int, int, int, int]:
    x0 = int(math.floor(left / TILE_SIZE))
    x1 = int(math.floor((right - 1) / TILE_SIZE))
    y0 = int(math.floor(top / TILE_SIZE))
    y1 = int(math.floor((bottom - 1) / TILE_SIZE))

    max_xy = (2 ** zoom) - 1
    y0 = max(0, min(max_xy, y0))
    y1 = max(0, min(max_xy, y1))
    return (x0, y0, x1, y1)


# ----------------------------
# Renderer class
# ----------------------------

StyleResolver = Callable[[Dict[str, Any]], AlertColors]


class NOAAAlertMapRenderer:
    """
    Reusable renderer for a *single* NOAA/NWS alert Feature.

    - Keeps a requests.Session and in-memory zone polygon cache for speed.
    - Uses disk cache for tiles + zones under config.cache_dir
    - Supports per-zone coloring OR unified "affected area" overlays.
    - For "affected" mode you can pass colors (fill/outline) per alert type.
    """

    def __init__(
            self,
            *,
            config: Optional[NOAAAlertMapConfig] = None,
            session: Optional[requests.Session] = None,
            logger: Optional[logging.Logger] = None,
            style_resolver: Optional[StyleResolver] = None,
    ) -> None:
        self.config = config or NOAAAlertMapConfig()
        self.log = logger or module_logger

        ua = (self.config.user_agent or "").strip()
        if not ua:
            raise ValueError("user_agent is required (e.g. 'icad_nws_alerts (nws@icarey.net)')")

        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
        })

        # per-instance in-memory cache of zone polys by URL
        self._zone_mem_cache: Dict[str, ZonePolys] = {}

        # optional style resolver (event -> colors). If not provided, caller passes colors per render.
        self.style_resolver = style_resolver

        ensure_dir(self.config.cache_dir)

    # ----------------------------
    # Public API
    # ----------------------------

    def render_to_image(
            self,
            feature: Dict[str, Any],
            *,
            width: Optional[int] = None,
            height: Optional[int] = None,
            tile_template: Optional[str] = None,
            attribution: Optional[str] = None,
            zones_mode: Optional[str] = None,  # "per-zone" or "affected"
            affected_colors: Optional[AlertColors] = None,
            label: Optional[str] = None,
            show_title_block: Optional[bool] = None,
            title: Optional[str] = None,
            subtitle: Optional[str] = None,
    ) -> Image.Image:
        """
        Render a single alert Feature to a PIL Image.

        - If zones_mode=="affected": uses affected_colors (fill/outline).
          If not provided, will use style_resolver(feature) if configured,
          otherwise falls back to default AlertColors().
        """
        cfg = self.config
        out_w = int(width or cfg.width)
        out_h = int(height or cfg.height)
        tile_template = tile_template or cfg.tile_template
        attribution = attribution or cfg.attribution
        zones_mode = (zones_mode or cfg.zones_mode_default).strip().lower()
        show_title = cfg.show_title_block if show_title_block is None else bool(show_title_block)

        polys, used_zones = self._polygons_and_zones_for_alert(feature)

        bb = bbox_from_polys(polys)
        if not bb:
            props = feature.get("properties") or {}
            fid = feature.get("id") or props.get("id") or "alert"
            raise RuntimeError(f"No geometry found for alert: {fid}")

        lon_min, lat_min, lon_max, lat_max = bb
        zoom = choose_zoom_for_bbox(
            lon_min, lat_min, lon_max, lat_max,
            out_w, out_h,
            min_zoom=cfg.min_zoom,
            max_zoom=cfg.max_zoom,
            margin_frac=cfg.margin_frac,
        )

        # step down if too many tiles
        while True:
            left, top, right, bottom = compute_viewport_world_px(
                lon_min, lat_min, lon_max, lat_max,
                zoom, out_w, out_h,
                cfg.margin_frac,
            )
            x0, y0, x1, y1 = tile_range_for_viewport(left, top, right, bottom, zoom)
            tile_count = (x1 - x0 + 1) * (y1 - y0 + 1)
            if tile_count <= cfg.max_tiles or zoom <= cfg.min_zoom:
                break
            zoom -= 1

        left, top, right, bottom = compute_viewport_world_px(
            lon_min, lat_min, lon_max, lat_max,
            zoom, out_w, out_h,
            cfg.margin_frac,
        )

        base = self._stitch_and_crop_basemap(
            tile_template=tile_template,
            zoom=zoom,
            left=left, top=top, right=right, bottom=bottom,
            out_w=out_w, out_h=out_h,
        )

        # Overlay
        if used_zones:
            if zones_mode == "per-zone":
                composed = self._draw_zones_on_image(base, used_zones, zoom, left, top)
            elif zones_mode == "affected":
                union_polys: List[PolyRings] = []
                for z in used_zones:
                    union_polys.extend(z.polys)

                if affected_colors is None and self.style_resolver is not None:
                    affected_colors = self.style_resolver(feature)
                if affected_colors is None:
                    affected_colors = AlertColors()

                composed = self._draw_affected_area_on_image(
                    base,
                    union_polys,
                    zoom=zoom,
                    viewport_left=left,
                    viewport_top=top,
                    fill_rgba=affected_colors.fill_rgba,
                    outline_rgba=affected_colors.outline_rgba,
                    outline_width=affected_colors.outline_width,
                    label=label,
                )
            else:
                raise ValueError("zones_mode must be 'per-zone' or 'affected'")
        else:
            # alert geometry directly
            if affected_colors is None and self.style_resolver is not None:
                affected_colors = self.style_resolver(feature)
            if affected_colors is None:
                affected_colors = AlertColors()

            composed = self._draw_affected_area_on_image(
                base,
                polys,
                zoom=zoom,
                viewport_left=left,
                viewport_top=top,
                fill_rgba=affected_colors.fill_rgba,
                outline_rgba=affected_colors.outline_rgba,
                outline_width=affected_colors.outline_width,
                label=label,
            )

        if not show_title:
            return composed

        props = feature.get("properties") or {}
        event = title or (props.get("event") or "NOAA Alert")
        if subtitle is None:
            subtitle = props.get("headline") or (f"{props.get('sent') or ''}  •  zoom={zoom}".strip())

        return self._add_title_block(composed, title=event, subtitle=subtitle, attribution=attribution)

    def render_to_file(
            self,
            feature: Dict[str, Any],
            out_path: Union[str, Path],
            **kwargs: Any,
    ) -> Path:
        """
        Legacy helper: render + save PNG to disk.
        """
        out_path = Path(out_path)
        _ = self.render(feature, save=True, out_path=out_path, **kwargs)
        return out_path

    def default_output_name(self, feature: Dict[str, Any], ext: str = ".png") -> str:
        props = feature.get("properties") or {}
        event = props.get("event") or "alert"
        fid = feature.get("id") or props.get("id") or "alert"
        short = hashlib.sha1(str(fid).encode("utf-8")).hexdigest()[:10]
        return f"{safe_slug(event)}_{short}{ext}"

    # ----------------------------
    # Caching fetchers
    # ----------------------------

    def _cache_path_for_url(self, prefix: str, url: str, suffix: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.config.cache_dir / prefix / f"{h}{suffix}"

    def _fetch_json_cached(self, url: str, ttl_s: int) -> Dict[str, Any]:
        ensure_dir(self.config.cache_dir / "zones")
        cpath = self._cache_path_for_url("zones", url, ".json")

        if is_cache_fresh(cpath, ttl_s):
            try:
                return json.loads(cpath.read_text("utf-8"))
            except Exception:
                pass

        self.log.debug("GET %s", url)
        r = self.session.get(url, timeout=self.config.request_timeout_s)
        r.raise_for_status()
        data = r.json()

        if ttl_s > 0:
            try:
                cpath.write_text(json.dumps(data), encoding="utf-8")
            except Exception as e:
                self.log.debug("Could not write cache %s: %s", cpath, e)

        return data

    def _zone_poly_cache_path(self, zurl: str) -> Path:
        ensure_dir(self.config.cache_dir / "zone_polys")
        h = hashlib.sha256(zurl.encode("utf-8")).hexdigest()[:32]
        return self.config.cache_dir / "zone_polys" / f"{h}.json"

    def _polyrings_to_jsonable(self, polys: List[PolyRings]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in polys:
            out.append({
                "outer": [[lon, lat] for lon, lat in p.outer],
                "holes": [[[lon, lat] for lon, lat in ring] for ring in p.holes],
            })
        return out

    def _polyrings_from_jsonable(self, data: Any) -> List[PolyRings]:
        polys: List[PolyRings] = []
        if not isinstance(data, list):
            return polys
        for item in data:
            if not isinstance(item, dict):
                continue
            outer = item.get("outer") or []
            holes = item.get("holes") or []
            try:
                o = [(float(x), float(y)) for x, y in outer]
                h = [[(float(x), float(y)) for x, y in ring] for ring in holes]
                if len(o) >= 3:
                    polys.append(PolyRings(outer=o, holes=h))
            except Exception:
                continue
        return polys

    def _fetch_zone_polys_cached(self, zurl: str) -> ZonePolys:
        # memory cache
        if zurl in self._zone_mem_cache:
            return self._zone_mem_cache[zurl]

        # disk poly cache
        ppath = self._zone_poly_cache_path(zurl)
        if is_cache_fresh(ppath, self.config.zone_poly_ttl_s):
            try:
                raw = json.loads(ppath.read_text("utf-8"))
                zp = ZonePolys(
                    url=zurl,
                    zone_id=str(raw.get("zone_id") or "ZONE"),
                    name=str(raw.get("name") or ""),
                    polys=self._polyrings_from_jsonable(raw.get("polys")),
                )
                self._zone_mem_cache[zurl] = zp
                return zp
            except Exception:
                pass

        # fetch zone JSON
        zdata = self._fetch_json_cached(zurl, ttl_s=self.config.zone_json_ttl_s)
        zgeom = zdata.get("geometry")
        zprops = zdata.get("properties") or {}

        if not zgeom and zdata.get("type") == "FeatureCollection":
            feats = zdata.get("features") or []
            if feats:
                zgeom = (feats[0] or {}).get("geometry")
                zprops = (feats[0] or {}).get("properties") or {}

        polys = extract_polyrings_from_geometry(zgeom) if zgeom else []
        zone_id = str(zprops.get("id") or zprops.get("zone") or zprops.get("name") or "ZONE")
        name = str(zprops.get("name") or "")

        zp = ZonePolys(url=zurl, zone_id=zone_id, name=name, polys=polys)

        # write poly cache
        if self.config.zone_poly_ttl_s > 0:
            try:
                ppath.write_text(json.dumps({
                    "url": zurl,
                    "zone_id": zone_id,
                    "name": name,
                    "polys": self._polyrings_to_jsonable(polys),
                }), encoding="utf-8")
            except Exception as e:
                self.log.debug("Could not write zone_polys cache %s: %s", ppath, e)

        self._zone_mem_cache[zurl] = zp
        return zp

    def _fetch_tile_cached(self, tile_template: str, z: int, x: int, y: int) -> Image.Image:
        ensure_dir(self.config.cache_dir / "tiles" / str(z) / str(x))
        tpath = self.config.cache_dir / "tiles" / str(z) / str(x) / f"{y}.png"

        if is_cache_fresh(tpath, self.config.tile_ttl_s):
            return Image.open(tpath).convert("RGBA")

        url = tile_template.format(z=z, x=x, y=y)
        self.log.debug("TILE %s", url)

        if self.config.tile_delay_s > 0:
            time.sleep(self.config.tile_delay_s)

        r = self.session.get(url, timeout=self.config.request_timeout_s)
        r.raise_for_status()
        img = Image.open(_io_bytes(r.content)).convert("RGBA")

        if self.config.tile_ttl_s > 0:
            try:
                img.save(tpath, format="PNG")
            except Exception as e:
                self.log.debug("Could not write tile cache %s: %s", tpath, e)

        return img

    # ----------------------------
    # Alert -> polygons
    # ----------------------------

    def _polygons_and_zones_for_alert(self, feature: Dict[str, Any]) -> Tuple[List[PolyRings], List[ZonePolys]]:
        # Prefer alert geometry
        geom = feature.get("geometry")
        if geom:
            polys = extract_polyrings_from_geometry(geom)
            if polys:
                return polys, []

        # Fallback to zones
        props = feature.get("properties") or {}
        zones = props.get("affectedZones") or []

        used: List[ZonePolys] = []
        all_polys: List[PolyRings] = []

        for zurl in zones:
            try:
                zp = self._fetch_zone_polys_cached(zurl)
                if zp.polys:
                    used.append(zp)
                    all_polys.extend(zp.polys)
            except Exception as e:
                self.log.warning("Zone fetch failed: %s (%s)", zurl, e)

        return all_polys, used

    # ----------------------------
    # Basemap stitching
    # ----------------------------

    def _stitch_and_crop_basemap(
            self,
            *,
            tile_template: str,
            zoom: int,
            left: float, top: float, right: float, bottom: float,
            out_w: int, out_h: int,
    ) -> Image.Image:
        x0, y0, x1, y1 = tile_range_for_viewport(left, top, right, bottom, zoom)
        tiles_w = (x1 - x0 + 1)
        tiles_h = (y1 - y0 + 1)
        tile_count = tiles_w * tiles_h

        if tile_count > self.config.max_tiles:
            raise RuntimeError(f"Tile count {tile_count} exceeds max_tiles={self.config.max_tiles} at zoom={zoom}")

        mosaic = Image.new("RGBA", (tiles_w * TILE_SIZE, tiles_h * TILE_SIZE))
        world_tiles = 2 ** zoom

        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                tx_wrapped = tx % world_tiles
                tile_img = self._fetch_tile_cached(tile_template, z=zoom, x=tx_wrapped, y=ty)
                px = (tx - x0) * TILE_SIZE
                py = (ty - y0) * TILE_SIZE
                mosaic.paste(tile_img, (px, py))

        crop_left = int(round(left - (x0 * TILE_SIZE)))
        crop_top = int(round(top - (y0 * TILE_SIZE)))
        return mosaic.crop((crop_left, crop_top, crop_left + out_w, crop_top + out_h))

    # ----------------------------
    # Drawing helpers
    # ----------------------------

    def _load_font(self, size: int = 18) -> ImageFont.FreeTypeFont:
        for p in self.config.font_candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def _add_title_block(self, img: Image.Image, title: str, subtitle: str, attribution: str) -> Image.Image:
        out = img.convert("RGBA")
        draw = ImageDraw.Draw(out)
        font_title = self._load_font(22)
        font_sub = self._load_font(16)
        font_attr = self._load_font(14)

        pad = 10
        box_h = 72
        box = Image.new("RGBA", (out.size[0], box_h), (0, 0, 0, 120))
        out.alpha_composite(box, (0, 0))

        draw.text((pad, 8), title, font=font_title, fill=(255, 255, 255, 255))
        draw.text((pad, 38), subtitle, font=font_sub, fill=(230, 230, 230, 255))

        attr_w = draw.textlength(attribution, font=font_attr)
        draw.rectangle(
            (out.size[0] - int(attr_w) - pad - 6, out.size[1] - 28, out.size[0], out.size[1]),
            fill=(0, 0, 0, 120),
        )
        draw.text((out.size[0] - int(attr_w) - pad, out.size[1] - 24), attribution, font=font_attr, fill=(255, 255, 255, 230))
        return out

    def _mask_from_polys(
            self,
            img_size: Tuple[int, int],
            polys: List[PolyRings],
            zoom: int,
            viewport_left: float,
            viewport_top: float,
    ) -> Image.Image:
        mask = Image.new("L", img_size, 0)
        mdraw = ImageDraw.Draw(mask)

        def ring_to_px(ring: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
            pts: List[Tuple[int, int]] = []
            for lon, lat in ring:
                wx, wy = lonlat_to_world_px(lon, lat, zoom)
                pts.append((int(round(wx - viewport_left)), int(round(wy - viewport_top))))
            return pts

        for p in polys:
            outer = ring_to_px(p.outer)
            if len(outer) >= 3:
                mdraw.polygon(outer, fill=255)
                for h in p.holes:
                    hole = ring_to_px(h)
                    if len(hole) >= 3:
                        mdraw.polygon(hole, fill=0)

        return mask

    def _mask_centroid(self, mask: Image.Image, step: int = 2) -> Optional[Tuple[int, int]]:
        bbox = mask.getbbox()
        if not bbox:
            return None
        px = mask.load()
        x0, y0, x1, y1 = bbox

        sx = sy = cnt = 0
        for y in range(y0, y1, step):
            for x in range(x0, x1, step):
                if px[x, y] > 0:
                    sx += x
                    sy += y
                    cnt += 1
        if cnt > 0:
            return (sx // cnt, sy // cnt)
        return ((x0 + x1) // 2, (y0 + y1) // 2)

    def _draw_affected_area_on_image(
            self,
            base: Image.Image,
            polys: List[PolyRings],
            zoom: int,
            viewport_left: float,
            viewport_top: float,
            *,
            fill_rgba: RGBA,
            outline_rgba: RGBA,
            outline_width: int,
            label: Optional[str] = None,
    ) -> Image.Image:
        img = base.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        if not polys:
            return img

        mask = self._mask_from_polys(img.size, polys, zoom, viewport_left, viewport_top)

        # fill
        fill_layer = Image.new("RGBA", img.size, fill_rgba)
        overlay = Image.composite(fill_layer, overlay, mask)

        # outline: edge = mask - eroded(mask)
        eroded = mask.filter(ImageFilter.MinFilter(3))
        edge = ImageChops.subtract(mask, eroded)

        if outline_width > 1:
            k = outline_width if (outline_width % 2 == 1) else (outline_width + 1)
            k = max(3, k)
            edge = edge.filter(ImageFilter.MaxFilter(k))

        outline_layer = Image.new("RGBA", img.size, outline_rgba)
        overlay = Image.composite(outline_layer, overlay, edge)

        # optional label at centroid
        if label:
            c = self._mask_centroid(mask, step=2)
            if c:
                lx, ly = c
                font = self._load_font(16)
                odraw = ImageDraw.Draw(overlay)
                tb = odraw.textbbox((0, 0), label, font=font)
                tw = tb[2] - tb[0]
                th = tb[3] - tb[1]
                pad = 4
                x0 = max(0, min(img.size[0] - 1, lx - tw // 2 - pad))
                y0 = max(0, min(img.size[1] - 1, ly - th // 2 - pad))
                x1 = max(0, min(img.size[0], lx + tw // 2 + pad))
                y1 = max(0, min(img.size[1], ly + th // 2 + pad))
                odraw.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 140))
                odraw.text((x0 + pad, y0 + pad), label, font=font, fill=(255, 255, 255, 240))

        return Image.alpha_composite(img, overlay)

    def _zone_color(self, zone_id: str) -> Tuple[RGBA, RGBA]:
        d = hashlib.sha1(zone_id.encode("utf-8")).digest()
        r = 60 + (d[0] % 160)
        g = 60 + (d[1] % 160)
        b = 60 + (d[2] % 160)
        return (r, g, b, 72), (r, g, b, 220)

    def _polygon_centroid_px(self, points: List[Tuple[int, int]]) -> Tuple[int, int]:
        if len(points) < 3:
            if not points:
                return (0, 0)
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))

        pts = points[:]
        if pts[0] != pts[-1]:
            pts.append(pts[0])

        a = 0.0
        cx = 0.0
        cy = 0.0
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            cross = (x0 * y1) - (x1 * y0)
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross

        if abs(a) < 1e-9:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))

        a *= 0.5
        cx /= (6.0 * a)
        cy /= (6.0 * a)
        return (int(round(cx)), int(round(cy)))

    def _draw_zones_on_image(
            self,
            base: Image.Image,
            zones: List[ZonePolys],
            zoom: int,
            viewport_left: float,
            viewport_top: float,
    ) -> Image.Image:
        img = base.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        font = self._load_font(16)

        def ring_to_px(ring: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
            pts: List[Tuple[int, int]] = []
            for lon, lat in ring:
                wx, wy = lonlat_to_world_px(lon, lat, zoom)
                pts.append((int(round(wx - viewport_left)), int(round(wy - viewport_top))))
            return pts

        odraw = ImageDraw.Draw(overlay)

        for z in zones:
            if not z.polys:
                continue

            fill_rgba, outline_rgba = self._zone_color(z.zone_id)

            mask = Image.new("L", img.size, 0)
            mdraw = ImageDraw.Draw(mask)
            label_points: List[Tuple[int, int]] = []

            for p in z.polys:
                outer = ring_to_px(p.outer)
                if len(outer) >= 3:
                    mdraw.polygon(outer, fill=255)
                    label_points.append(self._polygon_centroid_px(outer))
                    for h in p.holes:
                        hole = ring_to_px(h)
                        if len(hole) >= 3:
                            mdraw.polygon(hole, fill=0)

            fill_layer = Image.new("RGBA", img.size, fill_rgba)
            overlay = Image.composite(fill_layer, overlay, mask)
            odraw = ImageDraw.Draw(overlay)

            for p in z.polys:
                for ring in [p.outer, *p.holes]:
                    pts = ring_to_px(ring)
                    if len(pts) >= 2:
                        odraw.line(pts + [pts[0]], fill=outline_rgba, width=3)

            if label_points:
                lx, ly = label_points[0]
                label = z.zone_id
                tb = odraw.textbbox((0, 0), label, font=font)
                tw = tb[2] - tb[0]
                th = tb[3] - tb[1]
                pad = 4
                x0 = max(0, min(img.size[0] - 1, lx - tw // 2 - pad))
                y0 = max(0, min(img.size[1] - 1, ly - th // 2 - pad))
                x1 = max(0, min(img.size[0], lx + tw // 2 + pad))
                y1 = max(0, min(img.size[1], ly + th // 2 + pad))
                odraw.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 140))
                odraw.text((x0 + pad, y0 + pad), label, font=font, fill=(255, 255, 255, 240))

        return Image.alpha_composite(img, overlay)

    def render_map(
            self,
            feature: Dict[str, Any],
            *,
            save: bool = False,
            out_path: Optional[Union[str, Path]] = None,
            optimize: bool = True,
            **kwargs: Any,
    ) -> bytes:
        """
        Single entry point.

        - Always returns PNG bytes.
        - If save=True (or out_path is provided), also writes the PNG to disk.
          If save=True and out_path is omitted, it saves under:
              <cache_dir>/renders/<default_output_name(feature)>
        """
        img = self.render_to_image(feature, **kwargs)


        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=optimize)
        png = buf.getvalue()

        if save or out_path is not None:
            if out_path is None:
                out_path = self.config.cache_dir / "renders" / self.default_output_name(feature)

            out_path = Path(out_path)
            ensure_dir(out_path.parent)
            out_path.write_bytes(png)

        return png

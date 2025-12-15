#!/usr/bin/env python3
"""
Fetch recent NWS alerts for multiple UGC zones and keep exactly ONE
Discord webhook message per logical alert chain (Alert→Updates→Cancel).

State is stored in one JSON file per zone (no SQLite needed).
Runs once, does its work, then exits — perfect for a 1‑minute cron job.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, Any, List

import requests
from dateutil.parser import isoparse
from urllib.parse import urlencode, quote

# ─────────────────────────  your table of codes  ─────────────────────────
from lib.utility_module import event_codes     # unchanged

from lib.noaa_alert_map_module import (
    NOAAAlertMapRenderer,
    NOAAAlertMapConfig,
    AlertColors,
)

# ─────────────────────────  CONSTANTS  ─────────────────────────
APP_NAME   = "icad_nws_alerts"
__version__ = "1.0.0"

UTC = timezone.utc

VTEC_RE = re.compile(
    r"/[A-Z]\.(NEW|CON|EXT|EXA|EXB|UPG|CAN|COR|EXP)\.([A-Z]{4})\.([A-Z]{2})\.([A-Z])\.(\d{4})\."
)

SEVERITY_COLOR = {
    "Extreme":  0x8B0000,
    "Severe":   0xFF0000,
    "Moderate": 0xFD8D14,
    "Minor":    0xFFFF00,
    "Unknown":  0x808080,
}

def get_log_level(name: str | None) -> int:
    """Map string/int env or config values to logging levels."""
    if name is None:
        return logging.INFO
    if isinstance(name, int):
        return name
    name = name.upper()
    return {
        "CRITICAL": logging.CRITICAL,
        "ERROR":    logging.ERROR,
        "WARNING":  logging.WARNING,
        "INFO":     logging.INFO,
        "DEBUG":    logging.DEBUG,
    }.get(name, logging.INFO)


def resolve_paths() -> tuple[Path, Path, Path]:
    """
    Returns (cfg_path, log_dir, state_dir), all rooted at the script's directory
    unless overridden via env vars.

    Layout (default):
      <repo-root>/etc/config.json
      <repo-root>/var/log/
      <repo-root>/var/state/
    """
    base = Path(__file__).resolve().parent

    cfg_path  = Path(os.environ.get("NOAA_ALERTS_CONFIG",  base / "etc" / "config.json"))

    # Single var/ root, then split into log/ and state/
    var_dir   = Path(os.environ.get("NOAA_ALERTS_VARDIR",  base / "var"))
    log_dir   = Path(os.environ.get("NOAA_ALERTS_LOGDIR",  var_dir / "log"))
    state_dir = Path(os.environ.get("NOAA_ALERTS_STATEDIR", var_dir / "state"))

    return cfg_path, log_dir, state_dir

# ─────────────────────────  LOGGING  ─────────────────────────
def setup_logging(
        log_dir: Path,
        filename: str = f"{APP_NAME}.log",
        level: int = logging.INFO,
        backup_days: int = 14,
) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / filename

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    fh = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=backup_days,
        utc=True,
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(level)

    root.handlers[:] = [fh, ch]
    return logging.getLogger(APP_NAME)


# ─────────────────────────  CONFIG  ─────────────────────────

def load_config(config_path: Path, state_dir: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    # required
    zones = cfg.get("zones")
    if not zones or not isinstance(zones, list):
        raise SystemExit("config.json must include a non-empty 'zones' list")

    # defaults
    cfg.setdefault("user_agent", f"{APP_NAME}/{__version__} (noaa-alerts@icaddispatch.com)")
    cfg.setdefault("state_dir", str(state_dir))
    cfg.setdefault("log_level", "INFO")

    cfg.setdefault("map", {})
    m = cfg["map"]
    m.setdefault("enabled", True)
    m.setdefault("width", 800)
    m.setdefault("height", 500)
    m.setdefault("show_title_block", False)
    m.setdefault("zones_mode", "affected")
    m.setdefault("label", None)
    m.setdefault("optimize", True)
    # Keep caches under var/ by default
    m.setdefault("cache_dir", str(Path(cfg["state_dir"]).resolve().parent / "cache_noaa_maps"))


    # ensure state dir exists
    Path(cfg["state_dir"]).mkdir(parents=True, exist_ok=True)

    return cfg

def zone_render_overrides(zone_map: dict) -> dict:
    out = {}
    if "width" in zone_map: out["width"] = int(zone_map["width"])
    if "height" in zone_map: out["height"] = int(zone_map["height"])
    if "zones_mode" in zone_map: out["zones_mode"] = str(zone_map["zones_mode"])
    if "show_title_block" in zone_map: out["show_title_block"] = bool(zone_map["show_title_block"])
    if "tile_template" in zone_map: out["tile_template"] = str(zone_map["tile_template"])
    if "attribution" in zone_map: out["attribution"] = str(zone_map["attribution"])
    return out

# ─────────────────────────  STATE (JSON)  ─────────────────────────

def state_path(cfg: Dict[str, Any], zone_id: str) -> str:
    return os.path.join(cfg["state_dir"], f"{zone_id}.json")

def load_state(cfg: Dict[str, Any], zone_id: str) -> Dict[str, Any]:
    """
    Returns:
      {
        "alerts": {
            "<canonical_id>": {
               "cap_id": "...",
               "discord_id": "...",
               "status": "posted|updated|cleared",
               "expires_at": "ISO-8601"
            },
            ...
        }
      }
    """
    path = state_path(cfg, zone_id)
    if not os.path.exists(path):
        return {"alerts": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to read state file %s: %s (starting empty)", path, e)
        return {"alerts": {}}

def save_state(cfg: Dict[str, Any], zone_id: str, state: Dict[str, Any]) -> None:
    """
    Atomic write to avoid corruption.
    """
    path = state_path(cfg, zone_id)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)

def prune_state(state: Dict[str, Any], now: datetime) -> None:
    """
    Remove any chain whose expires_at is >7 days in the past.
    """
    cutoff = (now - timedelta(days=7)).isoformat()
    alerts = state.get("alerts", {})
    doomed = [cid for cid, r in alerts.items() if r.get("expires_at", "") < cutoff]
    for cid in doomed:
        del alerts[cid]

# ───────────────────────  NOAA API helpers  ───────────────────────

def hazard_color(props: dict) -> int:
    return SEVERITY_COLOR.get(props.get("severity", "Unknown"), 0x808080)

def fetch_recent_alerts(zone_id: str, ua: str) -> List[dict]:
    """
    Pull EVERYTHING the NWS still lists as *status=actual* for the zone.
    No time window – that way we never miss an older alert if the job was down.
    """
    headers = {
        "User-Agent": ua,
        "Accept": "application/geo+json",
    }
    params = {
        "zone": zone_id,
        "status": "actual",
        "limit": 500,
    }
    url = f"https://api.weather.gov/alerts?{urlencode(params)}"
    log.debug("GET %s", url)
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()["features"]

def vtec_key(props: dict) -> str | None:
    """
    Return 'OFFICE-PHENSIG-ETN' (e.g. 'KBGM-HT.Y-0006') if a VTEC line exists,
    otherwise None.
    """
    for line in props.get("parameters", {}).get("VTEC", []):
        m = VTEC_RE.match(line)
        if m:
            office, phensig, sub, etn = m.group(2), m.group(3), m.group(4), m.group(5)
            return f"{office}-{phensig}.{sub}-{etn}"
    return None

def canonical_id(alert_id: str) -> str:
    # urn:oid:... .003.1  -> strip last two numeric parts
    parts = alert_id.split(".")
    return ".".join(parts[:-2])

def chain_key(props: dict) -> str:
    return vtec_key(props) or canonical_id(props["id"])

def latest_by_chain(features: List[dict]) -> Dict[str, dict]:
    latest = {}
    for f in sorted(features, key=lambda f: f["properties"]["sent"], reverse=True):
        k = chain_key(f["properties"])
        if k not in latest:
            latest[k] = f
    return latest

#  ─────────────────────── Alert Url Builder ───────────────────────
def _ugc_code(x: str | None) -> str | None:
    if not x:
        return None
    x = x.strip()
    # allow either "TXZ199" or ".../TXZ199"
    if "/" in x:
        x = x.rsplit("/", 1)[-1]
    return x if len(x) >= 6 else None

def _is_zone_ugc(ugc: str) -> bool:
    ugc = _ugc_code(ugc) or ""
    return len(ugc) >= 3 and ugc[2].upper() == "Z"

def _is_county_ugc(ugc: str) -> bool:
    ugc = _ugc_code(ugc) or ""
    return len(ugc) >= 3 and ugc[2].upper() == "C"

def vtec_office(props: dict) -> str | None:
    """
    From VTEC like /O.CON.KHGX.FZ.W.0004....../ -> returns 'KHGX'
    """
    for line in (props.get("parameters", {}) or {}).get("VTEC", []) or []:
        m = VTEC_RE.match(line)
        if m:
            return m.group(2)
    return None

def nws_wwa_text_url(props: dict) -> str | None:
    """
    Fallback “human-ish” page that doesn’t need warnzone/warncounty.
    Example: https://forecast.weather.gov/wwamap/wwatxtget.php?cwa=HGX&wwa=freeze+warning
    """
    event = (props.get("event") or "").strip()
    if not event:
        return None

    office4 = vtec_office(props)
    if not office4 or len(office4) != 4:
        return None

    cwa = office4[-3:]
    return "https://forecast.weather.gov/wwamap/wwatxtget.php?" + urlencode({
        "cwa": cwa,
        "wwa": event.lower(),   # this page accepts lowercased in practice
    })

def nws_human_alert_url(props: dict, *, zone_id: str | None = None) -> str | None:
    """
    Prefer showsigwx.php when we can build it; else fallback to wwatxtget.php.
    showsigwx.php wants:
      - warnzone=TXZ199 (forecast zone UGC)
      - warncounty=TXC339 (optional; county UGC)
      - product1=Freeze+Warning
    """
    event = (props.get("event") or "").strip()
    if not event:
        return nws_wwa_text_url(props)

    geocode = props.get("geocode") or {}
    ugc_list  = [c.strip() for c in (geocode.get("UGC") or []) if str(c).strip()]
    same_list = [str(c).strip() for c in (geocode.get("SAME") or []) if str(c).strip()]

    zid = _ugc_code(zone_id)

    # 1) Pick warnzone (prefer a Z-code)
    warnzone = None
    if zid and _is_zone_ugc(zid):
        warnzone = zid
    else:
        # try geocode UGC Z-codes
        warnzone = next((_ugc_code(u) for u in ugc_list if _is_zone_ugc(u)), None)

    # fallback: parse from affectedZones URLs if geocode lacks UGC Z-codes
    if not warnzone:
        for zurl in props.get("affectedZones") or []:
            z = _ugc_code(zurl)
            if z and _is_zone_ugc(z):
                warnzone = z
                break

    # 2) Pick warncounty (prefer explicit county zone_id, else any C-code, else derive from SAME)
    warncounty = None
    if zid and _is_county_ugc(zid):
        warncounty = zid
    else:
        warncounty = next((_ugc_code(u) for u in ugc_list if _is_county_ugc(u)), None)

    # If we still don't have a county UGC, derive TXC### from SAME (SSCCC) using state from warnzone.
    if not warncounty and same_list and warnzone and len(warnzone) >= 2:
        state = warnzone[:2].upper()
        county3 = str(same_list[0])[-3:].zfill(3)
        warncounty = f"{state}C{county3}"

    # If we have a warnzone, showsigwx works even if warncounty is missing. :contentReference[oaicite:2]{index=2}
    if warnzone:
        qs = {"warnzone": warnzone, "product1": event}
        if warncounty:
            qs["warncounty"] = warncounty
        return "https://forecast.weather.gov/showsigwx.php?" + urlencode(qs)

    # last resort
    return nws_wwa_text_url(props)

def nws_public_alert_page(props: dict, *, zone_id: str | None = None) -> str | None:
    """
    Best-effort URL for the embed title:

      1) Human forecast.weather.gov page (showsigwx.php preferred, else wwatxtget.php)
      2) props["@id"] (usually https://api.weather.gov/alerts/urn:oid:...)
      3) props["id"]  (if urn:..., convert to https://api.weather.gov/alerts/<urn>)
    """
    # 1) Prefer human pages
    human = nws_human_alert_url(props, zone_id=zone_id)
    if human:
        return human

    # 2) Prefer @id (often already a full URL)
    v = (props.get("@id") or "").strip()
    if v:
        return v

    # 3) Fall back to id
    v = (props.get("id") or "").strip()
    if not v:
        return None

    # If id is a URN, make it clickable by turning it into the NWS API URL
    if v.startswith("urn:"):
        return f"https://api.weather.gov/alerts/{v}"

    return v

# ───────────────────────  Discord helpers  ───────────────────────

def discord_post_embed(embed: dict, webhook_url: str, *, png_bytes: bytes | None = None, filename: str = "alert.png") -> str:
    payload = {
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }

    url = webhook_url + ("&wait=true" if "?" in webhook_url else "?wait=true")

    if png_bytes is None:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()["id"]

    # multipart w/ attachment
    payload["attachments"] = [{"id": 0, "filename": filename}]
    files = {"files[0]": (filename, png_bytes, "image/png")}
    r = requests.post(url, data={"payload_json": json.dumps(payload)}, files=files, timeout=30)
    r.raise_for_status()
    return r.json()["id"]

def discord_edit_embed(msg_id: str, embed: dict, webhook_url: str, *, png_bytes: bytes | None = None, filename: str = "alert.png"):
    url_base = webhook_url.split("?", 1)[0]
    url = f"{url_base}/messages/{msg_id}"

    payload = {
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }

    if png_bytes is None:
        r = requests.patch(url, json=payload, timeout=15)
        r.raise_for_status()
        return

    # multipart edit w/ attachment
    payload["attachments"] = [{"id": 0, "filename": filename}]
    files = {"files[0]": (filename, png_bytes, "image/png")}
    r = requests.patch(url, data={"payload_json": json.dumps(payload)}, files=files, timeout=30)
    r.raise_for_status()

def best_event_code(props: dict) -> str | None:
    """
    Resolve the best matching event code using the same priority as event_icon:
      1) eventCode["NationalWeatherService"]
      2) eventCode["SAME"] (excluding "NWS")
      3) props["event"] (rare fallback)
    Returns the code key that exists in event_codes, or None.
    """
    e_codes = props.get("eventCode", {}) or {}

    for c in e_codes.get("NationalWeatherService", []) or []:
        if c in event_codes:
            return c

    for c in e_codes.get("SAME", []) or []:
        if c != "NWS" and c in event_codes:
            return c

    ev = props.get("event")
    if ev and ev in event_codes:
        return ev

    return None


def alert_colors(props: dict, *, cleared: bool = False) -> AlertColors:
    """
    Pull fill/outline RGBA from event_codes using the best_event_code() resolver.
    If cleared, fade it a bit.
    """
    defaults = AlertColors()
    fill = defaults.fill_rgba
    outline = defaults.outline_rgba

    code = best_event_code(props)
    if code:
        d = event_codes.get(code, {}) or {}
        fill = d.get("fill_rgba", fill)
        outline = d.get("outline_rgba", outline)

    if cleared:
        fill = (fill[0], fill[1], fill[2], max(8, int(fill[3] * 0.40)))
        outline = (outline[0], outline[1], outline[2], max(80, int(outline[3] * 0.60)))

    return AlertColors(fill_rgba=fill, outline_rgba=outline, outline_width=3)


def event_icon(props: dict) -> str:
    code = best_event_code(props)
    if code:
        return event_codes[code].get("icon", "ℹ️")
    return event_codes.get(props.get("event", ""), {}).get("icon", "ℹ️")

def build_embed(props: dict, cleared: bool = False, *, zone_id: str | None = None) -> dict:
    ev_icon = event_icon(props)

    # Title (short!) – Discord hard limits to 256 chars.
    headline = props.get("headline") or props["event"]
    max_len  = 254 - len(ev_icon)
    if len(headline) > max_len:
        headline = headline[:max_len - 1] + "…"

    title_txt = f"{ev_icon} {headline}"
    if cleared:
        title_txt = f"~~{title_txt}~~ – CANCELLED"

    # Times
    starts = props.get("effective") or props["sent"]
    ends   = props.get("ends") or props.get("expires") or "—"

    # Risk trio
    sev = props.get("severity", "Unknown").title()
    urg = props.get("urgency", "Unknown").title()
    cer = props.get("certainty", "Unknown").title()
    risk = f"**{sev} • {urg} • {cer}**"

    # Area preview
    areas = props.get("areaDesc", "").split("; ")
    area_field = ", ".join(areas[:3]) + (f" … (+{len(areas)-3} more)" if len(areas) > 3 else "")

    # Description
    # CHANGED: keep FULL text, no paragraph split, no truncation
    descr = (props.get("description", "") or "").strip()
    descr = descr[:4000]

    return {
        "title": title_txt,
        "url": nws_public_alert_page(props, zone_id=zone_id) or props.get("@id") or props.get("id"),
        "description": descr,
        "color": hazard_color(props),
        "timestamp": props["sent"],
        "fields": [
            {"name": "Starts",   "value": starts,     "inline": True},
            {"name": "Ends",     "value": ends,       "inline": True},
            {"name": "Severity", "value": risk,       "inline": False},
            {"name": "Affected", "value": area_field, "inline": False},
        ],
        "footer": {
            "text": f"{props.get('senderName','NWS')} – "
                    f"{datetime.fromisoformat(props['sent']).strftime('%b %d %I:%M %p')}"
        }
    }

# ───────────────────────  Alert life-cycle helpers  ───────────────────────

def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return isoparse(ts).astimezone(UTC)

def event_end_iso(props: dict) -> str | None:
    ends = props.get("ends")
    if ends:
        return ends
    end_param = (props.get("parameters", {}).get("eventEndingTime") or [None])[0]
    if end_param:
        return end_param
    return None

def derive_expires(props: dict) -> str:
    t_end = (parse_iso(event_end_iso(props)) or parse_iso(props.get("expires")))
    if not t_end:
        t_end = datetime.now(UTC) + timedelta(days=14)
    return t_end.isoformat()

def _first(*vals):
    return next((v for v in vals if v), None)

def is_still_effective(props: dict, now: datetime) -> bool:
    if props.get("messageType", "").lower() == "cancel":
        return False
    if "replacedBy" in props:
        return False

    t_end = _first(
        parse_iso(props.get("expires")),
        parse_iso(props.get("ends")),
        parse_iso((props.get("parameters", {}).get("eventEndingTime") or [None])[0]),
    )
    return not (t_end and now >= t_end)

# ───────────────────────  Runner (per zone)  ───────────────────────
def run_for_zone(cfg: Dict[str, Any], zone: Dict[str, Any], renderer: NOAAAlertMapRenderer | None) -> None:
    zone_id  = zone["zone_id"]
    webhooks = zone.get("webhooks", [])
    if not webhooks:
        log.warning("No webhook configured for zone %s – skipping", zone_id)
        return

    state = load_state(cfg, zone_id)
    now   = datetime.now(UTC)

    try:
        feats = fetch_recent_alerts(zone_id, cfg.get("user_agent", "noaa_alerts_bot"))
    except Exception as e:
        log.exception("NWS fetch failed for %s: %s", zone_id, e)
        return

    latest = latest_by_chain(feats)
    cur    = state.get("alerts", {})

    base_map = cfg.get("map", {}) or {}
    zone_map = zone.get("map", {}) or {}
    effective_map = {**base_map, **zone_map}
    fname = str(effective_map.get("filename") or "alert.png")

    map_enabled = (
            renderer is not None
            and bool(effective_map.get("enabled", True))
    )

    for cid, feat in sorted(latest.items(), key=lambda kv: kv[1]["properties"]["sent"]):
        props   = feat["properties"]
        cap_id  = props["id"]
        row     = cur.get(cid)

        active  = is_still_effective(props, now)
        cleared = not active

        # ── Decide action FIRST (so we can skip fast) ────────────────────
        if row is None:
            if cleared:
                log.info("[%s] Skipped expired %s (never seen)", zone_id, cid)
                continue
            action = "post"
        else:
            already_cleared = (row.get("status") == "cleared")
            should_edit = (cap_id != row.get("cap_id")) or (cleared and not already_cleared)
            if not should_edit:
                # Already posted and still current — no Discord edit, no map render.
                log.info(
                    "[%s] Skipped %s (up-to-date) cap_id=%s status=%s cleared=%s",
                    zone_id, cid, row.get("cap_id"), row.get("status"), cleared
                )
                continue
            action = "edit"

        # ── Only now do we build embed / render map ─────────────────────
        try:
            embed = build_embed(props, cleared, zone_id=zone_id)

            png = None
            if map_enabled:
                try:
                    png = renderer.render_map(
                        feat,
                        save=False,
                        optimize=bool(effective_map.get("optimize", True)),
                        affected_colors=alert_colors(props, cleared=cleared),
                        label=effective_map.get("label"),
                        title=props.get("event") or "NOAA Alert",
                        subtitle=None,
                        **zone_render_overrides(zone_map),
                    )
                    embed["image"] = {"url": f"attachment://{fname}"}
                except Exception as e:
                    log.exception("[%s] Map render failed for %s: %s", zone_id, cid, e)
                    png = None  # fall back to no image

            if action == "post":
                msg_id = discord_post_embed(embed, webhooks[0], png_bytes=png, filename=fname)
                cur[cid] = {
                    "cap_id":     cap_id,
                    "discord_id": msg_id,
                    "status":     "posted",
                    "expires_at": derive_expires(props),
                }
                log.info("[%s] Posted %s (new)", zone_id, cid)

            else:  # action == "edit"
                try:
                    discord_edit_embed(row["discord_id"], embed, webhooks[0], png_bytes=png, filename=fname)
                except requests.HTTPError as e:
                    if e.response is not None and e.response.status_code == 404:
                        log.warning("[%s] Discord 404 for %s – re-posting", zone_id, cid)
                        new_id = discord_post_embed(embed, webhooks[0], png_bytes=png, filename=fname)
                        row["discord_id"] = new_id
                    else:
                        raise

                row["cap_id"]     = cap_id
                row["status"]     = "cleared" if cleared else "updated"
                row["expires_at"] = derive_expires(props)
                log.info("[%s] Edited %s (%s)", zone_id, cid, row["status"])

        except Exception as e:
            log.exception("[%s] Discord failure for %s: %s", zone_id, cid, e)

    prune_state(state, now)
    state["alerts"] = cur
    save_state(cfg, zone_id, state)

# ─────────────────────────  main  ─────────────────────────

def main():
    # Resolve paths (env overrides supported)
    cfg_path, log_dir, state_default = resolve_paths()

    # If the config is missing, fail fast *before* we even try to log to file.
    if not cfg_path.exists():
        # minimal console logger so the user sees _something_
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s  %(levelname)s  %(message)s")
        logging.error("Config file %s not found. Aborting.", cfg_path)
        raise SystemExit(2)

    # Load config now (so we can grab log_level), then initialize full logging
    tmp_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    level   = get_log_level(tmp_cfg.get("log_level") or os.environ.get("NOAA_ALERTS_LOGLEVEL"))

    global log
    log = setup_logging(log_dir, f"{APP_NAME}.log", level=level)

    # Re-load using our loader (so it also validates & creates state_dir)
    cfg = load_config(cfg_path, state_default)

    base_map = cfg.get("map", {}) or {}

    renderer = None
    if base_map.get("enabled", True):
        renderer = NOAAAlertMapRenderer(
            config=NOAAAlertMapConfig(
                width=int(base_map.get("width", 800)),
                height=int(base_map.get("height", 500)),
                show_title_block=bool(base_map.get("show_title_block", False)),
                zones_mode_default=str(base_map.get("zones_mode", "affected")),
                cache_dir=Path(base_map.get("cache_dir")),
                user_agent=str(cfg.get("user_agent")),

                # also include these so you don't have to pass them on every render:
                tile_template=str(base_map.get("tile_template", NOAAAlertMapConfig().tile_template)),
                attribution=str(base_map.get("attribution", NOAAAlertMapConfig().attribution)),
                min_zoom=int(base_map.get("min_zoom", NOAAAlertMapConfig().min_zoom)),
                max_zoom=int(base_map.get("max_zoom", NOAAAlertMapConfig().max_zoom)),
                margin_frac=float(base_map.get("margin_frac", NOAAAlertMapConfig().margin_frac)),
                max_tiles=int(base_map.get("max_tiles", NOAAAlertMapConfig().max_tiles)),
                tile_delay_s=float(base_map.get("tile_delay_s", NOAAAlertMapConfig().tile_delay_s)),
                request_timeout_s=int(base_map.get("request_timeout_s", NOAAAlertMapConfig().request_timeout_s)),
                zone_json_ttl_s=int(base_map.get("zone_json_ttl_s", NOAAAlertMapConfig().zone_json_ttl_s)),
                zone_poly_ttl_s=int(base_map.get("zone_poly_ttl_s", NOAAAlertMapConfig().zone_poly_ttl_s)),
                tile_ttl_s=int(base_map.get("tile_ttl_s", NOAAAlertMapConfig().tile_ttl_s)),
            ),
            logger=log,
        )

    log.info("Starting %s %s with config=%s", APP_NAME, __version__, cfg_path)

    # Run each zone
    for zone in cfg["zones"]:
        try:
            run_for_zone(cfg, zone, renderer)
        except Exception:
            log.exception("Unhandled error while processing zone %s", zone.get("zone_id"))

    log.info("Run completed.")

if __name__ == "__main__":
    main()

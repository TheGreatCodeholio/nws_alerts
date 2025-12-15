DEFAULT_FILL_RGBA    = (255, 0, 0, 25)
DEFAULT_OUTLINE_RGBA = (255, 0, 0, 220)

event_codes = {
    'HTY': {'text': 'Heat Advisory', 'icon': '🌡️', 'level': 'advisory',
            'fill_rgba': (255, 127, 80, 25), 'outline_rgba': (255, 127, 80, 220)},  # FF7F50

    'TOE': {'text': '911 Outage Emergency', 'icon': '⛔', 'level': 'advisory',
            'fill_rgba': (192, 192, 192, 25), 'outline_rgba': (192, 192, 192, 220)},  # C0C0C0

    'ADR': {'text': 'Administrative Message', 'icon': '📋', 'level': 'advisory',
            'fill_rgba': (192, 192, 192, 25), 'outline_rgba': (192, 192, 192, 220)},  # C0C0C0

    'AVW': {'text': 'Avalanche Warning', 'icon': '❄️', 'level': 'warning',
            'fill_rgba': (30, 144, 255, 25), 'outline_rgba': (30, 144, 255, 220)},  # 1E90FF

    'AVA': {'text': 'Avalanche Watch', 'icon': '🏔️', 'level': 'watch',
            'fill_rgba': (244, 164, 96, 25), 'outline_rgba': (244, 164, 96, 220)},  # F4A460

    'BHW': {'text': 'Biological Hazard Warning', 'icon': '☣️', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'BZW': {'text': 'Blizzard Warning', 'icon': '🌨️', 'level': 'warning',
            'fill_rgba': (255, 69, 0, 25), 'outline_rgba': (255, 69, 0, 220)},  # FF4500

    'BLU': {'text': 'Blue Alert', 'icon': '🔵', 'level': 'advisory',
            'fill_rgba': (255, 255, 255, 25), 'outline_rgba': (255, 255, 255, 220)},  # FFFFFF (Transparent)

    'BWW': {'text': 'Boil Water Warning', 'icon': '🚱', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'CHW': {'text': 'Chemical Hazard Warning', 'icon': '🧪', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'CAE': {'text': 'Child Abduction Emergency', 'icon': '🚨', 'level': 'advisory',
            'fill_rgba': (255, 255, 255, 25), 'outline_rgba': (255, 255, 255, 220)},  # FFFFFF (Transparent)

    'CDW': {'text': 'Civil Danger Warning', 'icon': '⚠️', 'level': 'warning',
            'fill_rgba': (255, 182, 193, 25), 'outline_rgba': (255, 182, 193, 220)},  # FFB6C1

    'CEM': {'text': 'Civil Emergency Message', 'icon': '📢', 'level': 'advisory',
            'fill_rgba': (255, 182, 193, 25), 'outline_rgba': (255, 182, 193, 220)},  # FFB6C1

    'CFW': {'text': 'Coastal Flood Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': (34, 139, 34, 25), 'outline_rgba': (34, 139, 34, 220)},  # 228B22

    'CFA': {'text': 'Coastal Flood Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': (102, 205, 170, 25), 'outline_rgba': (102, 205, 170, 220)},  # 66CDAA

    'DEW': {'text': 'Contagious Disease Warning', 'icon': '🦠', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'CWW': {'text': 'Contaminated Water Warning', 'icon': '🚱', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'DBW': {'text': 'Dam Break Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'DBA': {'text': 'Dam Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'DMO': {'text': 'Demo Warning', 'icon': '🛠️', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'DSW': {'text': 'Dust Storm Warning', 'icon': '🌪️', 'level': 'warning',
            'fill_rgba': (255, 228, 196, 25), 'outline_rgba': (255, 228, 196, 220)},  # FFE4C4

    'EQW': {'text': 'Earthquake Warning', 'icon': '🌎', 'level': 'warning',
            'fill_rgba': (139, 69, 19, 25), 'outline_rgba': (139, 69, 19, 220)},  # 8B4513

    'EAN': {'text': 'Emergency Action Notification', 'icon': '🚨', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'EAT': {'text': 'Emergency Action Termination', 'icon': '🔚', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'EVI': {'text': 'Evacuation Immediate', 'icon': '🏃‍♂️', 'level': 'advisory',
            'fill_rgba': (127, 255, 0, 25), 'outline_rgba': (127, 255, 0, 220)},  # 7FFF00

    'EVA': {'text': 'Evacuation Watch', 'icon': '🏃‍♂️', 'level': 'watch',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'EWW': {'text': 'Extreme Wind Warning', 'icon': '🚩', 'level': 'warning',
            'fill_rgba': (255, 140, 0, 25), 'outline_rgba': (255, 140, 0, 220)},  # FF8C00

    'FRW': {'text': 'Fire Warning', 'icon': '🔥', 'level': 'warning',
            'fill_rgba': (160, 82, 45, 25), 'outline_rgba': (160, 82, 45, 220)},  # A0522D

    'FFS': {'text': 'Flash Flood Statement', 'icon': '🌧️', 'level': 'advisory',
            'fill_rgba': (139, 0, 0, 25), 'outline_rgba': (139, 0, 0, 220)},  # 8B0000

    'FFW': {'text': 'Flash Flood Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': (139, 0, 0, 25), 'outline_rgba': (139, 0, 0, 220)},  # 8B0000

    'FFA': {'text': 'Flash Flood Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': (46, 139, 87, 25), 'outline_rgba': (46, 139, 87, 220)},  # 2E8B57

    'FSW': {'text': 'Flash Freeze Warning', 'icon': '❄️', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'FLS': {'text': 'Flood Statement', 'icon': '🌧️', 'level': 'advisory',
            'fill_rgba': (0, 255, 0, 25), 'outline_rgba': (0, 255, 0, 220)},  # 00FF00

    'FLW': {'text': 'Flood Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': (0, 255, 0, 25), 'outline_rgba': (0, 255, 0, 220)},  # 00FF00

    'FLA': {'text': 'Flood Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': (46, 139, 87, 25), 'outline_rgba': (46, 139, 87, 220)},  # 2E8B57

    'FCW': {'text': 'Food Contamination Warning', 'icon': '☣️', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'FZW': {'text': 'Freeze Warning', 'icon': '❄️', 'level': 'warning',
            'fill_rgba': (72, 61, 139, 25), 'outline_rgba': (72, 61, 139, 220)},  # 483D8B

    'HMW': {'text': 'Hazardous Materials Warning', 'icon': '⚠️', 'level': 'warning',
            'fill_rgba': (75, 0, 130, 25), 'outline_rgba': (75, 0, 130, 220)},  # 4B0082

    'HWW': {'text': 'High Wind Warning', 'icon': '🚩', 'level': 'warning',
            'fill_rgba': (218, 165, 32, 25), 'outline_rgba': (218, 165, 32, 220)},  # DAA520

    'HWA': {'text': 'High Wind Watch', 'icon': '🍃', 'level': 'watch',
            'fill_rgba': (184, 134, 11, 25), 'outline_rgba': (184, 134, 11, 220)},  # B8860B

    'HLS': {'text': 'Hurricane Statement', 'icon': '🌀', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'HUW': {'text': 'Hurricane Warning', 'icon': '🌀', 'level': 'warning',
            'fill_rgba': (220, 20, 60, 25), 'outline_rgba': (220, 20, 60, 220)},  # DC143C

    'HUA': {'text': 'Hurricane Watch', 'icon': '🌀', 'level': 'watch',
            'fill_rgba': (255, 0, 255, 25), 'outline_rgba': (255, 0, 255, 220)},  # FF00FF

    'IBW': {'text': 'Iceberg Warning', 'icon': '🧊', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'IFW': {'text': 'Industrial Fire Warning', 'icon': '🏭🔥', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'LSW': {'text': 'Land Slide Warning', 'icon': '🪨', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'LEW': {'text': 'Law Enforcement Warning', 'icon': '🚓', 'level': 'warning',
            'fill_rgba': (192, 192, 192, 25), 'outline_rgba': (192, 192, 192, 220)},  # C0C0C0

    'LAE': {'text': 'Local Area Emergency', 'icon': '📢', 'level': 'advisory',
            'fill_rgba': (192, 192, 192, 25), 'outline_rgba': (192, 192, 192, 220)},  # C0C0C0

    'NAT': {'text': 'National Audible Test', 'icon': '🔔', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'NIC': {'text': 'National Information Center', 'icon': 'ℹ️', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'NPT': {'text': 'National Periodic Test', 'icon': '📝', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'NST': {'text': 'National Silent Test', 'icon': '🔕', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'NMN': {'text': 'Network Message Notification', 'icon': '📡', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'NUW': {'text': 'Nuclear Plant Warning', 'icon': '☢️', 'level': 'warning',
            'fill_rgba': (75, 0, 130, 25), 'outline_rgba': (75, 0, 130, 220)},  # 4B0082

    'POS': {'text': 'Power Outage Statement', 'icon': '🔌', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'RHW': {'text': 'Radiological Hazard Warning', 'icon': '☢️', 'level': 'warning',
            'fill_rgba': (75, 0, 130, 25), 'outline_rgba': (75, 0, 130, 220)},  # 4B0082

    'RMT': {'text': 'Required Monthly Test', 'icon': '📅', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'RWT': {'text': 'Required Weekly Test', 'icon': '📆', 'level': 'advisory',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'SVR': {'text': 'Severe Thunderstorm Warning', 'icon': '⛈️', 'level': 'warning',
            'fill_rgba': (255, 165, 0, 25), 'outline_rgba': (255, 165, 0, 220)},  # FFA500

    'SVA': {'text': 'Severe Thunderstorm Watch', 'icon': '⛈️', 'level': 'watch',
            'fill_rgba': (219, 112, 147, 25), 'outline_rgba': (219, 112, 147, 220)},  # DB7093

    'SVS': {'text': 'Severe Weather Statement', 'icon': '⚠️', 'level': 'advisory',
            'fill_rgba': (0, 255, 255, 25), 'outline_rgba': (0, 255, 255, 220)},  # 00FFFF

    'SPW': {'text': 'Shelter in Place Warning', 'icon': '🏠', 'level': 'warning',
            'fill_rgba': (250, 128, 114, 25), 'outline_rgba': (250, 128, 114, 220)},  # FA8072

    'SQW': {'text': 'Snow Squall Warning', 'icon': '🌨️', 'level': 'warning',
            'fill_rgba': (199, 21, 133, 25), 'outline_rgba': (199, 21, 133, 220)},  # C71585

    'SMW': {'text': 'Special Marine Warning', 'icon': '🚤', 'level': 'warning',
            'fill_rgba': (255, 165, 0, 25), 'outline_rgba': (255, 165, 0, 220)},  # FFA500

    'SPS': {'text': 'Special Weather Statement', 'icon': '📢', 'level': 'advisory',
            'fill_rgba': (255, 228, 181, 25), 'outline_rgba': (255, 228, 181, 220)},  # FFE4B5

    'SSW': {'text': 'Storm Surge Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': (181, 36, 247, 25), 'outline_rgba': (181, 36, 247, 220)},  # B524F7

    'SSA': {'text': 'Storm Surge Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': (219, 127, 247, 25), 'outline_rgba': (219, 127, 247, 220)},  # DB7FF7

    'TOR': {'text': 'Tornado Warning', 'icon': '🌪️', 'level': 'warning',
            'fill_rgba': (255, 0, 0, 25), 'outline_rgba': (255, 0, 0, 220)},  # FF0000

    'TOA': {'text': 'Tornado Watch', 'icon': '🌪️', 'level': 'watch',
            'fill_rgba': (255, 255, 0, 25), 'outline_rgba': (255, 255, 0, 220)},  # FFFF00

    'TRW': {'text': 'Tropical Storm Warning', 'icon': '🌀', 'level': 'warning',
            'fill_rgba': (178, 34, 34, 25), 'outline_rgba': (178, 34, 34, 220)},  # B22222

    'TRA': {'text': 'Tropical Storm Watch', 'icon': '🌀', 'level': 'watch',
            'fill_rgba': (240, 128, 128, 25), 'outline_rgba': (240, 128, 128, 220)},  # F08080

    'TSW': {'text': 'Tsunami Warning', 'icon': '🌊', 'level': 'warning',
            'fill_rgba': (253, 99, 71, 25), 'outline_rgba': (253, 99, 71, 220)},  # FD6347

    'TSA': {'text': 'Tsunami Watch', 'icon': '🌊', 'level': 'watch',
            'fill_rgba': (255, 0, 255, 25), 'outline_rgba': (255, 0, 255, 220)},  # FF00FF

    'VOW': {'text': 'Volcano Warning', 'icon': '🌋', 'level': 'warning',
            'fill_rgba': (47, 79, 79, 25), 'outline_rgba': (47, 79, 79, 220)},  # 2F4F4F

    'WFW': {'text': 'Wild Fire Warning', 'icon': '🔥', 'level': 'warning',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'WFA': {'text': 'Wild Fire Watch', 'icon': '🔥', 'level': 'watch',
            'fill_rgba': DEFAULT_FILL_RGBA, 'outline_rgba': DEFAULT_OUTLINE_RGBA},

    'WSW': {'text': 'Winter Storm Warning', 'icon': '❄️', 'level': 'warning',
            'fill_rgba': (255, 105, 180, 25), 'outline_rgba': (255, 105, 180, 220)},  # FF69B4

    'WSA': {'text': 'Winter Storm Watch', 'icon': '❄️', 'level': 'watch',
            'fill_rgba': (70, 130, 180, 25), 'outline_rgba': (70, 130, 180, 220)},  # 4682B4
}

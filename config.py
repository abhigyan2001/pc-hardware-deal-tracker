"""Tunables for the Flipkart deal tracker, plus the relevance rules.

Relevance lives here rather than in the scraper because it is applied twice: when
deciding what to store, and again when building the dashboard. That second pass
means tightening a filter hides stale rows immediately, without deleting price
history that would be needed if you loosen the filter again later.
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "prices.db"
DASHBOARD_PATH = DATA_DIR / "dashboard.html"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"

# Retailers to scrape. The definitions live in sites.py; category rules below
# are shared across retailers, since they describe the product, not the shop.
ENABLED_SITES = ["flipkart", "amazon"]

# Result pages per search query. Queries are narrow, so the interesting listings
# are on the first pages; going deeper mostly adds noise and requests.
MAX_PAGES = 2

MIN_DELAY = 3.0
MAX_DELAY = 6.5

HEADLESS = True
PAGE_TIMEOUT_MS = 45_000

SUSPICIOUS_MRP_RATIO = 2.5
STALE_AFTER_HOURS = 48
HISTORY_WINDOW_DAYS = 90
MIN_ITEMS_PER_PAGE_BEFORE_WARNING = 5

# Junk deliberately mis-listed in hardware categories with keyword-stuffed
# titles, e.g. "Auronix E88 Pro 4K Drone ... NVIDIA Chipset Graphics Card".
# The stuffed keyword defeats per-category matching, so these are excluded by
# what the product actually is. Applied to every category.
GLOBAL_EXCLUDE = [
    "drone", "quadcopter", "fpv", "smartwatch", "smart watch", "earbud",
    "headphone", "neckband", "trimmer", "shaver", "massager", "power bank",
    "selfie", "tripod", "projector", "doll", "kettle", "grinder", "induction",
    "gimbal", "stabilizer", "vlogging",
]

# Each category runs several searches and merges the results by product id.
# `queries` is used for every retailer; add `queries_amazon` (or
# `queries_<site>`) to a category to override them for just that one.
#
# require_groups is a list of keyword groups: a title must match at least one
# keyword in EVERY group. That allows conditions to be ANDed - a monitor must be
# a monitor AND be 4K or 1440p - which a single flat keyword list cannot express.
#
# min_capacity_gb compares the largest capacity named in the title, so "1 TB"
# clears a 512 floor and "500 GB" does not.
CATEGORIES = {
    "monitor": {
        "label": "Monitors (4K / 1440p)",
        "queries": ["4k monitor", "1440p qhd monitor", "oled 4k monitor"],
        "require_groups": [
            ["monitor", "display"],
            # Resolution. "1440" catches 2560x1440 and 1440p; "2160" catches
            # 3840x2160. Bare "2k" is left out - it false-positives on model
            # numbers, and Indian listings that mean 1440p almost always say QHD.
            ["4k", "uhd", "ultra hd", "qhd", "wqhd", "1440", "2160"],
        ],
        "exclude_any": [
            "baby", "blood pressure", "heart rate", "bp monitor", "stand",
            "mount", "arm", "skin", "screen guard", "cleaner", "cable",
            "adapter", "cctv", "camera",
        ],
        "min_price": 7000,
    },
    "ram": {
        "label": "RAM (DDR5)",
        # Parse size, kit, speed and desktop/laptop from titles for ₹ per GB.
        "ram_specs": True,
        "queries": ["ddr5 desktop ram", "ddr5 ram 32gb"],
        "require_groups": [["ddr5"]],
        "exclude_any": [
            "cooler", "heatsink", "graphics card", "ssd", "hard disk",
            "monitor", "cleaner",
        ],
        "min_price": 1500,
    },
    "ssd": {
        "label": "SSD (512GB+)",
        "queries": ["internal ssd nvme 1tb", "internal ssd 512gb", "nvme ssd 2tb"],
        "require_groups": [["ssd", "nvme", "solid state"]],
        "exclude_any": [
            "enclosure", "caddy", "docking", "cable", "adapter", "cleaner",
            "bracket",
        ],
        "min_price": 1800,
        "min_capacity_gb": 512,
    },
    "hdd": {
        "label": "HDD (512GB+)",
        "queries": ["internal hard disk drive 1tb", "internal hard disk 2tb"],
        "require_groups": [["hard disk", "hard drive", "hdd"]],
        "exclude_any": [
            "ssd", "enclosure", "caddy", "docking", "cable", "cleaner",
            "bracket",
        ],
        "min_price": 1000,
        "min_capacity_gb": 512,
    },
    "gpu": {
        "label": "Graphics Cards",
        "queries": ["graphics card", "rtx graphics card"],
        "require_groups": [
            ["graphics card", "graphic card", "gpu", "rtx", "gtx", "radeon",
             "geforce", "arc a"],
        ],
        "exclude_any": [
            "vacuum", "cleaner", "vr headset", "holder", "bracket", "stand",
            "riser", "cable", "hard disk", "cooler", "toy", "airplane",
            "mouse", "keyboard", "ram ",
        ],
        # Drones relisted as graphics cards keep changing names ("E88 Pro Aero
        # Zoom", "Sky Rider"), so chasing the word "drone" is whack-a-mole. What
        # gives them away is the auto-filled spec block: a real card never has a
        # 0-bit bus or a 0 MHz clock. Word boundaries matter here - a plain
        # substring test for "0 bit" would also reject a genuine 320 bit card.
        "exclude_regex": [r"\b0\s*bit\b", r"\b0(\.0)?\s*mhz\b"],
        "min_price": 1500,
    },
    "cpu": {
        "label": "Processors (AM5)",
        # The per-generation queries ("ryzen 7000 processor", "ryzen 9000
        # processor") were measured and returned zero products the broad query
        # had not already found, so they were dropped. Flipkart spells the
        # socket out in CPU titles, which makes "am5 socket" a productive query.
        "queries": ["amd ryzen processor", "am5 socket processor"],
        # Flipkart titles almost never say "AM5" - they say "AMD Ryzen 5 7600X".
        # So the socket is identified by model family instead: Ryzen 7000, 8000
        # and 9000 desktop parts are AM5, which also excludes AM4 chips like the
        # 5600X without needing to list them.
        "require_groups": [
            ["ryzen", "am5"],
            ["am5", "7500", "7600", "7700", "7800", "7900", "7950",
             "8400", "8500", "8600", "8700",
             "9600", "9700", "9800", "9900", "9950"],
        ],
        "exclude_any": [
            "cooler", "thermal paste", "holder", "bracket", "motherboard",
            "cleaner", "laptop", "assembler", "prebuilt", "gaming pc",
            "desktop pc", "all in one",
        ],
        "min_price": 8000,
    },
    "cooler": {
        "label": "Liquid Coolers",
        "queries": ["liquid cpu cooler aio", "aio cpu cooler 240mm"],
        "require_groups": [["liquid cool", "water cool", "aio", "liquid cpu"]],
        # "air cooler" here means a room cooler, which dominates this query.
        "exclude_any": [
            "air cooler", "room", "thermal paste", "cooling pad", "desert",
            "tower fan",
        ],
        "min_price": 1500,
    },
}

# The lookbehind stops model numbers being read as sizes ("GP-AG42TB" is a
# 2 TB drive, not 42 TB), and the lookahead skips link speeds like "6 Gb/s".
# Both matter now that capacity drives the price-per-TB ranking, where one
# misread title would sit at the top of the list.
_CAPACITY_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(tb|gb)\b(?!\s*/\s*s)",
                          re.IGNORECASE)


def max_capacity_gb(title: str, gb_per_tb: int = 1024) -> float:
    """Largest storage size named in a title, in GB. 0 when none is found.

    Pass gb_per_tb=1000 for drive-maker units, where a "1000 GB" listing and a
    "1 TB" listing are the same drive."""
    best = 0.0
    for amount, unit in _CAPACITY_RE.findall(title):
        gb = float(amount) * (gb_per_tb if unit.lower() == "tb" else 1)
        best = max(best, gb)
    return best


def is_ram(cfg: dict | None) -> bool:
    """Categories whose titles carry RAM specs, which get price-per-GB."""
    return bool(cfg and cfg.get("ram_specs"))


def is_storage(cfg: dict | None) -> bool:
    """Categories sized by capacity, which get price-per-TB on the dashboard."""
    return bool(cfg and cfg.get("min_capacity_gb"))


# "External DDR Cache Buffer" is an internal NVMe drive's spec sheet talking,
# so external/portable only counts when it is not describing a cache.
_EXTERNAL_RE = re.compile(r"\b(external|portable)\b(?!\s+(ddr|dram|cache))",
                          re.IGNORECASE)


def drive_form(title: str) -> str:
    """'external' for portable/USB drives, else 'internal'. Drives sold as a
    bare internal disk "with cover" count as external, which is what they are."""
    return "external" if _EXTERNAL_RE.search(title) else "internal"


# Kits are written "2x16GB", "2 x 16GB", "1 * 32 GB", "(2X24GB)" or "16GBx2".
_KIT_RE = re.compile(r"(?<![\w.])([1-8])\s*[x×*]\s*(\d+)\s*gb\b", re.IGNORECASE)
_KIT_REV_RE = re.compile(r"(?<![\w.])(\d+)\s*gb\s*[x×*]\s*([1-8])\b", re.IGNORECASE)
_KIT_OF_RE = re.compile(r"\bkit of ([2-8])\b", re.IGNORECASE)
# Speed as "6000MHz", "6000 MT/s", "DDR5-5600", "5600 DDR5", or a seller's
# "6000HZ". Five-digit PC5-48000 bandwidth ratings are deliberately skipped.
_MHZ_RES = [
    re.compile(r"(?<![\w.])(\d{4})\s*(?:mhz|mt/s|hz)\b", re.IGNORECASE),
    re.compile(r"\bddr5[-\s]?(\d{4})\b", re.IGNORECASE),
    re.compile(r"(?<![\w.])(\d{4})\s+ddr5\b", re.IGNORECASE),
]


def ram_spec(title: str) -> dict:
    """Total GB, stick count, rated speed and form factor of a RAM listing.

    A title with no kit marker is taken as one stick: kits are a selling point
    and are nearly always advertised. Flipkart's "(Dual Channel)" label is
    ignored because it is attached to single sticks too. Speed is the highest
    rating named ("4800MHz/5600MHZ" -> 5600), or None when there is none."""
    sticks, per = 1, None
    if m := _KIT_RE.search(title):
        sticks, per = int(m.group(1)), float(m.group(2))
    elif m := _KIT_REV_RE.search(title):
        per, sticks = float(m.group(1)), int(m.group(2))
    elif m := _KIT_OF_RE.search(title):
        sticks = int(m.group(1))

    total = sticks * per if per else max_capacity_gb(title)

    speeds = [int(s) for rx in _MHZ_RES for s in rx.findall(title)]
    speeds = [s for s in speeds if 3000 <= s <= 9999]

    t = title.lower()
    if re.search(r"so-?dimm", t):
        form = "laptop"
    elif re.search(r"u-?dimm|desktop", t):
        form = "desktop"
    else:
        form = "laptop" if "laptop" in t else "desktop"

    return {"gb": total or None, "sticks": sticks,
            "mhz": max(speeds) if speeds else None, "form": form}


def is_relevant(item: dict, cfg: dict | None) -> bool:
    """Whether a listing belongs in its category. Used when storing and again
    when rendering, so filter edits take effect without a rescrape."""
    if cfg is None:
        return False

    title = (item.get("title") or "").lower()
    if not title:
        return False

    if any(kw in title for kw in GLOBAL_EXCLUDE):
        return False

    for group in cfg.get("require_groups", []):
        if not any(kw in title for kw in group):
            return False

    if any(kw in title for kw in cfg.get("exclude_any", [])):
        return False

    # For rules a substring cannot express, such as word boundaries.
    if any(re.search(p, title, re.IGNORECASE) for p in cfg.get("exclude_regex", [])):
        return False

    floor = cfg.get("min_price")
    if floor and (item.get("price") or 0) < floor:
        return False

    capacity_floor = cfg.get("min_capacity_gb")
    if capacity_floor and max_capacity_gb(title) < capacity_floor:
        return False

    return True

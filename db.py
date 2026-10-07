"""SQLite storage and the view model the dashboard renders.

Price points are stored only when a price actually changes, which keeps the
database small and makes "previous price" a trivial lookup rather than a diff
against a wall of identical daily rows.
"""

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    pid         TEXT PRIMARY KEY,
    source      TEXT NOT NULL DEFAULT 'flipkart',
    category    TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    image       TEXT,
    rating      REAL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_points (
    pid          TEXT NOT NULL,
    ts           TEXT NOT NULL,
    price        INTEGER NOT NULL,
    mrp          INTEGER,
    discount_pct INTEGER,
    PRIMARY KEY (pid, ts)
);

CREATE INDEX IF NOT EXISTS idx_price_points_pid_ts ON price_points(pid, ts);

CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    category TEXT NOT NULL,
    items    INTEGER NOT NULL,
    note     TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_ago(**kwargs) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    """Bring an older database up to the current shape without losing history."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
    if "source" not in columns:
        # Everything recorded before multi-retailer support came from Flipkart.
        conn.execute("ALTER TABLE products ADD COLUMN source TEXT "
                     "NOT NULL DEFAULT 'flipkart'")
        conn.commit()


def record_run(conn, category: str, items: int, note: str = "") -> None:
    conn.execute(
        "INSERT INTO runs (ts, category, items, note) VALUES (?, ?, ?, ?)",
        (now_iso(), category, items, note),
    )
    conn.commit()


def save_items(conn, category: str, items: list[dict], source: str) -> dict:
    """Upsert products and append a price point only where the price moved."""
    ts = now_iso()
    stats = {"new": 0, "changed": 0, "unchanged": 0}

    for it in items:
        pid = it["pid"]
        existing = conn.execute(
            "SELECT pid, first_seen FROM products WHERE pid = ?", (pid,)
        ).fetchone()

        if existing is None:
            conn.execute(
                """INSERT INTO products
                   (pid, source, category, title, url, image, rating,
                    first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, source, category, it.get("title"), it.get("url"),
                 it.get("image"), it.get("rating"), ts, ts),
            )
            stats["new"] += 1
        else:
            conn.execute(
                """UPDATE products
                   SET last_seen = ?, title = COALESCE(?, title),
                       url = COALESCE(?, url), image = COALESCE(?, image),
                       rating = COALESCE(?, rating), category = ?, source = ?
                   WHERE pid = ?""",
                (ts, it.get("title"), it.get("url"), it.get("image"),
                 it.get("rating"), category, source, pid),
            )

        last = conn.execute(
            "SELECT price FROM price_points WHERE pid = ? ORDER BY ts DESC LIMIT 1",
            (pid,),
        ).fetchone()

        if last is None or last["price"] != it["price"]:
            conn.execute(
                """INSERT OR REPLACE INTO price_points
                   (pid, ts, price, mrp, discount_pct) VALUES (?, ?, ?, ?, ?)""",
                (pid, ts, it["price"], it.get("mrp"), it.get("discount_pct")),
            )
            if last is not None:
                stats["changed"] += 1
        else:
            stats["unchanged"] += 1

    conn.commit()
    return stats


def build_rows(conn) -> list[dict]:
    """Assemble the per-product view model the dashboard renders.

    Everything still under tracking is returned, including listings that have
    gone quiet, each tagged with `stale`. The deal panels drop stale rows; the
    tracked-items view can show them, which is the point of keeping them here.
    """
    stale_cutoff = iso_ago(hours=config.STALE_AFTER_HOURS)
    window_cutoff = iso_ago(days=config.HISTORY_WINDOW_DAYS)

    products = conn.execute(
        "SELECT * FROM products WHERE last_seen >= ? ORDER BY category, title",
        (window_cutoff,),
    ).fetchall()
    if not products:
        return []

    pids = {p["pid"] for p in products}

    history = defaultdict(list)
    for row in conn.execute(
        "SELECT pid, ts, price, mrp, discount_pct FROM price_points ORDER BY pid, ts"
    ):
        if row["pid"] in pids:
            history[row["pid"]].append(dict(row))

    rows = []
    for p in products:
        points = history.get(p["pid"])
        if not points:
            continue

        latest = points[-1]
        price = latest["price"]
        mrp = latest["mrp"]
        badge = latest["discount_pct"]

        # Re-checked here, not just at scrape time, so tightening a category
        # filter drops old listings off the dashboard straight away while their
        # price history stays in the database.
        cfg = config.CATEGORIES.get(p["category"])
        if not config.is_relevant({"title": p["title"], "price": price}, cfg):
            continue

        # Only storage gets a capacity; the dashboard uses it for price per TB.
        # Decimal units, as drives are sold, so "1000 GB" and "1 TB" compare equal.
        capacity = (config.max_capacity_gb(p["title"] or "", gb_per_tb=1000)
                    if config.is_storage(cfg) else 0)
        # Form factor keeps comparisons like-for-like: internal vs external
        # drives, desktop vs laptop RAM.
        ram = config.ram_spec(p["title"] or "") if config.is_ram(cfg) else {}
        form = (config.drive_form(p["title"] or "") if config.is_storage(cfg)
                else ram.get("form"))

        prev = points[-2]["price"] if len(points) >= 2 else None
        drop_abs = (prev - price) if prev and prev > price else None
        drop_pct = round(drop_abs / prev * 100, 1) if drop_abs else None

        all_prices = [pt["price"] for pt in points]
        # Carry the last price set before the window into the window minimum,
        # otherwise a long-unchanged price looks like it has no history.
        in_window = [pt["price"] for pt in points if pt["ts"] >= window_cutoff]
        before = [pt["price"] for pt in points if pt["ts"] < window_cutoff]
        if before:
            in_window.append(before[-1])
        window_min = min(in_window) if in_window else price
        window_max = max(in_window) if in_window else price

        suspicious = bool(mrp and price and mrp >= config.SUSPICIOUS_MRP_RATIO * price)

        first_seen = datetime.fromisoformat(p["first_seen"])
        days_tracked = max(0, (datetime.now(timezone.utc) - first_seen).days)

        rows.append({
            "pid": p["pid"],
            "source": p["source"],
            "category": p["category"],
            "title": p["title"] or "(no title)",
            "url": p["url"],
            "image": p["image"],
            "rating": p["rating"],
            "price": price,
            "capacity_gb": capacity or None,
            "form": form,
            "ram_gb": ram.get("gb"),
            "ram_sticks": ram.get("sticks"),
            "ram_mhz": ram.get("mhz"),
            "mrp": mrp,
            "badge_pct": badge,
            "prev_price": prev,
            "drop_abs": drop_abs,
            "drop_pct": drop_pct,
            "window_min": window_min,
            "window_max": window_max,
            "is_low": price <= min(all_prices),
            "suspicious_mrp": suspicious,
            "days_tracked": days_tracked,
            "observations": len(points),
            "last_seen": p["last_seen"],
            "first_seen": p["first_seen"],
            "stale": p["last_seen"] < stale_cutoff,
            "spark": [pt["price"] for pt in points[-30:]],
        })

    return rows


def tracking_stats(conn) -> dict:
    first_run = conn.execute("SELECT MIN(ts) AS t FROM runs").fetchone()["t"]
    run_count = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
    product_count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    point_count = conn.execute("SELECT COUNT(*) AS c FROM price_points").fetchone()["c"]

    days = 0
    if first_run:
        days = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(first_run)).days)

    return {
        "first_run": first_run,
        "days_tracking": days,
        "runs": run_count,
        "products": product_count,
        "price_points": point_count,
        "generated": now_iso(),
    }

"""Entry point: scrape, store, regenerate the dashboard.

    python run.py                      # every site and category, then rebuild
    python run.py --sites amazon       # just one retailer
    python run.py --categories gpu,cpu # just those two
    python run.py --pages 5            # go deeper per category
    python run.py --headful            # watch the browser work
    python run.py --dashboard-only     # rebuild the page from stored data
"""

import argparse
import sys
from datetime import datetime

import config
import dashboard
import db

# The Windows console defaults to cp1252, which raises on the rupee sign and on
# accented characters that show up in product titles.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str = "") -> None:
    if msg:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)
    else:
        print(flush=True)


def pick_categories(spec: str | None) -> dict:
    if not spec:
        return config.CATEGORIES
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    unknown = [k for k in keys if k not in config.CATEGORIES]
    if unknown:
        valid = ", ".join(config.CATEGORIES)
        sys.exit(f"Unknown category: {', '.join(unknown)}. Valid keys: {valid}")
    return {k: config.CATEGORIES[k] for k in keys}


def pick_sites(spec: str | None) -> list[str]:
    import sites
    if not spec:
        return list(config.ENABLED_SITES)
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    unknown = [k for k in keys if k not in sites.SITES]
    if unknown:
        valid = ", ".join(sites.SITES)
        sys.exit(f"Unknown site: {', '.join(unknown)}. Valid keys: {valid}")
    return keys


def preview(rows: list[dict]) -> None:
    drops = sorted(
        (r for r in rows if r["drop_pct"] is not None),
        key=lambda r: r["drop_pct"], reverse=True,
    )[:5]
    badges = sorted(
        (r for r in rows if r["badge_pct"] is not None and not r["suspicious_mrp"]),
        key=lambda r: r["badge_pct"], reverse=True,
    )[:5]

    tag = lambda r: f"{r.get('source', '?')[:4].upper():<4}"

    log()
    if drops:
        log("Biggest real drops since last check:")
        for r in drops:
            log(f"   {tag(r)} -{r['drop_pct']:>5}%  Rs.{r['price']:>7,}  "
                f"(was {r['prev_price']:,})  {r['title'][:52]}")
    else:
        log("No real price drops recorded yet - needs more scheduled runs to build history.")

    log()
    log("Top badge discounts (inflated-MRP listings excluded):")
    for r in badges:
        log(f"   {tag(r)}  {r['badge_pct']:>4}%  Rs.{r['price']:>7,}  {r['title'][:52]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Flipkart PC hardware deal tracker")
    ap.add_argument("--categories", help="comma separated, e.g. gpu,cpu,monitor")
    ap.add_argument("--sites", help="comma separated, e.g. flipkart,amazon "
                                    f"(default: {','.join(config.ENABLED_SITES)})")
    ap.add_argument("--pages", type=int, default=config.MAX_PAGES,
                    help=f"result pages per category (default {config.MAX_PAGES})")
    ap.add_argument("--headful", action="store_true", help="show the browser window")
    ap.add_argument("--open", dest="open_after", action="store_true",
                    help="open the dashboard when finished")
    ap.add_argument("--dashboard-only", action="store_true",
                    help="skip scraping, just rebuild the page from stored data")
    args = ap.parse_args()

    conn = db.connect()

    if not args.dashboard_only:
        try:
            import scraper
        except ImportError:
            sys.exit("Playwright is not installed. Run:\n"
                     "  pip install -r requirements.txt\n"
                     "  python -m playwright install chromium")

        import sites

        categories = pick_categories(args.categories)
        site_keys = pick_sites(args.sites)
        log(f"Scraping {len(site_keys)} site(s) x {len(categories)} categories, "
            f"{args.pages} page(s) each")

        results = scraper.scrape(
            site_keys, categories, args.pages, headless=not args.headful, log=log
        )

        total = 0
        for site_key, per_category in results.items():
            label = sites.SITES[site_key]["label"]
            site_total = 0
            for key, items in per_category.items():
                stats = db.save_items(conn, key, items, site_key)
                db.record_run(conn, key, len(items), note=site_key)
                site_total += len(items)
                log(f"  {label} / {config.CATEGORIES[key]['label']}: "
                    f"{len(items)} items ({stats['new']} new, "
                    f"{stats['changed']} price changes)")
            log(f"  {label} total: {site_total} listings")
            total += site_total

        log(f"Scrape complete: {total} listings")
        if total == 0:
            log("! Nothing was extracted. The markup may have changed, or the "
                "run was blocked. Try --headful to see what the page shows.")

    rows = db.build_rows(conn)
    stats = db.tracking_stats(conn)
    path = dashboard.render(rows, stats)

    preview(rows)
    log()
    log(f"Dashboard written to {path}")

    if args.open_after:
        import webbrowser
        webbrowser.open(config.DASHBOARD_PATH.as_uri())


if __name__ == "__main__":
    main()

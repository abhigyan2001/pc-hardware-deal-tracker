"""Report whether each retailer is actually reachable from wherever this runs.

Cloud runners use datacenter IP ranges, which Flipkart and especially Amazon
treat very differently from home broadband. Run this on a new host before
trusting a hosted setup, and run it again if a scheduled run starts coming back
empty - it separates "we are blocked" from "the markup changed".

Exits non-zero if any retailer is unusable, so CI shows it clearly.
"""

import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

import config
import scraper
import sites

PROBE_CATEGORY = "monitor"


def check(page, site_key: str, site: dict, cfg: dict) -> dict:
    query = (cfg.get(f"queries_{site_key}") or cfg["queries"])[0]
    url = site["search_url"](query, 1)
    out = {"label": site["label"], "blocked": False, "parsed": 0,
           "kept": 0, "error": None}

    print(f"  checking {site['label']}: {url}", flush=True)
    try:
        page.goto(url, timeout=config.PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        page.keyboard.press("Escape")

        out["blocked"] = bool(page.evaluate(site["blocked_js"]))
        if out["blocked"]:
            return out

        page.wait_for_selector(site["wait_selector"], timeout=20_000)
        page.evaluate(scraper.AUTOSCROLL_JS)
        found = page.evaluate(site["extract_js"])
        out["parsed"] = len(found)
        out["kept"] = sum(1 for item in found if config.is_relevant(item, cfg))
    except PlaywrightTimeout:
        # A block page has no results either, so distinguish the two.
        out["blocked"] = bool(page.evaluate(site["blocked_js"]))
        if not out["blocked"]:
            out["error"] = "timed out waiting for results"
    except Exception as exc:  # noqa: BLE001 - report anything, never crash
        out["error"] = str(exc)[:200]
    return out


def main() -> int:
    cfg = config.CATEGORIES[PROBE_CATEGORY]
    config.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    print(f"Probing retailer access using the '{cfg['label']}' category.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_PROFILE_DIR),
            headless=True,
            user_agent=scraper.USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            for key in config.ENABLED_SITES:
                results.append(check(page, key, sites.SITES[key], cfg))
        finally:
            context.close()

    usable = True
    print("\n" + "=" * 64)
    for r in results:
        if r["blocked"]:
            verdict = "BLOCKED - served a CAPTCHA or block page"
            usable = False
        elif r["error"]:
            verdict = f"ERROR - {r['error']}"
            usable = False
        elif r["kept"] == 0:
            verdict = (f"REACHABLE, but kept 0 of {r['parsed']} parsed "
                       f"- filters or markup, not a block")
        else:
            verdict = f"OK - parsed {r['parsed']}, kept {r['kept']}"
        print(f"  {r['label']:<10} {verdict}")
    print("=" * 64 + "\n")

    if usable:
        print("Both retailers are reachable from here. A hosted setup should work.")
        return 0

    print("At least one retailer is not usable from this host.")
    print("If this is a cloud runner, the datacenter IP is the most likely")
    print("cause - these sites treat home connections very differently. Options:")
    print("  - keep scraping locally on a machine with a home connection, or")
    print("  - host only the retailer that still works, or")
    print("  - scrape less often and see whether the block is rate-related.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Generic scraping driver.

Everything retailer-specific - search URLs, card extraction, block detection -
lives in sites.py. This module only drives the browser and applies the shared
relevance rules from config.py.
"""

import random
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

import config
import sites

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

AUTOSCROLL_JS = r"""
async () => {
  await new Promise((resolve) => {
    let y = 0;
    const step = () => {
      window.scrollBy(0, 900);
      y += 900;
      if (y >= document.body.scrollHeight || y > 25000) { resolve(); return; }
      setTimeout(step, 150);
    };
    step();
  });
}
"""


def _polite_pause() -> None:
    time.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY))


def scrape_category(page, site_key: str, site: dict, cfg: dict,
                    max_pages: int, log) -> list[dict]:
    """Run every query for one category on one site, merged by product id."""
    collected: dict[str, dict] = {}
    queries = cfg.get(f"queries_{site_key}") or cfg["queries"]

    for q_index, query in enumerate(queries):
        log(f'    query "{query}"')

        for page_no in range(1, max_pages + 1):
            url = site["search_url"](query, page_no)
            try:
                page.goto(url, timeout=config.PAGE_TIMEOUT_MS,
                          wait_until="domcontentloaded")
                page.keyboard.press("Escape")  # dismisses login interstitials

                if page.evaluate(site["blocked_js"]):
                    raise sites.SiteBlocked(
                        f"{site['label']} served a block/CAPTCHA page")

                page.wait_for_selector(site["wait_selector"], timeout=20_000)
                page.evaluate(AUTOSCROLL_JS)
                page.evaluate("() => window.scrollTo(0, 0)")
                found = page.evaluate(site["extract_js"])
            except sites.SiteBlocked:
                raise
            except PlaywrightTimeout:
                # A block page has no results either, so re-check before
                # blaming the timeout on a slow page.
                if page.evaluate(site["blocked_js"]):
                    raise sites.SiteBlocked(
                        f"{site['label']} served a block/CAPTCHA page")
                log(f"      page {page_no}: timed out; skipping")
                continue
            except Exception as exc:  # noqa: BLE001 - one bad page can't kill the run
                log(f"      page {page_no}: error: {exc}")
                continue

            if len(found) < config.MIN_ITEMS_PER_PAGE_BEFORE_WARNING:
                log(f"      ! only {len(found)} items parsed on page {page_no}. "
                    f"Either this query is thin or the markup changed.")

            kept = [item for item in found if config.is_relevant(item, cfg)]
            for item in kept:
                collected.setdefault(item["pid"], item)

            log(f"      page {page_no}: parsed {len(found)}, kept {len(kept)}; "
                f"category total {len(collected)}")

            is_last = (q_index == len(queries) - 1) and (page_no == max_pages)
            if not is_last:
                _polite_pause()

    return list(collected.values())


def scrape(site_keys: list[str], categories: dict, max_pages: int,
           headless: bool, log=print) -> dict[str, dict[str, list[dict]]]:
    """Scrape every category on every site. Returns {site: {category: items}}."""
    results: dict[str, dict[str, list[dict]]] = {}
    config.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_PROFILE_DIR),
            headless=headless,
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for s_index, site_key in enumerate(site_keys):
                site = sites.SITES[site_key]
                results[site_key] = {}
                log(f"=== {site['label']} ===")

                for i, (key, cfg) in enumerate(categories.items()):
                    log(f"  [{cfg['label']}]")
                    try:
                        results[site_key][key] = scrape_category(
                            page, site_key, site, cfg, max_pages, log)
                    except sites.SiteBlocked as exc:
                        # Stop this retailer for the run rather than hammering a
                        # site that has explicitly asked us to stop.
                        log(f"  ! {exc}. Skipping the rest of {site['label']} "
                            f"for this run; previously stored data is kept.")
                        break
                    if i < len(categories) - 1:
                        _polite_pause()

                if s_index < len(site_keys) - 1:
                    _polite_pause()
        finally:
            context.close()

    return results

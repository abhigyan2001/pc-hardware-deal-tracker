# PC Hardware Deal Tracker

Records a price history for a narrow set of PC hardware on **Flipkart and
Amazon.in**, and renders a dashboard with two rankings per retailer.

The retailers are kept strictly separate: the dashboard has a tab per site and
shows one at a time, never a merged list. Category rules are shared, since they
describe the product rather than the shop.

(The folder is still named `flipkart-deal-tracker` because the desktop shortcut
and any scheduled task point at this path.)

| Category | Scope tracked |
| --- | --- |
| Monitors | 4K / OLED 4K / 1440p only (no Full HD) |
| RAM | DDR5 only |
| SSD | 512 GB and larger |
| HDD | 512 GB and larger |
| Processors | AM5 socket only (Ryzen 7000 / 8000 / 9000) |
| Graphics Cards | all |
| Liquid Coolers | all (AIO / liquid, not room coolers) |

## The one thing worth understanding

Flipkart's struck-through "MRP" is frequently fictional, especially on no-name
brands. A listing claiming 78% off is usually a fake MRP, not a deal. So the
dashboard never merges the two signals:

- **Real price drops** (left panel) compares each price against *this tracker's
  own recorded history*. This is the signal worth acting on. It is empty on day
  one and becomes useful after roughly a week of scheduled runs.
- **Flipkart badge discounts** (right panel) mirrors what Flipkart claims off its
  own MRP. Rows where the claimed MRP is >= 2.5x the selling price are flagged
  `check MRP`. Useful as a starting point, but treat it with suspicion.

## Usage

```
.venv\Scripts\python.exe run.py                      # every site and category
.venv\Scripts\python.exe run.py --sites amazon       # one retailer only
.venv\Scripts\python.exe run.py --categories gpu,cpu # only those
.venv\Scripts\python.exe run.py --pages 5            # dig deeper per category
.venv\Scripts\python.exe run.py --headful            # watch the browser work
.venv\Scripts\python.exe run.py --dashboard-only     # rebuild page from stored data
.venv\Scripts\python.exe run.py --open               # open the dashboard when done
```

Retailers are listed in `ENABLED_SITES` in `config.py`. Removing one stops it
being scraped but keeps its stored history, and its tab stays on the dashboard.

The dashboard is written to `data/dashboard.html`. It embeds its own data, so
just open it in a browser - **no server needs to be running**. There is a
desktop shortcut, "Flipkart Deals", that opens it directly.

To refresh the numbers and open it in one step:

```
.venv\Scripts\python.exe run.py --open
```

## Using the dashboard

The top row of tabs picks the retailer, with a count of what is tracked there.
Switching sites swaps the whole page over: filters, rankings and the tracked
table all show that retailer only. Everything below applies within the selected
site.

Two views, switched under the retailer tabs:

- **Deals** - the two ranked panels described above.
- **Tracked items** - everything under tracking, as a table: current price,
  badge, last drop, lowest price seen, number of observations, and when each
  item was first and last seen. This is where to look for items that are being
  tracked but are not currently discounted, so appear in neither deal panel.

Controls apply to both views:

- **Sort** - panel default, price (low/high), real drop % or &#8377;, badge
  discount %, or most recently seen. Price sorts use the after-offer price when
  an offer is set.
- **Filters** - text search, category, min/max price, minimum discount %, hide
  inflated-MRP listings, and show/hide stale items (not seen in 48 hours).
  Category chips show how many items match the current filters.
- **Bank / coupon offer** - enter a percentage, an optional cap, and an optional
  flat amount, and every row shows what it would actually cost:
  `10% off capped at ₹1,500` turns a ₹33,999 SSD into ₹32,499 and a ₹12,578
  monitor into ₹11,320. Sorting by price then ranks on that effective price.
- **Storage** (SSD / HDD) - every drive shows its price per TB, and the
  cheapest SSD and cheapest HDD under the current filters are named side by
  side. Set a **target** (in TB or GB) and each drive also shows how many you
  would need and what they cost in total, e.g. a 4 TB target from 1 TB drives
  is `4 × = ₹21,596`. Sort by **Storage ₹ per TB** or **Storage total for
  target** to rank them. Capacity is read from the listing title in drive-maker
  units (1 TB = 1000 GB), and both respect any offer you have set. A drive type
  filter shows internal drives, external/portable ones, or both, and external
  drives carry a tag so they are not mistaken for internal ones in a ranking.
- **RAM** - every listing shows its price per GB of the whole kit, so a 2x16 GB
  kit and a 1x32 GB stick compare directly, along with its kit layout and rated
  speed. Filter to desktop or laptop (SO-DIMM) memory, single sticks or 2-stick
  kits, and a minimum speed, then sort by **RAM ₹ per GB**. A title with no kit
  marker is taken as one stick, and a listing that states no speed is hidden
  when a minimum speed is set.

Settings persist in the browser's local storage, so they survive a dashboard
regeneration. **Reset** clears them.

## Scheduling

`run_tracker.bat` pins the working directory and venv, and appends output to
`data/tracker.log`. To run it every 6 hours:

```
schtasks /Create /TN "Flipkart Deal Tracker" /TR "C:\Users\rajsn\IdeaProjects\flipkart-deal-tracker\run_tracker.bat" /SC HOURLY /MO 6 /IT /F
```

`/IT` runs it only while you are logged on, which avoids the session-0 problems
a headless browser hits when run as a detached service. Remove the task with:

```
schtasks /Delete /TN "Flipkart Deal Tracker" /F
```

`data/tracker.log` grows unbounded; delete it occasionally.

## Tuning the category filters

Flipkart search is noisy. "graphics card" returns mini vacuum cleaners and VR
headsets; "monitor" returns baby monitors; "liquid cooler" returns room coolers.
Worse, sellers list drones under Graphics Cards with keyword-stuffed titles like
`Auronix E88 Pro 4K Drone ... NVIDIA Chipset 0 bit 2.4 MHz Graphics Card`, which
no per-category keyword rule can catch.

So `config.py` has these layers:

- `GLOBAL_EXCLUDE` - product types that are never wanted in any category
  (drones, gimbals, smartwatches...). This is what catches the keyword stuffers.
- `queries` - each category runs several searches, merged by product id.
  Narrow queries beat deep paging: they put the right listings on page one.
- `require_groups` - a list of keyword groups. A title must match at least one
  keyword in **every** group, which lets conditions be ANDed. A monitor must be
  a monitor *and* be 4K or 1440p; a flat keyword list cannot express that.
- `exclude_any` and `min_price` - per category.
- `min_capacity_gb` - compares the largest capacity named in the title, so
  `1 TB` clears a 512 floor and `500 GB` does not.

Two notes on the rules as written:

- **AM5 is matched by model family, not the word "AM5".** Most listings say
  "AMD Ryzen 5 7600X"; requiring the literal string would return almost nothing.
  Matching the 7000/8000/9000 families also excludes AM4 parts like the 5600X
  without listing them. (Flipkart does usually spell out "AM5 Socket" in CPU
  titles, so that is matched too, but it is not relied on alone.)
- **Bare "2K" is deliberately not a monitor resolution keyword.** It
  false-positives on model numbers, and listings meaning 1440p say QHD.

Every run prints how many items each query kept (`parsed 40, kept 22`). If a
category keeps very few items, loosen its rules; if junk appears, add a term. A
category showing `kept 0` usually means titles are not matching a
`require_groups` entry. Watch for queries that add nothing - two of the CPU
queries were dropped after the log showed they found no products the broad
query had not already returned.

Relevance is applied twice: when storing, and again when building the
dashboard. So tightening a filter hides stale listings on the next
`--dashboard-only` rebuild, with no rescrape and without deleting the price
history you would need if you loosen the filter again later. Anything that stops
being scraped also ages off after `STALE_AFTER_HOURS` (48).

## When it breaks

Retailer-specific extraction lives in `sites.py`; `scraper.py` only drives the
browser. The two sites fail in different ways.

**Flipkart** is the fragile one. Its CSS class names are obfuscated and rotate,
so nothing keys on them. Extraction groups anchors by their `pid` (the stable
product id in the URL - the rest of the query string is per-request tracking
junk) and reads prices from elements whose entire text is a rupee amount.
Flipkart serves at least two result layouts and both are handled: the grid puts
the product name in a `title` attribute, the list layout renders it as a bare
leaf div. If a run reports very few parsed items, or titles come back empty,
the markup has probably changed.

**Amazon** is easier to parse - each result is one container tagged with a
`data-asin`, and the ASIN is a stable id needing no cleanup - but it is much
quicker to block automated traffic. When it serves a CAPTCHA or block page the
scraper detects it, logs it, and **stops that retailer for the rest of the run**
rather than retrying. Stored history is untouched, and Flipkart still runs. This
tool does not try to work around a block; if it happens repeatedly, scrape
Amazon less often. Amazon does have an official Product Advertising API, but it
requires an affiliate account with qualifying sales.

Ids cannot collide between the two: Flipkart pids are 16 characters, ASINs are
10, so both share one key space safely.

Run with `--headful` to watch either site, and check `sites.py` for extraction.

## Scope and etiquette

This is a personal tracker. It walks a few pages per category a few times a day
with real delays between requests, which is ordinary price-tracking behaviour,
but it is still scraping rather than an official API. Flipkart's affiliate API
has been closed to new signups for years; Amazon's requires an affiliate account
with qualifying sales. Both sites' terms discourage scraping, and Amazon
enforces that far more actively.

Adding a second retailer roughly doubles the request volume per run, so keep
`MAX_PAGES` and the schedule modest, don't redistribute the data, and if Amazon
starts returning block pages, back off rather than trying to get around it.

## Running it in the cloud (GitHub Actions)

Two workflows are included. **Run the probe before trusting the scheduled one.**

### 1. Probe first

The thing most likely to break a hosted setup is not the hosting, it is the IP
address. Flipkart and especially Amazon treat datacenter ranges very differently
from home broadband, and this repo runs fine locally partly because it scrapes
from a residential connection.

So: push the repo, open **Actions -> Probe retailer access -> Run workflow**.
It scrapes one category on each retailer and prints a verdict per site. The same
check runs locally:

```
.venv\Scripts\python.exe check_access.py
```

A failure there means a retailer is unreachable from CI, not that the code is
broken. If Amazon blocks but Flipkart does not, set
`ENABLED_SITES = ["flipkart"]` in `config.py` and keep Amazon running locally.

### 2. Then enable the schedule

`Track prices` runs every 6 hours (05:30, 11:30, 17:30, 23:30 IST) and can also
be triggered by hand. GitHub's scheduler is best-effort and often late under
load, which is fine for this.

Actions minutes are unlimited on public repositories, so frequency is not
limited by cost here. The limit that matters is politeness: each run is roughly
60 page loads across two retailers, and scraping harder is how you get blocked.
Four runs a day is already more than enough to catch real price moves.

Nothing needs doing by hand. The schedule scrapes, commits the updated history,
and redeploys the page on its own.

### How the data survives

CI runners start from an empty filesystem, so `data/prices.db` is committed back
to the repo after every run. Without that the price history - the entire point of
the tool - would silently reset on each run while everything still looked fine.

`actions/cache` is deliberately not used for the database: cache entries are
evicted after 7 days without a hit, which would quietly destroy the history.

This also keeps the repo active, which stops GitHub disabling scheduled
workflows after 60 days of inactivity.

Two consequences worth knowing:

- **Don't run the scraper locally and in CI at the same time.** Both write the
  same database and git cannot merge a binary file. Either let CI own it, or
  `git pull` before running locally and push afterwards.
- **The repo grows, slowly.** Measured over five simulated runs, git stores
  about 281 KB of objects, roughly 57 KB per run, so near enough 40 MB a year at
  two runs a day. Fine for years.

The database is committed **raw**. Two plausible-sounding optimisations were
measured and both lose:

| Stored as | File on disk | Git objects, 5 runs |
| --- | --- | --- |
| raw `.db` | 720 KB | **281 KB** |
| gzipped `.db.gz` | 171 KB | 945 KB |
| SQL text dump | 588 KB | 232 KB |

Gzip makes the file four times smaller and the repository three times bigger.
Git already zlib-compresses blobs, so compressing first gains almost nothing,
and compressed bytes change wholesale on any edit so git cannot delta them -
every run stores a complete new blob instead of a small diff. The SQL text dump
wins only 18%, which does not pay for a restore step that could lose history.

`dashboard.html` is not committed at all. It is regenerated from the database on
every run, so versioning it would add roughly as much again for nothing.

### Seeing the dashboard

The workflow publishes `dashboard.html` to **GitHub Pages** after every run, so
the site is always as fresh as the last scrape. No commit of the HTML is
involved - it is staged as `_site/index.html` and deployed straight from the run.

This repository is **public**, which is what makes Pages free. That does mean the
scraped prices and the list of tracked products are visible to anyone. If you
later want it private, GitHub Pages for private repos needs a paid plan;
Cloudflare Pages serves private repos for free instead.

Locally, the desktop shortcut opens `data/dashboard.html` directly, which needs
no server and works offline.

## Possible next steps

- A watchlist: flag 10-20 specific parts you are actually shopping for and check
  those more often, with an alert on a real drop.
- Email or push notification when a tracked product hits an all-time low.

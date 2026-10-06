"""Per-retailer definitions: how to search, how to read a result card, and how
to tell when the site has blocked us.

Everything site-specific lives here so the scraper driver stays generic.

A note on product ids: Flipkart pids are 16 characters and Amazon ASINs are 10,
so they cannot collide and both can share one `pid` key in the database.
"""

from urllib.parse import quote_plus

# --------------------------------------------------------------------------
# Flipkart
# --------------------------------------------------------------------------
# Each product is rendered as several sibling anchors - image, title, price -
# that all carry the same pid, so anchors are grouped by pid and merged rather
# than hunting for one enclosing card. Class names are obfuscated and rotate,
# so nothing keys on them. Prices are read from whole elements whose text is
# exactly a rupee amount, never from concatenated textContent: Flipkart renders
# "4,211" and "6,000" and "29% off" in adjacent nodes, and the naive reading
# glues them into a bogus MRP of 600029.

FLIPKART_EXTRACT_JS = r"""
() => {
  const PRICE_RE  = /^₹\s*[\d,]+$/;
  const OFF_RE    = /^(\d{1,3})\s*%\s*off$/i;
  const RATING_RE = /^[0-5]\.[0-9]$/;

  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // Flipkart serves at least two result layouts. The grid puts the product name
  // in a title attribute; the list layout has no title attribute and renders the
  // name as a bare leaf div, so a text fallback is needed too.
  const looksLikeName = (t) =>
    t.length >= 12 && t.length <= 300 &&
    t.indexOf('₹') === -1 &&
    !/%\s*off/i.test(t) &&
    !/^\d[\d,.]*$/.test(t) &&
    !/\bratings?\b/i.test(t) &&
    !/\breviews?\b/i.test(t) &&
    !/^(add to compare|compare|sponsored|ad)\b/i.test(t);

  const deepestMatches = (root, test) => {
    const all = Array.from(root.querySelectorAll('*'))
      .filter(el => test((el.textContent || '').trim()));
    return all.filter(el => !all.some(other => other !== el && el.contains(other)));
  };

  const byPid = new Map();

  for (const a of document.querySelectorAll('a[href*="/p/"]')) {
    const href = a.getAttribute('href') || '';
    const pidMatch = href.match(/[?&]pid=([A-Za-z0-9]+)/i);
    if (!pidMatch) continue;
    const pid = pidMatch[1];

    let rec = byPid.get(pid);
    if (!rec) {
      rec = { pid: pid, title: '', altTitle: '', url: '', image: '',
              prices: [], discount_pct: null, rating: null };
      byPid.set(pid, rec);
    }

    if (!rec.url) {
      let path;
      try { path = new URL(href, location.origin).pathname; }
      catch (e) { path = href.split('?')[0]; }
      rec.url = 'https://www.flipkart.com' + path + '?pid=' + pid;
    }

    const attrTitle = clean(a.getAttribute('title'));
    if (attrTitle.length > rec.title.length) rec.title = attrTitle;

    for (const el of a.querySelectorAll('*')) {
      if (el.children.length) continue;
      const t = clean(el.textContent);
      if (looksLikeName(t) && t.length > rec.altTitle.length) rec.altTitle = t;
    }

    if (!rec.image) {
      const img = a.querySelector('img');
      if (img) rec.image = img.getAttribute('src') || '';
    }

    if (!rec.prices.length) {
      const vals = deepestMatches(a, t => PRICE_RE.test(t))
        .map(el => parseInt(el.textContent.replace(/[^\d]/g, ''), 10))
        .filter(v => Number.isFinite(v) && v > 0);
      if (vals.length) rec.prices = vals;
    }

    if (rec.discount_pct === null) {
      const hit = deepestMatches(a, t => OFF_RE.test(t))[0];
      if (hit) rec.discount_pct = parseInt(hit.textContent.trim().match(OFF_RE)[1], 10);
    }

    if (rec.rating === null) {
      const hit = deepestMatches(a, t => RATING_RE.test(t))[0];
      if (hit) rec.rating = parseFloat(hit.textContent.trim());
    }
  }

  const out = [];
  for (const rec of byPid.values()) {
    if (!rec.prices.length) continue;
    const price = rec.prices[0];
    let mrp = null;
    for (let i = 1; i < rec.prices.length; i++) {
      if (rec.prices[i] > price) { mrp = rec.prices[i]; break; }
    }
    let discount = rec.discount_pct;
    if (discount === null && mrp) discount = Math.round((mrp - price) / mrp * 100);

    out.push({
      pid: rec.pid,
      title: (rec.title || rec.altTitle).slice(0, 300),
      url: rec.url,
      image: rec.image,
      price: price,
      mrp: mrp,
      discount_pct: discount,
      rating: rec.rating
    });
  }
  return out;
}
"""

FLIPKART_BLOCKED_JS = r"""
() => {
  const t = document.body ? document.body.innerText.slice(0, 3000) : '';
  return /unusual traffic|access denied|are you a robot/i.test(t);
}
"""

# --------------------------------------------------------------------------
# Amazon
# --------------------------------------------------------------------------
# Far friendlier to parse than Flipkart: each result is one container tagged
# with a data-asin attribute, and the ASIN is a stable product id that needs no
# tracking parameters stripped. The product URL is rebuilt from the ASIN rather
# than read from an href, because the title anchor is not always present.

AMAZON_EXTRACT_JS = r"""
() => {
  const out = [];

  const money = (el) => {
    if (!el) return null;
    const v = parseFloat((el.textContent || '').replace(/[^0-9.]/g, ''));
    return Number.isFinite(v) && v > 0 ? Math.round(v) : null;
  };

  const cards = document.querySelectorAll(
    'div[data-asin][data-component-type="s-search-result"]');

  for (const card of cards) {
    const asin = (card.getAttribute('data-asin') || '').trim();
    if (!asin) continue;

    // .a-offscreen holds the screen-reader price, which is the clean one.
    const price = money(card.querySelector('.a-price .a-offscreen'));
    if (!price) continue;

    let mrp = money(card.querySelector('.a-text-price .a-offscreen'));
    if (mrp !== null && mrp <= price) mrp = null;

    const h2 = card.querySelector('h2');
    const title = h2 ? (h2.textContent || '').replace(/\s+/g, ' ').trim() : '';
    if (!title) continue;

    let rating = null;
    const rEl = card.querySelector('i[class*="a-icon-star"] span.a-icon-alt');
    if (rEl) {
      const m = (rEl.textContent || '').match(/([0-5](?:\.[0-9])?)\s*out of/i);
      if (m) rating = parseFloat(m[1]);
    }

    const img = card.querySelector('img.s-image');

    out.push({
      pid: asin,
      title: title.slice(0, 300),
      url: 'https://www.amazon.in/dp/' + asin,
      image: img ? (img.getAttribute('src') || '') : '',
      price: price,
      mrp: mrp,
      discount_pct: mrp ? Math.round((mrp - price) / mrp * 100) : null,
      rating: rating
    });
  }
  return out;
}
"""

AMAZON_BLOCKED_JS = r"""
() => {
  const t = document.body ? document.body.innerText.slice(0, 4000) : '';
  return /Enter the characters you see below|Type the characters you see/i.test(t)
      || /To discuss automated access|not a robot/i.test(t)
      || !!document.querySelector('form[action*="validateCaptcha"]');
}
"""


SITES = {
    "flipkart": {
        "label": "Flipkart",
        "search_url": lambda q, n: (
            f"https://www.flipkart.com/search?q={quote_plus(q)}&page={n}"),
        "wait_selector": 'a[href*="/p/"]',
        "extract_js": FLIPKART_EXTRACT_JS,
        "blocked_js": FLIPKART_BLOCKED_JS,
    },
    "amazon": {
        "label": "Amazon",
        "search_url": lambda q, n: (
            f"https://www.amazon.in/s?k={quote_plus(q)}&page={n}"),
        "wait_selector": 'div[data-component-type="s-search-result"]',
        "extract_js": AMAZON_EXTRACT_JS,
        "blocked_js": AMAZON_BLOCKED_JS,
    },
}


class SiteBlocked(Exception):
    """Raised when a retailer serves a CAPTCHA or block page.

    The run stops for that site rather than retrying. Working around a block is
    not something this tool does.
    """

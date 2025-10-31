#!/usr/bin/env python3
"""
Domain/Subdomain Mapping Extractor with Live Metadata

Enhances domain detection by attempting to fetch the site's homepage and
extract metadata via trafilatura. Falls back to heuristics if network
access fails or metadata is insufficient. Logs fallbacks and CF/antibot
encounters and can optionally route through a local Cloudflare-bypass proxy.

Usage:
  python domain_subdomain_extractor.py -i sitelist.txt [-o mapping.yaml]
    [--timeout 15] [--no-proxy] [--user-agent "..."]

sitelist.txt format:
  # comments allowed with leading '#'
  example.com
  https://www.foodblog.com
  mindoverclutter.ca

Output YAML example:

domain_mapping:
  example.com:
    domain: 'technology'
    subdomain: 'programming'

Notes:
- If heuristics or network fallback is used, an entry is logged under
  dynaclean/logs/domain_extractor_YYYYMMDD_HHMMSS.log
- Default CF-bypass proxy (when needed): http://changeme:changeme@127.0.0.1:1234
"""

import argparse
from pathlib import Path
import sys
import re
import yaml
from typing import Dict, Tuple, List, Optional
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional progress bar
try:
    from tqdm.auto import tqdm  # type: ignore
except Exception:
    tqdm = None

# Network
try:
    import requests
except Exception:
    requests = None  # We will handle absence gracefully

try:
    from trafilatura import fetch_url, extract_metadata
except Exception:
    fetch_url = None
    extract_metadata = None

# Optional HTML parser for head/meta fallback
try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # fallback to regex-lite if unavailable

# Keep heuristics aligned with pipeline
# Expanded keyword taxonomy for better coverage
DOMAIN_KEYWORDS = {
    'food': [
        'recipe', 'recipes', 'cook', 'cooking', 'food', 'cuisine', 'meal', 'meals', 'kitchen', 'bake', 'baking',
        'chef', 'gourmet', 'stove', 'plate', 'healthy', 'nutrition', 'nutritional', 'diet', 'dietary', 'eat', 'eating'
    ],
    'travel': [
        'travel', 'trip', 'vacation', 'tour', 'tourism', 'destination', 'journey', 'adventure', 'itinerary', 'guide'
    ],
    'technology': [
        'tech', 'software', 'hardware', 'computer', 'digital', 'code', 'coding', 'program', 'programming', 'ai', 'data', 'web', 'app'
    ],
    'health': [
        'health', 'fit', 'fitness', 'wellness', 'medical', 'medicine', 'clinic', 'exercise', 'nutrition', 'disease',
        'disorder', 'sleep', 'mental', 'therapy', 'diet', 'healthy'
    ],
    'lifestyle': [
        'life', 'lifestyle', 'living', 'home', 'family', 'personal', 'daily', 'organize', 'organizing', 'declutter', 'decor', 'diy', 'craft', 'crafts'
    ],
    'business': [
        'business', 'finance', 'money', 'invest', 'investment', 'career', 'work', 'market', 'sales', 'management', 'productivity'
    ],
    'entertainment': [
        'entertain', 'movie', 'music', 'game', 'fun', 'celebrity', 'tv', 'film', 'art', 'design', 'photography', 'culture'
    ]
}

SKIP_TOKENS = {
    'www', 'blog', 'site', 'web', 'online', 'news', 'the', 'my'
}

# Generic/non-informative terms to ignore from metadata/head
GENERIC_TERMS = {
    'home', 'homepage', 'about', 'contact', 'welcome', 'start', 'index', 'main', 'archive', 'category', 'tag', 'tags', 'news', 'daily'
}

# Technical/plugin/platform terms that should never influence domain/subdomain
TECH_STOPWORDS = {
    'wp', 'wordpress', 'json', 'api', 'oembed', 'yoast', 'seo', 'kadence', 'elementor', 'jetpack', 'mailerlite', 'aioseo',
    'woocommerce', 'wc', 'cart', 'checkout', 'sitemap', 'manifest', 'robots', 'thumbnail', 'thumbnails', 'featuredimages',
    'webhook', 'webhooks', 'endpoint', 'endpoints', 'v1', 'v2', 'v3', 'schema', 'route', 'routes', 'batch', 'theme', 'plugin',
    'plugins', 'template', 'templates', 'debug', 'graphql', 'rest', 'amp', 'cdn', 'cache', 'minify', 'firebase', 'gtm', 'ga',
    'analytics', 'optimize', 'adthrive', 'mediavine', 'newsletter', 'subscribe', 'login', 'logout', 'admin', 'backend', 'frontend',
    'thumbnailid', 'getfeaturedimageid', 'featuredimage', 'images', 'image', 'media', 'attachment', 'wpforms', 'ninja', 'forms', 'ninjaforms',
    'code', 'app', 'apps', 'technical', 'mapping', 'mappings', 'repair', 'training', 'domain', 'email', 'mail', 'started'
}

TECH_BAD_SUBSTRINGS = [
    'wp-', 'wprm', 'yoast', 'kadence', 'elementor', 'jetpack', 'mailerlite', 'aioseo', 'woocommerce', 'wc/', 'wc_', 'sitemap', 'oembed',
    'wpforms', 'ninja-forms', 'ninja_forms', 'rest', 'api', '/v1', '/v2', '/v3', 'graphql', 'manifest', 'robots', 'thumbnails', 'thumbnail',
]

HINT_WHITELIST = {
    # Food/cooking
    'recipe', 'recipes', 'kitchen', 'cook', 'cooking', 'baking', 'food', 'eat', 'eating', 'meal', 'meals',
    # Travel
    'travel', 'trip', 'vacation', 'tour', 'destination', 'guide', 'itinerary',
    # Lifestyle/home/decor/DIY
    'home', 'decor', 'design', 'diy', 'craft', 'crafts', 'organize', 'organizing', 'clean', 'cleaning', 'garden', 'gardening',
    # Health/fitness
    'health', 'fitness', 'wellness', 'nutrition', 'diet',
    # Business/finance
    'business', 'finance', 'money', 'budget', 'saving', 'savings', 'invest', 'investment',
    # Pets/animals
    'pet', 'pets', 'cat', 'cats', 'dog', 'dogs'
}

# Special-case rules for certain domains/patterns
SPECIAL_DOMAIN_RULES: Dict[str, Dict[str, str]] = {
    # High-confidence mappings
    'myplate.gov': {'domain': 'health', 'subdomain': 'nutrition'},
    'nal.usda.gov': {'domain': 'food', 'subdomain': 'agriculture'},
    'usda.gov': {'domain': 'food', 'subdomain': 'agriculture'},
    'narcolepsynetwork.org': {'domain': 'health', 'subdomain': 'narcolepsy'},
    'natashaskitchen.com': {'domain': 'food', 'subdomain': 'recipes'},
    'mymodernmet.com': {'domain': 'entertainment', 'subdomain': 'art'},
    'mymove.com': {'domain': 'lifestyle', 'subdomain': 'home'},
    'mysocalledcraftylife.com': {'domain': 'lifestyle', 'subdomain': 'crafts'},
    # From user's sample list
    'myfussyeater.com': {'domain': 'food', 'subdomain': 'recipes'},
    'myglobalviewpoint.com': {'domain': 'travel', 'subdomain': 'inspiration'},
    'mygourmetconnection.com': {'domain': 'food', 'subdomain': 'gourmet'},
    'myhomierhome.com': {'domain': 'lifestyle', 'subdomain': 'home'},
    'myindianstove.com': {'domain': 'food', 'subdomain': 'indian'},
    'mykitchenstories.com.au': {'domain': 'food', 'subdomain': 'recipes'},
    'mypathtozero.com': {'domain': 'lifestyle', 'subdomain': 'sustainability'},
    'mypeoplepatterns.com': {'domain': 'business', 'subdomain': 'hr'},
    'nadiashealthykitchen.com': {'domain': 'food', 'subdomain': 'healthy recipes'},
    'napo-gpc.org': {'domain': 'business', 'subdomain': 'organizing'},
    'naswdc.org': {'domain': 'health', 'subdomain': 'social work'},
    'nathab.com': {'domain': 'travel', 'subdomain': 'wildlife'},
    # Specific overrides to improve extraction quality per feedback
    'allthingsthrifty.com': {'domain': 'food', 'subdomain': 'recipe'},
    'ambitiouskitchen.com': {'domain': 'food', 'subdomain': 'ambitiouskitchen'},
    'artsychicksrule.com': {'domain': 'lifestyle', 'subdomain': 'decor'},
    'atlfamilylawgroup.com': {'domain': 'business', 'subdomain': 'family-law'},
    'atomicsmash.co.uk': {'domain': 'technology', 'subdomain': 'website'},
    'bloggizmo.com': {'domain': 'technology', 'subdomain': 'daily'},
    'canadianhometrends.com': {'domain': 'entertainment', 'subdomain': 'design'},
    'cats.com': {'domain': 'travel', 'subdomain': 'guides'},
    'cleaneatingmag.com': {'domain': 'food', 'subdomain': 'eating'},
    'clickbizhub.com': {'domain': 'business', 'subdomain': 'sales tips & deals'},
    'cocolapinedesign.com': {'domain': 'entertainment', 'subdomain': 'design'},
    'cookwithmanali.com': {'domain': 'food', 'subdomain': 'cookwithmanali'},
    'creationsbykara.com': {'domain': 'food', 'subdomain': 'creationsbykara'},
    'cuckoo4design.com': {'domain': 'entertainment', 'subdomain': 'design'},
}

CF_PATTERNS = [
    'cloudflare', 'cf-ray', 'cf_chl_', 'cf-browser-verification',
    'attention required', 'just a moment', 'bot protection'
]

DEFAULT_PROXY = 'http://changeme:changeme@127.0.0.1:1234'
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def setup_logger() -> Path:
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"domain_extractor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger('domain_extractor')
    logger.setLevel(logging.INFO)
    # Avoid duplicate handlers on repeated runs in same interpreter
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return log_file


def normalize_domain(domain: str) -> str:
    if not domain:
        return ''
    d = domain.strip().lower()
    d = re.sub(r'^https?://', '', d)
    d = d.split('/')[0]
    d = d.split(':')[0]
    if d.startswith('www.'):
        d = d[4:]
    return d


def build_url_variants(domain: str) -> List[str]:
    d = normalize_domain(domain)
    variants = [
        f'https://{d}',
        f'https://www.{d}',
        f'http://{d}',
        f'http://www.{d}',
    ]
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for u in variants:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def tokenize_domain(domain: str) -> List[str]:
    name = normalize_domain(domain).split('.')[0]
    tokens = re.split(r'[^a-zA-Z0-9]+', name)
    # also split camelCase or alnum boundaries
    split_tokens: List[str] = []
    for t in tokens:
        if not t:
            continue
        # split by letter-number boundaries
        parts = re.findall(r'[A-Za-z]+|\d+', t)
        for p in parts:
            split_tokens.extend(re.findall(r'[A-Z]?[a-z]+|[0-9]+', p))
    # normalize
    normalized = [s.lower() for s in split_tokens if s and s.lower() not in SKIP_TOKENS]
    return normalized or [name]


def guess_domain_and_sub(tokens: List[str]) -> Tuple[Optional[str], str]:
    # Score domain categories
    scores: Dict[str, int] = {k: 0 for k in DOMAIN_KEYWORDS.keys()}
    for t in tokens:
        for dom, kws in DOMAIN_KEYWORDS.items():
            if any(k in t for k in kws):
                scores[dom] += 1
    # pick best
    best_dom: Optional[str] = None
    best_score = -1
    for dom, sc in scores.items():
        if sc > best_score:
            best_dom, best_score = dom, sc
    # choose subdomain: first meaningful token that matches best domain's keywords if possible
    sub = None
    if best_dom and best_score > 0:
        for t in tokens:
            if any(k in t for k in DOMAIN_KEYWORDS[best_dom]):
                sub = t
                break
    if not sub:
        sub = tokens[0] if tokens else 'general'
    if not best_dom or best_score == 0:
        best_dom = None
    return best_dom, sub


def cf_suspected(text: str) -> bool:
    if not text:
        return False
    lt = text.lower()
    return any(p in lt for p in CF_PATTERNS)


def http_get(url: str, timeout: int, user_agent: str, use_proxy: bool) -> Optional[str]:
    headers = {'User-Agent': user_agent, 'Accept': 'text/html,application/xhtml+xml'}
    proxies = None
    if use_proxy:
        proxies = {
            'http': DEFAULT_PROXY,
            'https': DEFAULT_PROXY,
        }
    if requests is None:
        return None
    try:
        r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies, allow_redirects=True)
        if r.status_code >= 200 and r.status_code < 400 and r.text:
            return r.text
    except Exception:
        return None
    return None


def get_wp_json_info(domain: str, timeout: int, user_agent: str) -> Optional[Dict]:
    """Try to fetch WordPress site info from /wp-json without proxy.
    Returns parsed JSON dict if available, else None.
    """
    if requests is None:
        return None
    headers = {'User-Agent': user_agent, 'Accept': 'application/json,text/json,*/*'}
    # Try https and http variants, with and without www
    base_variants = [
        f"https://{normalize_domain(domain)}",
        f"https://www.{normalize_domain(domain)}",
        f"http://{normalize_domain(domain)}",
        f"http://www.{normalize_domain(domain)}",
    ]
    seen = set()
    for base in base_variants:
        if base in seen:
            continue
        seen.add(base)
        url = base.rstrip('/') + '/wp-json'
        try:
            r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code >= 200 and r.status_code < 400 and r.content:
                # Prefer JSON decoding; some servers set wrong content-type
                try:
                    return r.json()
                except Exception:
                    # Best-effort: attempt to parse minimal JSON-like responses
                    return None
        except Exception:
            continue
    return None


def infer_from_wp_json_info(info: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Infer domain/subdomain from WP JSON info.
    Uses site "name" and "description" as primary signals.
    From namespaces/routes, only whitelisted content hints are considered
    (e.g., recipe, kitchen, travel, decor) to avoid plugin/technical noise.
    """
    if not isinstance(info, dict):
        return None, None
    terms: List[str] = []
    # Basic textual fields
    for key in ('name', 'description', 'site_description', 'site_name'):
        val = info.get(key)
        if isinstance(val, str) and val:
            terms.extend(re.findall(r'[A-Za-z]{3,}', val))
    # Namespaces: include only whitelisted hints
    ns = info.get('namespaces')
    if isinstance(ns, list):
        for n in ns:
            if not isinstance(n, str):
                continue
            tokens = [t.lower() for t in re.findall(r'[A-Za-z]{3,}', n.replace('/', ' '))]
            for t in tokens:
                if t in HINT_WHITELIST and t not in TECH_STOPWORDS:
                    terms.append(t)
    # Routes keys: include only whitelisted hints
    routes = info.get('routes')
    if isinstance(routes, dict):
        for k in routes.keys():
            if not isinstance(k, str):
                continue
            tokens = [t.lower() for t in re.findall(r'[A-Za-z]{3,}', k.replace('/', ' '))]
            for t in tokens:
                if t in HINT_WHITELIST and t not in TECH_STOPWORDS:
                    terms.append(t)
    # Score using same logic as head terms
    return _score_terms_choose(terms)


def fetch_homepage_html(domain: str, timeout: int, user_agent: str, use_proxy: bool) -> Tuple[Optional[str], Optional[str], str]:
    """Fetch homepage HTML following required order:
    1) Try trafilatura (no proxy)
    2) If it failed, try requests with proxy over HTTPS
    3) If still failed, try requests with proxy over HTTP
    Returns: (html, final_url, method_used)
    method_used in {'trafilatura', 'requests-proxy-https', 'requests-proxy-http', ''}
    """
    html: Optional[str] = None
    final_url: Optional[str] = None
    method_used = ''

    for url in build_url_variants(domain):
        # Only process each variant once
        # 1) Try trafilatura.fetch_url if available
        if fetch_url is not None:
            try:
                html = fetch_url(url, no_ssl=True, decode=True)
                if html and not cf_suspected(html):
                    final_url = url
                    method_used = 'trafilatura'
                    return html, final_url, method_used
            except Exception:
                html = None
        # 2) If allowed, try with proxy over HTTPS only
        if use_proxy and url.startswith('https://'):
            html = http_get(url, timeout, user_agent, use_proxy=True)
            if html and not cf_suspected(html):
                final_url = url
                method_used = 'requests-proxy-https'
                return html, final_url, method_used
        # 3) If allowed, try with proxy over HTTP
        if use_proxy and url.startswith('http://'):
            html = http_get(url, timeout, user_agent, use_proxy=True)
            if html and not cf_suspected(html):
                final_url = url
                method_used = 'requests-proxy-http'
                return html, final_url, method_used
    return None, None, method_used


def infer_from_metadata(meta: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Infer domain/subdomain from trafilatura metadata dict."""
    # Collect candidate terms from categories/keywords/breadcrumbs/title/description
    terms: List[str] = []
    if not isinstance(meta, dict):
        return None, None
    for key in ('categories', 'tags', 'keywords', 'breadcrumbs', 'section', 'sections', 'article:section'):
        val = meta.get(key)
        if isinstance(val, list):
            terms.extend([str(x) for x in val if x])
        elif isinstance(val, str) and val:
            # some metadata may be comma-separated keywords
            parts = [p.strip() for p in re.split(r',|/|\|', val) if p.strip()]
            terms.extend(parts)
    # Use title and description/site_name as weak signals
    for key in ('title', 'description', 'site_name'):
        val = meta.get(key)
        if isinstance(val, str) and val:
            terms.extend(re.findall(r'[A-Za-z]{3,}', val))

    # Score using unified chooser with filtering
    return _score_terms_choose(terms)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def _score_terms_choose(terms: List[str]) -> Tuple[Optional[str], Optional[str]]:
    if not terms:
        return None, None
    # Normalize and drop generic + technical stopwords
    norm_terms = [t.lower() for t in terms if isinstance(t, str) and t]
    norm_terms = [t for t in norm_terms if t not in GENERIC_TERMS and t not in TECH_STOPWORDS]
    if not norm_terms:
        return None, None
    # Prefer whitelisted content hints if available
    wl_terms = [t for t in norm_terms if t in HINT_WHITELIST]
    use_terms = wl_terms if wl_terms else norm_terms
    # Domain scores
    scores: Dict[str, int] = {k: 0 for k in DOMAIN_KEYWORDS.keys()}
    for t in use_terms:
        for dom, kws in DOMAIN_KEYWORDS.items():
            if any(k in t for k in kws):
                scores[dom] += 1
    domain: Optional[str] = None
    max_sc = 0
    for dom, sc in scores.items():
        if sc > max_sc:
            domain, max_sc = dom, sc
    if domain is None or max_sc == 0:
        return None, None
    # choose subdomain term aligned to chosen domain, avoiding stopwords
    sub: Optional[str] = None
    for t in use_terms:
        if t in TECH_STOPWORDS or t in GENERIC_TERMS:
            continue
        if any(k in t for k in DOMAIN_KEYWORDS[domain]):
            sub = t
            break
    if not sub:
        # pick first non-generic, non-technical term
        for t in use_terms:
            if t not in GENERIC_TERMS and t not in TECH_STOPWORDS:
                sub = t
                break
    return domain, sub


def _extract_head_terms(html: str) -> List[str]:
    terms: List[str] = []
    if not html:
        return terms
    try:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, 'lxml') if 'lxml' in sys.modules else BeautifulSoup(html, 'html.parser')
            # meta keywords
            for meta in soup.find_all('meta'):
                name = (meta.get('name') or meta.get('property') or '').lower()
                content = meta.get('content') or ''
                if not content:
                    continue
                if name in {'keywords', 'news_keywords', 'category', 'tags', 'section', 'article:section', 'og:section'}:
                    parts = [p.strip() for p in re.split(r',|/|\|', content) if p.strip()]
                    terms.extend(parts)
                if name in {'og:site_name', 'og:title', 'og:description'}:
                    terms.extend(re.findall(r'[A-Za-z]{3,}', content))
            # title and headers
            if soup.title and soup.title.string:
                terms.extend(re.findall(r'[A-Za-z]{3,}', soup.title.string))
            for tag in soup.find_all(['h1', 'h2']):
                txt = tag.get_text(' ', strip=True)
                if txt:
                    terms.extend(re.findall(r'[A-Za-z]{3,}', txt))
        else:
            # Regex-lite fallback: only parse <title> to avoid brittle HTML regexes
            t = re.findall(r'<title>(.*?)</title>', html, flags=re.I|re.S)
            for s in t:
                terms.extend(re.findall(r'[A-Za-z]{3,}', s))
    except Exception:
        pass
    return terms


def build_mapping(domains: List[str], timeout: int, user_agent: str, allow_proxy: bool, logger: logging.Logger, parallel: int = 24, fallback_dom: str = 'daily life', fallback_sub: str = 'general') -> Dict:
    """Build mapping concurrently.
    - parallel: number of concurrent domains to resolve
    - fallback_dom/sub: values to use if inference cannot determine categories
    """
    mapping: Dict[str, Dict[str, str]] = {}

    # Dedup and normalize first
    norm_domains: List[str] = []
    seen = set()
    for d in domains:
        nd = normalize_domain(d)
        if not nd or nd in seen:
            continue
        seen.add(nd)
        norm_domains.append(nd)

    # Worker function for one domain
    def process_one(nd: str) -> Tuple[str, Dict[str, str]]:
        domain_val: Optional[str] = None
        sub_val: Optional[str] = None
        decided_by: str = 'unknown'
        used_fallback = False
        method_used = ''

        # 0) Special-case rules
        if nd in SPECIAL_DOMAIN_RULES:
            rule = SPECIAL_DOMAIN_RULES[nd]
            domain_val = rule.get('domain')
            sub_val = rule.get('subdomain')
            decided_by = 'special-rule'
        else:
            # 1) Try WordPress JSON first (no proxy)
            try:
                wp_info = get_wp_json_info(nd, timeout, user_agent)
            except Exception:
                wp_info = None
            if wp_info:
                d_wp, s_wp = infer_from_wp_json_info(wp_info)
                if d_wp and s_wp:
                    domain_val, sub_val = d_wp, s_wp
                    decided_by = 'wp-json'
                    method_used = 'wp-json'

            # 2) If not decided, try network fetch and trafilatura metadata
            if not domain_val or not sub_val:
                html, final_url, method_used = fetch_homepage_html(nd, timeout, user_agent, use_proxy=allow_proxy)
                meta = None
                if html and extract_metadata is not None:
                    try:
                        meta = extract_metadata(html, url=final_url)
                    except Exception:
                        meta = None
                if meta:
                    dval, sval = infer_from_metadata(meta)
                    if dval and sval:
                        domain_val, sub_val = dval, sval
                        decided_by = 'trafilatura-metadata'
                # 3) Fallback: parse HTML head/meta terms
                if (not domain_val or not sub_val) and html:
                    terms = _extract_head_terms(html)
                    d2, s2 = _score_terms_choose(terms)
                    if d2 and s2:
                        domain_val, sub_val = d2, s2
                        decided_by = 'html-head-terms'

            # 4) Last resort: tokenize domain name
            if not domain_val or not sub_val:
                tokens = tokenize_domain(nd)
                dom_h, sub_h = guess_domain_and_sub(tokens)
                domain_val = domain_val or dom_h
                sub_val = sub_val or sub_h
                used_fallback = True
                if decided_by == 'unknown':
                    decided_by = 'domain-heuristic'

        # Logging
        if used_fallback:
            reason = 'metadata_missing_or_inconclusive'
            if decided_by == 'domain-heuristic':
                if method_used == '' or method_used is None:
                    reason = 'network_failed_or_blocked'
            logger.info(f"fallback-used domain={nd} method={method_used or 'none'} decided_by={decided_by} domain_val={domain_val} sub_val={sub_val}")
        else:
            logger.info(f"resolved domain={nd} decided_by={decided_by} method={method_used or 'none'} domain_val={domain_val} sub_val={sub_val}")
            if method_used in ('requests-proxy',):
                logger.info(f"proxy-used domain={nd} method={method_used}")

        # Apply final fallback to ensure no 'unknown' leaks
        final_domain = domain_val or fallback_dom
        final_sub = sub_val or fallback_sub
        return nd, {
            'domain': final_domain,
            'subdomain': final_sub
        }

    # Concurrency with nice progress
    total = len(norm_domains)
    bar = None
    if tqdm is not None:
        try:
            bar = tqdm(total=total, desc='Resolving domains', unit='site', leave=False, dynamic_ncols=True)
        except Exception:
            bar = None

    max_workers = max(1, int(parallel or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(process_one, nd): nd for nd in norm_domains}
        for fut in as_completed(future_map):
            nd = future_map[fut]
            try:
                key, value = fut.result()
                mapping[key] = value
            except Exception as e:
                # Log and mark with configured fallbacks (no 'unknown')
                logger.error(f"error-processing domain={nd} err={e}")
                mapping[nd] = {'domain': fallback_dom, 'subdomain': fallback_sub}
            finally:
                if bar is not None:
                    try:
                        bar.update(1)
                    except Exception:
                        pass

    if bar is not None:
        try:
            bar.close()
        except Exception:
            pass

    return {'domain_mapping': mapping}


def main():
    parser = argparse.ArgumentParser(description='Generate domain_mapping YAML from a site list using live metadata when possible.')
    parser.add_argument('-i', '--input', required=True, help='Path to sitelist.txt')
    parser.add_argument('-o', '--output', help='Output YAML file (optional). If omitted, prints to stdout.')
    parser.add_argument('--timeout', type=int, default=15, help='Network timeout seconds (default: 15)')
    parser.add_argument('--no-proxy', action='store_true', help='Do not use Cloudflare-bypass proxy as a retry fallback')
    parser.add_argument('--user-agent', default=DEFAULT_UA, help='Custom User-Agent string for requests')
    parser.add_argument('--parallel', type=int, default=24, help='Number of domains to resolve concurrently (default: 24)')
    parser.add_argument('--fallback_dom', default='daily life', help='Fallback domain when inference is inconclusive (default: daily life)')
    parser.add_argument('--fallback_sub', default='general', help='Fallback subdomain when inference is inconclusive (default: general)')
    args = parser.parse_args()

    log_file = setup_logger()
    logger = logging.getLogger('domain_extractor')

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    # Read lines, ignore comments/blank
    raw_lines = in_path.read_text(encoding='utf-8').splitlines()
    domains = []
    for line in raw_lines:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        domains.append(s)

    data = build_mapping(domains, timeout=args.timeout, user_agent=args.user_agent, allow_proxy=(not args.no_proxy), logger=logger, parallel=args.parallel, fallback_dom=args.fallback_dom, fallback_sub=args.fallback_sub)

    yaml_str = yaml.safe_dump(data, sort_keys=True, allow_unicode=True)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(yaml_str, encoding='utf-8')
        print(f"✓ Wrote domain_mapping for {len(data['domain_mapping'])} domains to {out_path}")
        print(f"  Log: {log_file}")
    else:
        print(yaml_str)
        print(f"# Log: {log_file}")


if __name__ == '__main__':
    main()

import os
import sys
import traceback
from datetime import datetime
from typing import Iterable

from lxml import etree

# Ensure project root on path
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bigdata.domain_configs import DomainConfigRegistry  # noqa: E402
from bigdata.domain_configs.domain_config import DomainConfig  # noqa: E402


XPATH_FIELDS = [
    'navigation_xpaths',
    'article_target_xpaths',
    'title_xpath',
    'body_xpath',
    'tags_xpath',
    'author_xpath',
    'post_date_xpath',
    'exclude_xpaths',
]


def _to_iterable(value) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return value
    # single string
    return [value]


def validate_xpath(expr: str) -> tuple[bool, str | None]:
    try:
        # lxml will parse and raise XPathSyntaxError on invalid expressions
        etree.XPath(expr)
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def validate_config(config: DomainConfig) -> dict:
    results = {}
    for field in XPATH_FIELDS:
        value = getattr(config, field, None)
        entries = _to_iterable(value)
        field_results = []
        for idx, expr in enumerate(entries):
            if not expr or not isinstance(expr, str):
                continue
            ok, err = validate_xpath(expr)
            field_results.append({
                'index': idx,
                'expr': expr,
                'ok': ok,
                'error': err,
            })
        if field_results:
            results[field] = field_results
    return results


def main() -> int:
    DomainConfigRegistry.clear()
    DomainConfigRegistry.load_all_configs()

    domains = sorted(DomainConfigRegistry.get_all_domains())
    invalid_total = 0
    lines = []

    header = f"XPath Validation Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    lines.append(header)
    lines.append('=' * len(header))
    lines.append("")

    for domain in domains:
        cfg = DomainConfigRegistry.get(domain)
        results = validate_config(cfg)
        domain_invalid = 0
        lines.append(f"Domain: {domain}")
        for field, items in results.items():
            for item in items:
                if not item['ok']:
                    domain_invalid += 1
                    invalid_total += 1
                    lines.append(f"  [INVALID] {field}[{item['index']}] -> {item['expr']}")
                    lines.append(f"            Error: {item['error']}")
        if domain_invalid == 0:
            lines.append("  All XPath expressions OK")
        lines.append("")

    summary = f"Total domains: {len(domains)}, Invalid XPath entries: {invalid_total}"
    lines.append(summary)

    report_text = "\n".join(lines)
    print(report_text)

    # Save report
    logs_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    report_path = os.path.join(logs_dir, f"xpath_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise

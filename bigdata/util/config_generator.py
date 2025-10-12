"""
Configuration file generator utility
Generates domain configuration templates
"""

from pathlib import Path


def generate_config_template(domain, output_path):
    """Generate a configuration template for a domain"""

    config_template = f'''"""
Configuration for {domain}
Generated configuration template - Please customize!

Instructions:
1. Test the domain to find correct XPath selectors
2. Update the XPaths below with actual values
3. Test configuration: python cli.py test {domain}
4. Adjust settings as needed
"""

from bigdata.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

# TODO: Update these XPath selectors!
# Use browser DevTools to find correct selectors for this domain
# Right-click element -> Inspect -> Copy -> Copy XPath

{domain.replace('.', '_').upper()}_CONFIG = DomainConfig(
    domain="{domain}",
    
    # Rendering engine: SCRAPY (fast, no JS) or PLAYWRIGHT (slow, renders JS)
    render_engine=RenderEngine.SCRAPY,
    
    # ========================================================================
    # NAVIGATION XPATHS (Required)
    # ========================================================================
    
    # XPath to find article links on listing pages
    # Example: "//article//a/@href" or "//div[@class='post']//a/@href"
    article_links_xpath="TODO: Add article links XPath",
    
    # XPath to find pagination/next page links (Optional)
    # Example: "//a[@rel='next']/@href" or "//div[@class='pagination']//a/@href"
    pagination_xpath=None,  # TODO: Add if pagination exists
    
    # Maximum pages to crawl (None for unlimited)
    max_pages=None,
    
    # ========================================================================
    # CONTENT EXTRACTION XPATHS (Required)
    # ========================================================================
    
    # XPath to extract article title
    # Example: "//h1/text()" or "//h1[@class='title']/text()"
    title_xpath="//h1/text()",  # TODO: Verify this works
    
    # XPath to extract article body/content
    # Example: "//article" or "//div[@class='content']"
    body_xpath="//article",  # TODO: Verify this works
    
    # ========================================================================
    # OPTIONAL CONTENT EXTRACTION
    # ========================================================================
    
    # XPath to extract tags/categories
    # Example: "//a[@rel='tag']/text()"
    tags_xpath=None,  # TODO: Add if needed
    
    # XPath to extract author name
    # Example: "//span[@class='author']/text()"
    author_xpath=None,  # TODO: Add if needed
    
    # XPath to extract post date
    # Example: "//time/@datetime" or "//span[@class='date']/text()"
    post_date_xpath=None,  # TODO: Add if needed
    
    # Date format for parsing (strptime format)
    # Example: "%Y-%m-%d" for "2024-01-15"
    # Example: "%B %d, %Y" for "January 15, 2024"
    post_date_format=None,  # TODO: Add if post_date_xpath is set
    
    # ========================================================================
    # CONTENT EXCLUSIONS
    # ========================================================================
    
    # Additional XPaths to exclude from body content
    # Common exclusions (ads, scripts, etc.) are automatically added
    exclude_xpaths=[
        # "//div[@class='advertisement']",
        # "//aside[@class='sidebar']",
    ],
    
    # ========================================================================
    # NETWORK SETTINGS
    # ========================================================================
    
    # Delay between requests (seconds) - be respectful!
    download_delay=1.0,
    
    # Number of concurrent requests to this domain
    concurrent_requests=2,
    
    # ========================================================================
    # PROXY CONFIGURATION (Optional)
    # ========================================================================
    
    proxy_config=ProxyConfig(
        enabled=False,  # Set to True to enable
        proxy_list=[
            # "http://proxy1.example.com:8080",
            # "http://proxy2.example.com:8080",
        ],
        rotation_strategy="round_robin"  # round_robin, random, or sticky
    ),
    
    # ========================================================================
    # RETRY CONFIGURATION
    # ========================================================================
    
    retry_config=RetryConfig(
        max_retries=5,
        retry_http_codes=[403, 429, 500, 502, 503, 504],
        backoff_factor=2.0,
        priority_boost=10
    ),
    
    # ========================================================================
    # BOT PROTECTION HANDLING
    # ========================================================================
    
    bot_protection=BotProtectionConfig(
        enabled=True,
        use_stealth_mode=True,  # Only works with Playwright
        wait_for_selectors=[
            # Add selectors to wait for (Playwright only)
            # "#content",
            # ".article-body",
        ]
    ),
    
    # ========================================================================
    # PLAYWRIGHT SETTINGS (if render_engine=PLAYWRIGHT)
    # ========================================================================
    
    playwright_wait_until="networkidle",  # load, domcontentloaded, networkidle
    playwright_timeout=30000,  # milliseconds
    
    # ========================================================================
    # METADATA
    # ========================================================================
    
    lang="en",  # Language code
    active=True,  # Set to False to disable
    notes="TODO: Add configuration notes"
)

# Auto-register configuration
DomainConfigRegistry.register({domain.replace('.', '_').upper()}_CONFIG)


# ============================================================================
# TESTING NOTES
# ============================================================================
# 
# After filling in the XPaths above:
#
# 1. Test the configuration:
#    python cli.py test {domain} --verbose
#
# 2. Check what was extracted:
#    - Title should be clear and complete
#    - Body should contain main article content
#    - Article links should point to actual articles
#    - Pagination should find next page (if any)
#
# 3. Common issues:
#    - XPath returns empty: Use browser DevTools to verify selector
#    - Multiple elements found: Make XPath more specific
#    - JavaScript content missing: Switch to render_engine=RenderEngine.PLAYWRIGHT
#
# 4. Fine-tuning:
#    - If getting blocked: Enable proxies or Playwright stealth mode
#    - If too slow: Decrease download_delay (but be respectful!)
#    - If missing content: Add wait_for_selectors (Playwright only)
#
# ============================================================================
'''

    # Create directory if it doesn't exist
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write template
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(config_template)

    print(f"✓ Configuration template created: {output_path}")
    print(f"\nNext steps:")
    print(f"1. Edit {output_path}")
    print(f"2. Fill in the TODO items with correct XPath selectors")
    print(f"3. Test with: python cli.py test {domain} --verbose")
    print(f"4. Adjust and re-test until all extractions work correctly")

    return output_path
import click
import os
import sys
from pathlib import Path

from .domain_configs import DomainConfigRegistry
from .domain_configs.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from .util.config_tester import ConfigTester


@click.group()
def cli():
    """Domain configuration management tool for web scraping"""
    pass


@cli.command()
@click.argument('domain')
@click.option('--prompt', '-i', is_flag=True, help='prompts generation mode')
def add(domain, interactive):
    """Add a new domain configuration"""

    if not interactive:
        # Quick add with template
        from bigdata.util.config_generator import generate_config_template
        output = f"domain_configs/{domain.replace('.', '_')}.py"
        generate_config_template(domain, output)
        click.echo(f"✓ Template created: {output}")
        click.echo(f"  Edit the file and run: python cli.py test {domain}")
        return

    click.echo(f"\n{'=' * 60}")
    click.echo(f"🔧 Adding Configuration for: {domain}")
    click.echo(f"{'=' * 60}\n")

    # Required fields
    click.echo("📋 REQUIRED FIELDS")
    click.echo("-" * 60)

    article_links_xpath = click.prompt(
        "Article links XPath, can specify multiple, seperated by 'comma'",
        default="//article//a/@href"
    )

    title_xpath = click.prompt(
        "Title XPath",
        default="//h1/text()"
    )

    body_xpath = click.prompt(
        "Body content XPath",
        default="//article | //div[contains(@class,'content')]"
    )

    # Optional fields
    click.echo("\n📝 OPTIONAL FIELDS (press Enter to skip)")
    click.echo("-" * 60)

    pagination_xpath = click.prompt(
        "Pagination links XPath, can specify multiple, seperated by 'comma'",
        default="",
        show_default=False
    ) or None

    max_pages = click.prompt(
        "Max pagination depth (0 for unlimited)",
        type=int,
        default=0
    )
    max_pages = max_pages if max_pages > 0 else None

    tags_xpath = click.prompt(
        "Tags XPath",
        default=""
    ) or None

    author_xpath = click.prompt(
        "Author XPath",
        default=""
    ) or None

    post_date_xpath = click.prompt(
        "Post date XPath",
        default=""
    ) or None

    post_date_format = None
    if post_date_xpath:
        post_date_format = click.prompt(
            "Post date format (strptime format, e.g., %Y-%m-%d)",
            default=""
        ) or None

    # Rendering engine
    click.echo("\n🎭 RENDERING ENGINE")
    click.echo("-" * 60)

    render_engine = click.prompt(
        "Rendering engine",
        type=click.Choice(['scrapy', 'playwright'], case_sensitive=False),
        default='scrapy'
    )

    # Rate limiting
    click.echo("\n⏱️  RATE LIMITING")
    click.echo("-" * 60)

    download_delay = click.prompt(
        "Download delay (seconds)",
        type=float,
        default=1.0
    )

    concurrent_requests = click.prompt(
        "Concurrent requests per domain",
        type=int,
        default=2
    )

    # Proxy configuration
    click.echo("\n🔒 PROXY CONFIGURATION")
    click.echo("-" * 60)

    use_proxy = click.confirm("Use proxy?", default=False)

    proxy_config = ProxyConfig()
    if use_proxy:
        proxy_config.enabled = True

        click.echo("Enter proxy URLs (one per line, empty line to finish):")
        proxy_list = []
        while True:
            proxy = click.prompt("Proxy URL", default="", show_default=False)
            if not proxy:
                break
            proxy_list.append(proxy)

        proxy_config.proxy_list = proxy_list

        if proxy_list:
            proxy_config.rotation_strategy = click.prompt(
                "Proxy rotation strategy",
                type=click.Choice(['round_robin', 'random', 'sticky']),
                default='round_robin'
            )

    # Bot protection
    click.echo("\n🤖 BOT PROTECTION")
    click.echo("-" * 60)

    bot_protection = BotProtectionConfig()
    bot_protection.enabled = click.confirm(
        "Enable bot protection detection?",
        default=True
    )

    if bot_protection.enabled and render_engine == 'playwright':
        bot_protection.use_stealth_mode = click.confirm(
            "Use stealth mode?",
            default=True
        )

        if click.confirm("Add wait-for selectors?", default=False):
            wait_selectors = []
            click.echo("Enter selectors to wait for (empty to finish):")
            while True:
                selector = click.prompt("Selector", default="", show_default=False)
                if not selector:
                    break
                wait_selectors.append(selector)
            bot_protection.wait_for_selectors = wait_selectors

    # Retry configuration
    click.echo("\n🔄 RETRY CONFIGURATION")
    click.echo("-" * 60)

    retry_config = RetryConfig()
    retry_config.max_retries = click.prompt(
        "Max retries",
        type=int,
        default=5
    )

    # Additional excludes
    click.echo("\n🗑️  CONTENT EXCLUSIONS")
    click.echo("-" * 60)

    exclude_xpaths = []
    if click.confirm("Add custom XPath exclusions?", default=False):
        click.echo("Enter XPaths to exclude (empty to finish):")
        while True:
            xpath = click.prompt("Exclude XPath", default="", show_default=False)
            if not xpath:
                break
            exclude_xpaths.append(xpath)

    # Metadata
    click.echo("\n📊 METADATA")
    click.echo("-" * 60)

    lang = click.prompt(
        "Language code",
        default="en"
    )

    notes = click.prompt(
        "Notes (optional)",
        default=""
    )

    # Create configuration
    config = DomainConfig(
        domain=domain,
        render_engine=RenderEngine(render_engine),
        pagination_xpath=pagination_xpath,
        article_links_xpath=article_links_xpath,
        max_pages=max_pages,
        title_xpath=title_xpath,
        body_xpath=body_xpath,
        tags_xpath=tags_xpath,
        author_xpath=author_xpath,
        post_date_xpath=post_date_xpath,
        post_date_format=post_date_format,
        exclude_xpaths=exclude_xpaths,
        download_delay=download_delay,
        concurrent_requests=concurrent_requests,
        proxy_config=proxy_config,
        retry_config=retry_config,
        bot_protection=bot_protection,
        lang=lang,
        notes=notes
    )

    # Validate configuration
    is_valid, errors = config.validate()

    if not is_valid:
        click.echo("\n❌ Configuration validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        sys.exit(1)

    # Save configuration
    config_dir = Path("domain_configs")
    config_dir.mkdir(exist_ok=True)

    config_file = config_dir / f"{domain.replace('.', '_')}.py"

    # Generate Python file
    config_content = generate_config_file(domain, config)

    with open(config_file, 'w') as f:
        f.write(config_content)

    click.echo(f"\n✓ Configuration saved: {config_file}")

    # Prompt for testing
    if click.confirm("\nTest configuration now?", default=True):
        _run_config_test(domain, verbose=True)


@cli.command()
def list():
    """List all registered domains"""
    DomainConfigRegistry.load_all_configs()
    domains = DomainConfigRegistry.get_all_domains()

    if not domains:
        click.echo("No domains registered yet.")
        return

    click.echo(f"\n📋 Registered domains ({len(domains)}):")
    click.echo("=" * 60)

    for domain in sorted(domains):
        config = DomainConfigRegistry.get(domain)
        status = "✓" if config.active else "✗"
        engine = config.render_engine.value

        click.echo(f"{status} {domain:<30} [{engine}]")
        if config.notes:
            click.echo(f"   Note: {config.notes}")


@cli.command()
@click.argument('domain')
def validate(domain):
    """Validate configuration for a domain"""
    DomainConfigRegistry.load_all_configs()
    config = DomainConfigRegistry.get(domain)

    if not config:
        click.echo(f"❌ No configuration found for {domain}")
        sys.exit(1)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Validating configuration for: {domain}")
    click.echo(f"{'=' * 60}\n")

    is_valid, errors = config.validate()

    if is_valid:
        click.echo("✓ Configuration is valid\n")

        click.echo("📝 Configuration Details:")
        click.echo("-" * 60)
        click.echo(f"  Domain: {config.domain}")
        click.echo(f"  Engine: {config.render_engine.value}")
        click.echo(f"  Active: {config.active}")
        click.echo(f"  Language: {config.lang}")
        click.echo(f"\n  Title XPath: {config.title_xpath}")
        click.echo(f"  Body XPath: {config.body_xpath}")
        click.echo(f"  Article Links: {config.article_links_xpath}")

        if config.pagination_xpath:
            click.echo(f"  Pagination: {config.pagination_xpath}")
            if config.max_pages:
                click.echo(f"  Max Pages: {config.max_pages}")

        if config.proxy_config.enabled:
            click.echo(f"\n  Proxy: Enabled ({len(config.proxy_config.proxy_list)} proxies)")
            click.echo(f"  Strategy: {config.proxy_config.rotation_strategy}")

        click.echo(f"\n  Download Delay: {config.download_delay}s")
        click.echo(f"  Concurrent Requests: {config.concurrent_requests}")
        click.echo(f"  Max Retries: {config.retry_config.max_retries}")
    else:
        click.echo("❌ Configuration validation failed:\n")
        for error in errors:
            click.echo(f"  - {error}")
        sys.exit(1)


@cli.command()
@click.argument('domain')
@click.option('--url', '-u', help='Specific URL to test (listing page or article page)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--article-url', help='Test with a specific article URL')
@click.option('--listing-url', help='Test with a specific listing URL')
def test(domain, url, verbose, article_url, listing_url):
    """Test configuration by fetching sample pages

    Examples:
        # Test homepage (auto-detect page type)
        python cli.py test example.com

        # Test specific URL
        python cli.py test example.com --url https://example.com/articles

        # Test article page
        python cli.py test example.com --article-url https://example.com/article-1

        # Test listing page
        python cli.py test example.com --listing-url https://example.com/articles
    """

    # Determine which URL to test
    test_urls = []

    if article_url:
        test_urls.append(('article', article_url))

    if listing_url:
        test_urls.append(('listing', listing_url))

    if url:
        test_urls.append(('auto', url))

    if not test_urls:
        # Default: test homepage
        test_urls.append(('auto', None))

    # Run tests for each URL
    all_passed = True

    for page_type, test_url in test_urls:
        if len(test_urls) > 1:
            click.echo(f"\n{'=' * 60}")
            click.echo(f"Testing {page_type} page: {test_url or 'homepage'}")
            click.echo(f"{'=' * 60}")

        result = _run_config_test(domain, test_url, verbose, expected_type=page_type)

        if not result:
            all_passed = False

    if not all_passed:
        sys.exit(1)


@cli.command()
@click.argument('domain')
def edit(domain):
    """Edit an existing domain configuration"""
    config_file = Path(f"domain_configs/{domain.replace('.', '_')}.py")

    if not config_file.exists():
        click.echo(f"❌ Configuration file not found: {config_file}")
        sys.exit(1)

    editor = os.environ.get('EDITOR', 'nano')
    os.system(f"{editor} {config_file}")

    click.echo(f"\n✓ Configuration edited: {config_file}")

    if click.confirm("Validate configuration?", default=True):
        DomainConfigRegistry.load_all_configs()
        config = DomainConfigRegistry.get(domain)

        if config:
            is_valid, errors = config.validate()
            if is_valid:
                click.echo("✓ Configuration is valid")
            else:
                click.echo("❌ Validation errors:")
                for error in errors:
                    click.echo(f"  - {error}")


@cli.command()
@click.argument('domain')
def delete(domain):
    """Delete a domain configuration"""
    config_file = Path(f"domain_configs/{domain.replace('.', '_')}.py")

    if not config_file.exists():
        click.echo(f"❌ Configuration file not found: {config_file}")
        sys.exit(1)

    if click.confirm(f"⚠️  Delete configuration for {domain}?", default=False):
        config_file.unlink()
        click.echo(f"✓ Deleted: {config_file}")
    else:
        click.echo("Cancelled")


@cli.command()
@click.argument('domain')
@click.option('--active/--inactive', default=None, help='Set active status')
def toggle(domain, active):
    """Toggle domain active status"""
    DomainConfigRegistry.load_all_configs()
    config = DomainConfigRegistry.get(domain)

    if not config:
        click.echo(f"❌ No configuration found for {domain}")
        sys.exit(1)

    if active is None:
        active = not config.active

    config.active = active

    # Update the config file
    config_file = Path(f"domain_configs/{domain.replace('.', '_')}.py")
    config_content = generate_config_file(domain, config)

    with open(config_file, 'w') as f:
        f.write(config_content)

    status = "enabled" if active else "disabled"
    click.echo(f"✓ Domain {domain} {status}")


@cli.command()
@click.option('--domain', '-d', help='Test specific domain')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def test_all(domain, verbose):
    """Test all domain configurations"""
    DomainConfigRegistry.load_all_configs()

    if domain:
        domains = [domain]
    else:
        domains = DomainConfigRegistry.get_all_domains()

    if not domains:
        click.echo("No domains to test")
        return

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Testing {len(domains)} domain(s)")
    click.echo(f"{'=' * 60}\n")

    results = []

    for dom in domains:
        click.echo(f"\nTesting: {dom}")
        click.echo("-" * 60)

        try:
            result = _run_config_test(dom, None, verbose)
            results.append((dom, result, None))
        except Exception as e:
            results.append((dom, False, str(e)))
            click.echo(f"❌ Test failed: {e}")

    # Summary
    click.echo(f"\n{'=' * 60}")
    click.echo("Test Summary")
    click.echo(f"{'=' * 60}\n")

    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed

    for dom, success, error in results:
        status = "✓" if success else "❌"
        click.echo(f"{status} {dom}")
        if error and verbose:
            click.echo(f"   Error: {error}")

    click.echo(f"\nPassed: {passed}/{len(results)}")
    if failed > 0:
        sys.exit(1)


def _run_config_test(domain, test_url=None, verbose=False, expected_type='auto'):
    """Test a domain configuration (internal function)"""
    DomainConfigRegistry.load_all_configs()
    config = DomainConfigRegistry.get(domain)

    if not config:
        click.echo(f"❌ No configuration found for {domain}")
        sys.exit(1)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Testing configuration for: {domain}")
    if test_url:
        click.echo(f"Test URL: {test_url}")
    if expected_type != 'auto':
        click.echo(f"Expected page type: {expected_type}")
    click.echo(f"{'=' * 60}")

    # Validate first
    is_valid, errors = config.validate()
    if not is_valid:
        click.echo("\n❌ Configuration validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        return False

    click.echo("✓ Configuration validation passed")

    # Initialize tester
    tester = ConfigTester(config)

    # Run tests
    click.echo(f"\n🧪 Running extraction tests...")
    click.echo(f"   Render engine: {config.render_engine.value}")

    test_results = tester.test_all(test_url=test_url, verbose=verbose)

    # Display results
    click.echo(f"\n📊 Test Results:")
    click.echo("-" * 60)

    all_passed = True

    for test_name, result in test_results.items():
        status = "✓" if result['passed'] else "❌"
        click.echo(f"{status} {test_name}: {result['message']}")

        if verbose and result.get('data'):
            if isinstance(result['data'], list):
                click.echo(f"   Data ({len(result['data'])} items):")
                for item in result['data'][:3]:
                    click.echo(f"     - {item}")
            else:
                data_str = str(result['data'])
                if len(data_str) > 200:
                    data_str = data_str[:200] + "..."
                click.echo(f"   Data: {data_str}")

        if not result['passed']:
            all_passed = False

    if all_passed:
        click.echo("\n✅ All tests passed!")
        return True
    else:
        click.echo("\n❌ Some tests failed")
        click.echo("\n💡 Tips:")
        click.echo("  - Use browser DevTools to inspect elements and verify XPaths")
        click.echo("  - Test with --verbose to see extracted data")
        click.echo("  - Test specific URLs: --article-url or --listing-url")
        if config.render_engine.value == 'scrapy':
            click.echo("  - Try switching to Playwright if content is JavaScript-rendered")
        return False


def generate_config_file(domain, config):
    """Generate Python configuration file content"""

    proxy_config_str = ""
    if config.proxy_config.enabled:
        proxy_list_str = ",\n        ".join([f'"{p}"' for p in config.proxy_config.proxy_list])
        proxy_config_str = f"""
    proxy_config=ProxyConfig(
        enabled=True,
        proxy_list=[
        {proxy_list_str}
        ],
        rotation_strategy="{config.proxy_config.rotation_strategy}"
    ),"""

    retry_config_str = f"""
    retry_config=RetryConfig(
        max_retries={config.retry_config.max_retries},
        retry_http_codes={config.retry_config.retry_http_codes},
        backoff_factor={config.retry_config.backoff_factor},
        priority_boost={config.retry_config.priority_boost}
    ),"""

    bot_protection_str = f"""
    bot_protection=BotProtectionConfig(
        enabled={config.bot_protection.enabled},
        use_stealth_mode={config.bot_protection.use_stealth_mode}
    ),"""

    custom_excludes = [x for x in config.exclude_xpaths if x not in config.exclude_xpaths[:len(config.exclude_xpaths)]]
    exclude_str = ""
    if custom_excludes:
        exclude_list = ",\n        ".join([f'"{x}"' for x in custom_excludes])
        exclude_str = f"""
    exclude_xpaths=[
        {exclude_list}
    ],"""

    content = f'''"""
Configuration for {domain}
Auto-generated configuration file

Notes: {config.notes}
"""

from bigdata.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

{domain.replace('.', '_').upper()}_CONFIG = DomainConfig(
    domain="{domain}",
    render_engine=RenderEngine.{config.render_engine.name},

    # Navigation
    article_links_xpath="{config.article_links_xpath}",
    pagination_xpath={f'"{config.pagination_xpath}"' if config.pagination_xpath else 'None'},
    max_pages={config.max_pages if config.max_pages else 'None'},

    # Content extraction
    title_xpath="{config.title_xpath}",
    body_xpath="{config.body_xpath}",
    tags_xpath={f'"{config.tags_xpath}"' if config.tags_xpath else 'None'},
    author_xpath={f'"{config.author_xpath}"' if config.author_xpath else 'None'},
    post_date_xpath={f'"{config.post_date_xpath}"' if config.post_date_xpath else 'None'},
    post_date_format={f'"{config.post_date_format}"' if config.post_date_format else 'None'},{exclude_str}

    # Network settings
    download_delay={config.download_delay},
    concurrent_requests={config.concurrent_requests},{proxy_config_str}{retry_config_str}{bot_protection_str}

    # Metadata
    lang="{config.lang}",
    active={config.active},
    notes="{config.notes}"
)

# Auto-register
DomainConfigRegistry.register({domain.replace('.', '_').upper()}_CONFIG)
'''

    return content


if __name__ == '__main__':
    cli()
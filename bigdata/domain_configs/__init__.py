"""
Domain configuration registry
Auto-discovers and loads all domain configurations
"""
from typing import Optional, List
import logging
import json
import os
from .domain_config import DomainConfig, RenderEngine

class DomainConfigRegistry:
    """Central registry for all domain configurations"""

    _configs = {}
    _logger = logging.getLogger(__name__)

    @classmethod
    def register(cls, config: DomainConfig):
        """Register a domain configuration"""
        cls._configs[config.domain] = config
        if config.site_subdomains:
            for subdomain in config.site_subdomains:
                cls._configs[subdomain] = config
        cls._logger.debug(f"Registered config for {config.domain}")

    @classmethod
    def get(cls, domain: str) -> Optional[DomainConfig]:
        """Get configuration for a domain"""
        return cls._configs.get(domain)

    @classmethod
    def get_all_domains(cls) -> List[str]:
        """Get all registered domains"""
        return list(cls._configs.keys())

    @classmethod
    def load_wild_crawl_configs(cls, config_path: str):
        """Load wild crawl configurations from JSON file"""
        if not os.path.exists(config_path):
            cls._logger.warning(f"Wild crawl config not found: {config_path}")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                wild_config = json.load(f)

            defaults = wild_config.get('defaults', {})
            domains = wild_config.get('domains', [])

            cls._logger.info(f"Loading {len(domains)} wild crawl domains from {config_path}")

            for domain_spec in domains:
                # Merge with defaults
                config_data = {**defaults, **domain_spec}

                # Convert render_engine string to enum
                render_engine_str = config_data.get('render_engine', 'scrapy')
                render_engine = RenderEngine(render_engine_str)

                # Create DomainConfig for wild crawl
                config = DomainConfig(
                    domain=config_data['domain'],
                    site_subdomains=config_data.get('site_subdomains', []),
                    render_engine=render_engine,
                    use_proxy=config_data.get('use_proxy', True),
                    cloudflare_proxy_bypass=config_data.get('cloudflare_proxy_bypass', False),
                    follow_related_content=config_data.get('follow_related_content', False),
                    lang=config_data.get('lang', 'en'),
                    domain_type=config_data.get('domain_type', 'general'),
                    active=config_data.get('active', True),
                    notes=config_data.get('notes', ''),
                    is_wild_crawl=True,  # Mark as wild crawl
                    # No XPaths needed - will use trafilatura
                    navigation_xpaths=None,
                    article_target_xpaths=None,
                    title_xpath=None,
                    body_xpath=None,
                )

                cls.register(config)
                cls._logger.info(f"Registered wild crawl config for {config.domain}")

        except Exception as e:
            cls._logger.error(f"Failed to load wild crawl config: {e}", exc_info=True)

    @classmethod
    def load_all_configs(cls, wild_crawl_config_path: Optional[str] = None):
        """Auto-discover and load all config files + wild crawl configs"""
        import importlib
        import sys

        # Get the directory where this __init__.py file is located
        config_dir = os.path.dirname(__file__)

        cls._logger.info(f"Loading configs from: {config_dir}")

        if not os.path.exists(config_dir):
            cls._logger.warning(f"Config directory does not exist: {config_dir}")
            return

        # Load wild crawl configs first (if path provided)
        if wild_crawl_config_path:
            cls.load_wild_crawl_configs(wild_crawl_config_path)

        # Get all Python files in the directory
        for filename in os.listdir(config_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                module_name = f"bigdata.domain_configs.{filename[:-3]}"

                try:
                    # Import the module
                    if module_name in sys.modules:
                        # Reload if already imported
                        module = importlib.reload(sys.modules[module_name])
                    else:
                        module = importlib.import_module(module_name)

                    # Auto-register configs that follow naming convention
                    registered_count = 0
                    for attr_name in dir(module):
                        if attr_name.endswith('_CONFIG'):
                            config = getattr(module, attr_name)
                            if isinstance(config, DomainConfig):
                                cls.register(config)
                                registered_count += 1

                    if registered_count > 0:
                        cls._logger.info(f"Loaded {registered_count} config(s) from {filename}")

                except Exception as e:
                    cls._logger.error(f"Failed to load config {module_name}: {e}", exc_info=True)

        cls._logger.info(f"Total domains registered: {len(cls._configs)}")

    @classmethod
    def clear(cls):
        """Clear all registered configurations (useful for testing)"""
        cls._configs = {}
        cls._logger.info("Cleared all registered configs")
"""
Domain configuration registry
Auto-discovers and loads all domain configurations
"""
from typing import Optional, List
import logging
from .domain_config import DomainConfig

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
    def load_all_configs(cls):
        """Auto-discover and load all config files"""
        import os
        import importlib
        import sys

        # Get the directory where this __init__.py file is located
        config_dir = os.path.dirname(__file__)

        cls._logger.info(f"Loading configs from: {config_dir}")

        if not os.path.exists(config_dir):
            cls._logger.warning(f"Config directory does not exist: {config_dir}")
            return

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
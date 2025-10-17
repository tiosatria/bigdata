"""
Domain configuration registry
Auto-discovers and loads all domain configurations
"""
from typing import Optional, List, Dict, Any
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
    def apply_dynamic_hints(cls, hints: Dict[str, Any]):
        """Apply dynamic, JSON-provided hints to existing domain configs.
        Supported keys per-domain or in global sections ('*', '__all__', 'global'):
          - allowed_url_regex: list[str] | str
          - blocked_url_keywords: list[str] | str
          - blocked_title_keywords: list[str] | str
          - deny_urls_regex: list[str] | str (merged with existing)
        The merge is additive (unique), does not mutate the config modules, and is reversible by restarting without the hints file.
        """
        if not hints or not isinstance(hints, dict):
            cls._logger.info("No dynamic hints to apply or invalid format.")
            return

        def _tolist(v):
            if v is None:
                return []
            if isinstance(v, (list, tuple)):
                return [x for x in v if x is not None and str(x).strip()]
            return [v]

        # Collect global hints
        global_keys = ['*', '__all__', 'global', '__global__']
        global_hints: Dict[str, Any] = {}
        for gk in global_keys:
            if gk in hints and isinstance(hints[gk], dict):
                for k, v in hints[gk].items():
                    global_hints[k] = v if k not in global_hints else _tolist(global_hints[k]) + _tolist(v)

        def _merge_into(config: DomainConfig, data: Dict[str, Any]):
            if not data:
                return
            # allowed_url_regex (regexes)
            if 'allowed_url_regex' in data and data['allowed_url_regex'] is not None:
                add = _tolist(data['allowed_url_regex'])
                existing = list(config.allowed_url_regex or [])
                config.allowed_url_regex = list(dict.fromkeys(existing + add)) if add else existing or None
            # blocked_url_keywords (lowercased substrings)
            if 'blocked_url_keywords' in data and data['blocked_url_keywords'] is not None:
                add = [str(x).lower() for x in _tolist(data['blocked_url_keywords'])]
                existing = [str(x).lower() for x in (config.blocked_url_keywords or [])]
                config.blocked_url_keywords = list(dict.fromkeys(existing + add)) if add else existing or None
            # blocked_title_keywords
            if 'blocked_title_keywords' in data and data['blocked_title_keywords'] is not None:
                add = [str(x).lower() for x in _tolist(data['blocked_title_keywords'])]
                existing = [str(x).lower() for x in (config.blocked_title_keywords or [])]
                config.blocked_title_keywords = list(dict.fromkeys(existing + add)) if add else existing or None
            # deny_urls_regex
            if 'deny_urls_regex' in data and data['deny_urls_regex'] is not None:
                add = _tolist(data['deny_urls_regex'])
                existing = list(config.deny_urls_regex or [])
                config.deny_urls_regex = list(dict.fromkeys(existing + add)) if add else existing or None

        # Apply global first to all
        if global_hints:
            for cfg_domain, cfg in cls._configs.items():
                try:
                    _merge_into(cfg, global_hints)
                except Exception:
                    cls._logger.warning(f"Failed applying global hints to {cfg_domain}")

        # Apply per-domain overrides
        for key, data in hints.items():
            if key in global_keys:
                continue
            if not isinstance(data, dict):
                continue
            cfg = cls.get(key)
            if not cfg:
                # Try without leading 'www.'
                alt = key.replace('www.', '')
                cfg = cls.get(alt)
            if not cfg:
                cls._logger.info(f"No registered domain matched dynamic hints key: {key}")
                continue
            try:
                _merge_into(cfg, data)
                cls._logger.info(f"Applied dynamic hints to {key}")
            except Exception:
                cls._logger.warning(f"Failed applying dynamic hints to {key}")

    @classmethod
    def clear(cls):
        """Clear all registered configurations (useful for testing)"""
        cls._configs = {}
        cls._logger.info("Cleared all registered configs")
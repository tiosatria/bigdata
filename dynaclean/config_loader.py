"""
Configuration loader with inheritance and deep merge support
"""
import yaml
import os
from copy import deepcopy
from pathlib import Path


class ConfigLoader:
    def __init__(self, config_path='site_cfg.yaml'):
        self.config_path = config_path
        self.config = self._load_yaml()
        self._expand_env_vars()
        self.global_config = self.config.get('GLOBAL', {})
        self.sites = self.config.get('SITES', {})

    def _load_yaml(self):
        """Load YAML configuration file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _expand_env_vars(self):
        """Expand environment variables in paths"""
        if 'GLOBAL' in self.config and 'paths' in self.config['GLOBAL']:
            paths = self.config['GLOBAL']['paths']
            for key, path in paths.items():
                if isinstance(path, str):
                    # Expand environment variables
                    expanded = os.path.expandvars(path)
                    paths[key] = expanded

    def get_global_config(self):
        """Get global configuration"""
        return deepcopy(self.global_config)

    def get_site_config(self, site_key):
        """Get site-specific config with inheritance and overrides"""
        # Use default or global if site not found
        if site_key not in self.sites:
            if 'default' in self.sites:
                site_config = self.sites['default']
            else:
                # Return global as-is
                return deepcopy(self.global_config)
        else:
            site_config = self.sites[site_key]

        merged = {}
        merge_key = site_config.get('inherit')
        if merge_key:
            cfg = self.config.get(merge_key)
            if cfg:
                merged = deepcopy(cfg)

        # Apply overrides
        if 'overrides' in site_config:
            merged = self._deep_merge(merged, site_config['overrides'])

        return merged

    def _deep_merge(self, base, override):
        """Deep merge two dictionaries with override semantics"""
        result = deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursive merge for nested dicts
                result[key] = self._deep_merge(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                # For lists in specific contexts (like cleaning_pipeline), merge by name
                if key == 'cleaning_pipeline':
                    result[key] = self._merge_pipeline(result[key], value)
                else:
                    # Default: override replaces
                    result[key] = value
            else:
                # Override replaces, including null values
                result[key] = value

        return result

    def _merge_pipeline(self, base_pipeline, override_pipeline):
        """Merge cleaning pipeline steps by name"""
        result = deepcopy(base_pipeline)

        # Create lookup by name
        base_lookup = {step['name']: i for i, step in enumerate(result)}

        for override_step in override_pipeline:
            step_name = override_step['name']
            if step_name in base_lookup:
                # Update existing step
                idx = base_lookup[step_name]
                # Deep merge params if both exist
                if 'params' in result[idx] and 'params' in override_step:
                    result[idx]['params'] = self._deep_merge(
                        result[idx]['params'],
                        override_step['params']
                    )
                # Update other fields
                for key, value in override_step.items():
                    if key != 'params':
                        result[idx][key] = value
            else:
                # Add new step
                result.append(override_step)

        return result
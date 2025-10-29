"""
Record filtering with include/exclude logic
"""
import re
from utils.logger import get_logger


class Filter:
    def __init__(self, config):
        self.config = config
        self.filters = config.get('filters', {})
        self.logger = get_logger('filter')

        # Compile regex patterns
        self.exclude_patterns = self._compile_patterns(self.filters.get('exclude', {}))
        self.include_patterns = self._compile_patterns(self.filters.get('include', {}))

    def _compile_patterns(self, filter_dict):
        """Compile regex patterns for each field"""
        compiled = {}
        for field, patterns in filter_dict.items():
            if patterns and patterns is not None:
                compiled[field] = [re.compile(p) for p in patterns]
        return compiled

    def apply(self, record):
        """
        Apply filters to record
        Returns: 'pass', 'excluded', or 'not_included'
        """
        # Extract filterable fields
        filterable = {
            'title': self._get_nested(record, 'metadata.title') or '',
            'url': self._get_nested(record, 'metadata.url') or '',
            'domain': self._get_nested(record, 'metadata.hostname') or '',
            'subdomain': '',  # Can be derived from tags/categories if needed
            'body': record.get('body', '')
        }

        # Exclude check (takes precedence)
        for field, patterns in self.exclude_patterns.items():
            field_value = filterable.get(field, '')
            if not field_value:
                continue

            for pattern in patterns:
                if pattern.search(str(field_value)):
                    self.logger.debug(f"Excluded by {field} pattern: {pattern.pattern}")
                    return 'excluded'

        # Include check (only if include patterns are specified)
        if self.include_patterns:
            # All include patterns must match
            for field, patterns in self.include_patterns.items():
                field_value = filterable.get(field, '')
                if not field_value:
                    return 'not_included'

                for pattern in patterns:
                    if not pattern.search(str(field_value)):
                        self.logger.debug(f"Not included by {field} pattern: {pattern.pattern}")
                        return 'not_included'

        return 'pass'

    def _get_nested(self, obj, path):
        """Get nested value from object"""
        keys = path.split('.')
        value = obj
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
            if value is None:
                return None
        return value
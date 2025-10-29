"""
URL deduplication and filtering cleaner
"""
import re
from .base import BaseCleaner


class UrlDedupeCleaner(BaseCleaner):
    @property
    def name(self):
        return 'url_dedupe_and_filtering'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Default filters
        self.default_filters = [
            r'/about/?$',
            r'/contact/?$',
            r'/privacy/?$',
            r'/terms/?$'
        ]

        # Get regex filters from params
        use_default = params.get('use_default', True)
        custom_filters = params.get('regex_filter', [])

        # Combine filters
        if use_default:
            filters = self.default_filters + custom_filters
        else:
            filters = custom_filters

        # Compile patterns
        self.patterns = [re.compile(f) for f in filters]

    def clean(self, record):
        """Filter URLs based on regex patterns"""
        url = self._get_nested(record, 'metadata.url') or ''

        for pattern in self.patterns:
            if pattern.search(url):
                self.logger.debug(f"Filtered URL: {url} (pattern: {pattern.pattern})")
                return None  # Filter out this record

        return record
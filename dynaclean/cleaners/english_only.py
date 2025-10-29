"""
English-only filter
"""
import re
from .base import BaseCleaner


class EnglishOnlyCleaner(BaseCleaner):
    @property
    def name(self):
        return 'english_only_filter'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Threshold for English content (percentage)
        self.threshold = params.get('threshold', 0.7)

        # Pattern for English letters
        self.english_pattern = re.compile(r'[a-zA-Z]')

    def clean(self, record):
        """Filter non-English content"""
        body = record.get('body', '')

        if not body:
            return None

        # Count English letters
        english_chars = len(self.english_pattern.findall(body))

        # Count total alphanumeric characters
        total_alpha = sum(c.isalpha() for c in body)

        if total_alpha == 0:
            self.logger.debug("No alphabetic characters found")
            return None

        # Calculate English ratio
        english_ratio = english_chars / total_alpha

        if english_ratio < self.threshold:
            self.logger.debug(f"English ratio {english_ratio:.2f} below threshold {self.threshold}")
            return None

        return record
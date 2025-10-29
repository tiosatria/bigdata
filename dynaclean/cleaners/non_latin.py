"""
Non-latin character removal
"""
import re
from .base import BaseCleaner


class NonLatinCleaner(BaseCleaner):
    @property
    def name(self):
        return 'non_latin'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Pattern to keep only Latin characters, numbers, punctuation, and whitespace
        # This removes characters from non-Latin scripts (Arabic, Chinese, Cyrillic, etc.)
        self.non_latin_pattern = re.compile(r'[^\x00-\x7F\x80-\xFF\u0100-\u017F\u0180-\u024F]+')

    def clean(self, record):
        """Remove non-latin characters from body"""
        body = record.get('body', '')

        if body:
            # Remove non-latin characters
            cleaned = self.non_latin_pattern.sub(' ', body)
            # Clean up multiple spaces
            cleaned = re.sub(r'\s+', ' ', cleaned)
            record['body'] = cleaned.strip()

        # Also clean title
        title = self._get_nested(record, 'metadata.title')
        if title:
            cleaned_title = self.non_latin_pattern.sub(' ', title)
            cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
            self._set_nested(record, 'metadata.title', cleaned_title)

        return record
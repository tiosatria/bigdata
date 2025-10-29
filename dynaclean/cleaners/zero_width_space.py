"""
Zero-width space removal
"""
import re
from .base import BaseCleaner


class ZeroWidthSpaceCleaner(BaseCleaner):
    @property
    def name(self):
        return 'zero_width_space'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Zero-width characters
        self.zero_width_pattern = re.compile(
            '[\u200b\u200c\u200d\u200e\u200f\ufeff]'
        )

    def clean(self, record):
        """Remove zero-width characters from body and title"""
        body = record.get('body', '')

        if body:
            record['body'] = self.zero_width_pattern.sub('', body)

        # Clean title
        title = self._get_nested(record, 'metadata.title')
        if title:
            cleaned_title = self.zero_width_pattern.sub('', title)
            self._set_nested(record, 'metadata.title', cleaned_title)

        return record
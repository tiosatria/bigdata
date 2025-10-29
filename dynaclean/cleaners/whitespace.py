"""
Whitespace normalization
"""
import re
from .base import BaseCleaner


class WhitespaceCleaner(BaseCleaner):
    @property
    def name(self):
        return 'whitespace'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Patterns for various whitespace issues
        self.multiple_spaces = re.compile(r' {2,}')
        self.multiple_newlines = re.compile(r'\n{3,}')
        self.trailing_spaces = re.compile(r' +\n')
        self.leading_spaces = re.compile(r'\n +')

    def clean(self, record):
        """Normalize whitespace in body and title"""
        body = record.get('body', '')

        if body:
            # Normalize multiple spaces
            body = self.multiple_spaces.sub(' ', body)

            # Normalize multiple newlines (keep max 2)
            body = self.multiple_newlines.sub('\n\n', body)

            # Remove trailing spaces before newlines
            body = self.trailing_spaces.sub('\n', body)

            # Remove leading spaces after newlines
            body = self.leading_spaces.sub('\n', body)

            # Strip leading/trailing whitespace
            body = body.strip()

            record['body'] = body

        # Clean title
        title = self._get_nested(record, 'metadata.title')
        if title:
            cleaned_title = self.multiple_spaces.sub(' ', title).strip()
            self._set_nested(record, 'metadata.title', cleaned_title)

        return record
"""
HTML entity unescaping
"""
import html
from .base import BaseCleaner


class HtmlUnescapeCleaner(BaseCleaner):
    @property
    def name(self):
        return 'html_unescape'

    def clean(self, record):
        """Unescape HTML entities in body and title"""
        body = record.get('body', '')

        if body:
            record['body'] = html.unescape(body)

        # Clean title
        title = self._get_nested(record, 'metadata.title')
        if title:
            cleaned_title = html.unescape(title)
            self._set_nested(record, 'metadata.title', cleaned_title)

        return record
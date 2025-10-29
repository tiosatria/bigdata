"""
Emoji cleaning
"""
import re
from .base import BaseCleaner


class EmojiCleaner(BaseCleaner):
    @property
    def name(self):
        return 'emoji_cleaning'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Emoji pattern (Unicode ranges)
        self.emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002600-\U000026FF"  # Miscellaneous Symbols
            "\U00002700-\U000027BF"  # Dingbats
            "]+",
            flags=re.UNICODE
        )

    def clean(self, record):
        """Remove emojis from body and title"""
        # Clean body
        body = record.get('body', '')
        if body:
            record['body'] = self.emoji_pattern.sub('', body)

        # Clean title
        title = self._get_nested(record, 'metadata.title')
        if title:
            cleaned_title = self.emoji_pattern.sub('', title)
            self._set_nested(record, 'metadata.title', cleaned_title)

        return record
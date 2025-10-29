"""
Title site template removal
"""
import re
from .base import BaseCleaner


class TitleSiteTemplateCleaner(BaseCleaner):
    @property
    def name(self):
        return 'title_site_template'

    def __init__(self, params, config):
        super().__init__(params, config)

        # Common title separators
        self.separators = [' | ', ' - ', ' :: ', ' — ', ' – ', ' > ']

        # Patterns for common site name templates
        self.template_patterns = [
            re.compile(r'\s*[\|\-–—]\s*[^|\-–—]+$'),  # "Title - SiteName"
            re.compile(r'^\s*[^|\-–—]+\s*[\|\-–—]\s*'),  # "SiteName | Title"
        ]

    def clean(self, record):
        """Remove site name templates from title"""
        title = self._get_nested(record, 'metadata.title')
        sitename = self._get_nested(record, 'metadata.sitename')

        if not title:
            return record

        cleaned_title = title

        # If sitename is known, remove it explicitly
        if sitename:
            for sep in self.separators:
                # Remove "Title | SiteName"
                suffix = f"{sep}{sitename}"
                if cleaned_title.endswith(suffix):
                    cleaned_title = cleaned_title[:-len(suffix)].strip()
                    break

                # Remove "SiteName | Title"
                prefix = f"{sitename}{sep}"
                if cleaned_title.startswith(prefix):
                    cleaned_title = cleaned_title[len(prefix):].strip()
                    break

        # Generic template removal (last segment after separator)
        # Only if title is long enough and has separator
        if len(cleaned_title) > 30:
            for sep in self.separators:
                if sep in cleaned_title:
                    parts = cleaned_title.split(sep)
                    if len(parts) >= 2:
                        # Check if last part looks like a site name (short, capitalized)
                        last_part = parts[-1].strip()
                        if len(last_part) < 30 and last_part[0].isupper():
                            cleaned_title = sep.join(parts[:-1]).strip()
                            break

        self._set_nested(record, 'metadata.title', cleaned_title)
        return record
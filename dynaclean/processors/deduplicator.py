"""
URL-based deduplicator
"""


class Deduplicator:
    def __init__(self):
        self.seen_urls = set()

    def is_duplicate(self, url):
        """Check if URL has been seen"""
        if not url:
            return False

        normalized_url = self._normalize_url(url)
        return normalized_url in self.seen_urls

    def add(self, url):
        """Add URL to seen set"""
        if url:
            normalized_url = self._normalize_url(url)
            self.seen_urls.add(normalized_url)

    def _normalize_url(self, url):
        """Normalize URL for comparison"""
        # Remove trailing slashes, convert to lowercase
        url = url.lower().strip()
        if url.endswith('/'):
            url = url[:-1]
        return url

    def reset(self):
        """Reset seen URLs (for new file)"""
        self.seen_urls.clear()
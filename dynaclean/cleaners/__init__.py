"""
Cleaner factory and registry
"""
from .url_dedupe import UrlDedupeCleaner
from .html_body import HtmlBodyCleaner
from .emoji import EmojiCleaner
from .anonymization import AnonymizationCleaner
from .non_latin import NonLatinCleaner
from .whitespace import WhitespaceCleaner
from .zero_width_space import ZeroWidthSpaceCleaner
from .html_unescape import HtmlUnescapeCleaner
from .title_site_template import TitleSiteTemplateCleaner
from .english_only import EnglishOnlyCleaner


class CleanerFactory:
    _registry = {
        'url_dedupe_and_filtering': UrlDedupeCleaner,
        'html_body_cleaning': HtmlBodyCleaner,
        'emoji_cleaning': EmojiCleaner,
        'anonymization': AnonymizationCleaner,
        'non_latin': NonLatinCleaner,
        'whitespace': WhitespaceCleaner,
        'zero_width_space': ZeroWidthSpaceCleaner,
        'html_unescape': HtmlUnescapeCleaner,
        'title_site_template': TitleSiteTemplateCleaner,
        'english_only_filter': EnglishOnlyCleaner
    }

    @classmethod
    def create(cls, name, params, config):
        """Create cleaner instance"""
        if name not in cls._registry:
            raise ValueError(f"Unknown cleaner: {name}")

        cleaner_class = cls._registry[name]
        return cleaner_class(params, config)

    @classmethod
    def register(cls, name, cleaner_class):
        """Register a new cleaner"""
        cls._registry[name] = cleaner_class
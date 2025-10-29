"""
HTML body cleaning using trafilatura
"""
from .base import BaseCleaner

try:
    from trafilatura import extract
    from trafilatura.settings import use_config

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    print("Warning: trafilatura not installed. HTML cleaning will be basic.")

from lxml import html as lxml_html
from lxml.html.clean import Cleaner


class HtmlBodyCleaner(BaseCleaner):
    @property
    def name(self):
        return 'html_body_cleaning'

    def __init__(self, params, config):
        super().__init__(params, config)

        self.use_trafilatura = TRAFILATURA_AVAILABLE
        self.retain_table = params.get('retain_table', True)
        self.retain_image = params.get('retain_image', True)
        self.body_xpath = params.get('body_xpath', None)

        # Default noise elements
        self.default_noises = [
            "//script",
            "//style",
            "//head",
            "//footer",
            "//header",
            "//nav",
            "//aside",
            "//form",
            "//input",
            "//button"
        ]

        # Get noise filters
        use_default = params.get('use_default_noises', True)
        custom_noises = params.get('noises', [])

        if use_default:
            self.noises = self.default_noises + custom_noises
        else:
            self.noises = custom_noises

    def clean(self, record):
        """Clean HTML body"""
        body = record.get('body', '')

        if not body:
            return record

        try:
            if self.use_trafilatura:
                cleaned = self._clean_with_trafilatura(body)
            else:
                cleaned = self._clean_with_lxml(body)

            # Update body
            record['body'] = cleaned if cleaned else body

        except Exception as e:
            self.logger.error(f"HTML cleaning failed: {e}")
            # Keep original body on error

        return record

    def _clean_with_trafilatura(self, html_content):
        """Clean using trafilatura"""
        try:
            # Configure trafilatura
            config = use_config()
            config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

            # Extract main content
            extracted = extract(
                html_content,
                include_tables=self.retain_table,
                include_images=self.retain_image,
                include_links=False,
                no_fallback=False,
                config=config
            )

            return extracted
        except Exception as e:
            self.logger.warning(f"Trafilatura extraction failed: {e}, falling back to lxml")
            return self._clean_with_lxml(html_content)

    def _clean_with_lxml(self, html_content):
        """Fallback cleaning with lxml"""
        try:
            doc = lxml_html.fromstring(html_content)

            # Apply custom xpath if specified
            if self.body_xpath:
                elements = doc.xpath(self.body_xpath)
                if elements:
                    doc = elements[0]

            # Remove noise elements
            for noise_xpath in self.noises:
                for element in doc.xpath(noise_xpath):
                    element.getparent().remove(element)

            # Use lxml cleaner
            cleaner = Cleaner(
                scripts=True,
                javascript=True,
                comments=True,
                style=True,
                inline_style=True,
                links=False,
                meta=True,
                page_structure=False,
                processing_instructions=True,
                embedded=True,
                frames=True,
                forms=False if self.retain_image else True,
                annoying_tags=True,
                remove_tags=['script', 'style', 'head'],
                kill_tags=['nav', 'aside', 'header', 'footer']
            )

            cleaned_doc = cleaner.clean_html(doc)
            text = cleaned_doc.text_content()

            return text.strip()

        except Exception as e:
            self.logger.error(f"LXML cleaning failed: {e}")
            return html_content
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy.spiders import CrawlSpider, Rule
import trafilatura
from scrapy.responsetypes import Response
import re
import scrapy
from pathlib import Path
import yaml

from bigdata.items import CrawlItem

DEFAULT_DENY = [
    r'.*\.(css|js|woff|woff2|ttf|eot|svg|png|jpg|jpeg|gif|ico|pdf|zip|gz|tar)$',
    r'.*/wp-admin/.*',
    r'.*/admin/.*',
    r'.*/login.*',
    r'.*/logout.*',
    r'.*/register.*',
    r'.*/auth.*',
    r'.*/authentication.*',
    r'.*/account.*',
    r'.*/my-account.*',
    r'.*/profile.*',
    r'.*/user.*',
    r'.*/member.*',
    r'.*/dashboard.*',
    r'.*/cart.*',
    r'.*/checkout.*',
    r'.*/shop.*',
    r'.*/shopping.*',
    r'.*/promo.*',
    r'.*/store.*',
    r'.*/disclosure.*',
    r'.*/press.*',
    r'.*/buy.*',
    r'.*/faq.*',
    r'.*/purchase.*',
    r'.*/payment.*',
    r'.*/order.*',
    r'.*/wp-login.*',
    r'.*/wp-content.*',
    r'.*/author.*',
    r'.*/contributor.*',
    r'.*/writer.*',
    r'.*/cdn-cgi.*',
    r'.*/_next.*',
    r'.*/_static.*',
    r'.*/_asset.*',
    r'.*/static.*',
    r'.*/about.*',
    r'.*/contact.*',
    r'.*/privacy.*',
    r'.*/terms.*',
    r'.*/legal.*',
    r'.*/jobs.*',
    r'.*newsletter.*',
    r'.*/subscribe.*',
    r'.*/email.*',
    r'.*/recetas.*',
    r'.*/unsubscribe.*',
    r'.*/comment.*',
    r'.*/#comment.*',
    r'.*/share.*',
    r'.*print.*',
    r'.*/redirect.*',
    r'.*/track.*',
    r'.*/click.*',
    r'.*/?\?s=.*',
    r'.*/?\?reply=.*',
    r'.*/exit.*',
    r'.*/media.*',
    r'.*/images.*',
    r'.*/img.*',
    r'/wp-admin/cookies/',
    r'/wp-admin/wp-admin/',
    r'.*/photos.*',
    r'.*/picture.*',
    r'.*/product.*',
    r'.*/search.*',
    r'.*%5C.*',
    r'/cookies/.*wp-admin',
    r'.*\\.*',
    r'.*/video.*',
    r'.*/_p.*',
    r'.*/join.*',
    r'.*/log-in.*',
    r'.*/get-in-touch.*',
    r'.*/internships.*',
    r'.*cookbook.*',
    r'.*vlog.*',
    r'.*/wp-json.*',
    r'.*/api/?$',
    r'.*/api/api.*',
    r'.*/API/API.*.*',
    r'.*/API.*.*',
    r'.*/logging.*',
    r'.*/new-here.*',
    r'.*/subscription.*',
    r'.*/advert.*',
    r'.*advertising.*',
    r'.*/ads.*',
    r'.*/sponsor.*',
    r'.*/connect.*',
    r'.*/contest.*',
    r'.*/service.*',
    r'.*/course.*',
    r'.*/find.*',
    r'.*/scholarship.*',
    r'.*\?print$',
]

DEFAULT_URL_FILTERS = [
    # Navigation pages
    r'/about/?$',
    r'/contact/?$',
    r'/privacy/?$',
    r'/terms/?$',
    r'/disclaimer/?$',
    r'/cookie[s]?/?$',
    r'/legal/?$',
    r'/sitemap/?$',
    # Homepage/root
    r'^https?://[^/]+/?$',
    # Pagination
    r'[?&]page=\d+',
    r'[?&]p=\d+',
    r'/page/\d+/?$',
    r'/p/\d+/?$',
    r'[?&]s=',
    r'[?&]search=',
    r'[?&]q=',
    r'[?&]query=',
    r'[?&]filter=',
    r'[?&]sort=',
    r'[?&]category=',
    r'[?&]tag=',
    # File extensions (non-HTML)
    r'\.(js|css|json|xml|txt|pdf|zip|gz|tar|jpg|jpeg|png|gif|svg|ico|woff|woff2|ttf|eot)$',
    # Feed/API endpoints
    r'/feed/?$',
    r'/rss/?$',
    r'/atom/?$',
    r'/api/',
    r'\.json$',
    r'\.xml$',
    # Auth/account pages
    r'/login/?$',
    r'/signin/?$',
    r'/signup/?$',
    r'/register/?$',
    r'/logout/?$',
    r'/account/?$',
    r'/profile/?$',
    r'/settings/?$',
    # Admin/backend
    r'/admin/',
    r'/wp-admin/',
    r'/dashboard/?$',
    # Common non-content paths
    r'/tag/',
    r'/tags/?$',
    r'/category/?$',
    r'/categories/?$',
    r'/author/',
    r'/archive/?$',
    r'/search/?$',
]

class UniversalSpider(CrawlSpider):

    name = 'universal'
    allowed_domains = []
    restrict_xpaths = []
    allow = []
    deny = []
    seeds = []
    deny_extensions = []
    bypass_cf = False
    use_proxy = False
    use_playwright = False

    def __init__(self, domain=None, config_file='site_cfg.yaml', *args, **kwargs):
        """
        Initialize spider with optional domain parameter.
        If domain is provided, load configuration from YAML file.
        """
        self.domain = domain
        self.config_file = config_file
        self._domain_settings = {}  # Store settings to apply later
        if domain:
            self._load_domain_config(domain)

        # Build deny list
        denies = DEFAULT_DENY.copy()
        denies.extend(self.deny)

        # Setup rules
        self.rules = [
            Rule(LxmlLinkExtractor(
                allow_domains=self.allowed_domains,
                restrict_xpaths=self.restrict_xpaths,
                allow=self.allow,
                deny=denies,
                deny_extensions=self.deny_extensions),
                process_request=self._apply_request_meta,
                callback=self.parse_response,
                follow=True),
        ]

        super().__init__(*args, **kwargs)

    @classmethod
    def update_settings(cls, settings):
        """
        Override this method to apply domain-specific settings.
        This is called by Scrapy before the spider is instantiated.
        """
        super().update_settings(settings)

        # Get domain and config from spider arguments
        # Note: These come from the crawler arguments
        if hasattr(cls, '_temp_domain_settings'):
            for key, value in cls._temp_domain_settings.items():
                settings.set(key, value)

    def _load_domain_config(self, domain):
        """Load domain-specific configuration from YAML file"""
        config_path = Path(self.config_file)

        if not config_path.exists():
            self.logger.warning(f'Config file {self.config_file} not found. Using defaults.')
            return

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        if 'domains' not in config or domain not in config['domains']:
            self.logger.warning(f'Domain {domain} not found in config. Using defaults.')
            return

        domain_config = config['domains'][domain]

        # Load basic settings
        self.allowed_domains = domain_config.get('allowed_domains', [domain])
        self.start_urls = domain_config.get('start_urls', [f'https://{domain}/'])

        # Load link extraction rules
        self.allow = domain_config.get('allow', [])
        self.deny = domain_config.get('deny', [])
        self.restrict_xpaths = domain_config.get('restrict_xpaths', [])
        self.deny_extensions = domain_config.get('deny_extensions', [])

        # Load connection settings
        self.bypass_cf = domain_config.get('bypass_cf', False)
        self.use_proxy = domain_config.get('use_proxy', False)
        self.use_playwright = domain_config.get('use_playwright', False)

        # Load custom spider settings
        if 'settings' in domain_config:
            self.custom_settings = domain_config['settings']
            self.__class__._temp_domain_settings = self._domain_settings

        self.logger.info(f'Loaded configuration for domain: {domain}')
        self.logger.info(f'Start URLs: {self.start_urls} | Allowed domains : {self.allowed_domains} | Custom Settings: {self.custom_settings}')
        self.logger.info(f'Proxy: {self.use_proxy}, CF Bypass: {self.bypass_cf}, Playwright: {self.use_playwright}')

    async def start(self):
        self.seeds = self.seeds or self.start_urls
        for seed in self.seeds:
            yield scrapy.Request(seed,
                                 meta={'bypass_cf': self.bypass_cf,
                                       'use_proxy': self.use_proxy,
                                       'playwright': self.use_playwright,
                                       'playwright_page_goto_kwargs': {
                                           'wait_until': 'domcontentloaded',
                                       }},
                                 callback=self._parse)

    def _apply_playwright_meta(self, request):
        request.meta['playwright'] = True
        request.meta['playwright_page_goto_kwargs'] = {
            'wait_until': 'domcontentloaded',
        }

    def _apply_request_meta(self, request, response):
        """Apply domain-specific configuration to request"""
        if self.bypass_cf:
            request.meta['bypass_cf'] = True
        if self.use_proxy:
            request.meta['use_proxy'] = True
        if self.use_playwright:
            self._apply_playwright_meta(request)
        return request

    def get_and_set_metadata(self, response: Response):
        metadata = (trafilatura
                    .extract_metadata(response.text,
                                      default_url=response.url)
                    .as_dict())
        metadata['body_type'] = 'html'
        if cs := response.meta.get('content_subdomain'):
            metadata['content_subdomain'] = cs
        if cd := response.meta.get('content_domain'):
            metadata['content_domain'] = cd
        return metadata

    def should_skip_content(self, response):
        url = response.url
        for pattern in DEFAULT_URL_FILTERS:
            if re.search(pattern, url, re.IGNORECASE):
                return True, f"default_filter:{pattern}"
        return False

    def parse_response(self, response: Response):
        """Parse and yield article content"""

        if self.should_skip_content(response):
            self.logger.info(f'Skipping navigation: {response.url} ❌')
            return

        metadata = self.get_and_set_metadata(response)
        body = response.text

        # Additional validation: check if trafilatura found a title
        if not metadata.get('title'):
            self.logger.info(f'No title found, skipping: {response.url} ❌')
            return

        self.logger.info(f'Yielding {metadata.get("title")} on: {response.url} ✅')
        yield CrawlItem(
            meta=metadata,
            body=body
        )
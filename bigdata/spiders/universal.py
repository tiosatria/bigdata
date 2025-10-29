from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.responsetypes import Response
import scrapy
from pathlib import Path
import yaml
import uuid

from bigdata.items import CrawlItem

DEFAULT_DENY = [
    r'.*\.(css|js|woff|woff2|ttf|eot|svg|png|jpg|jpeg|gif|ico|pdf|zip|gz|tar)$',
    r'.*/wp-admin/.*',
    r'.*/admin/.*',
    r'https?://stage\.',
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
    r'.*comment.*',
    r'.*Comment.*',
    r'\?reply.+\='
    r'.*share.*',
    r'.*Share.*',
    r'.*print.*',
    r'.*Print.*',
    r'.*/redirect.*',
    r'.*/track.*',
    r'.*editorial.*',
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
    r'.*podcast.*',
    r'.*/contest.*',
    r'.*/service.*',
    r'.*/course.*',
    r'.*/find.*',
    r'.*password.*',
    r'.*/scholarship.*',
    r'.*\?print$',
]

DEFAULT_URL_FILTERS = [
    # Navigation pages
    r'/about/?$',
    r'/contact/?',
    r'/privacy/?',
    r'/terms/?',
    r'/disclaimer/?',
    r'/cookie[s]?/?$',
    r'/\..*',
    r'/#.*',
    r'\?.+=',
    r'/legal/?',
    r'/sitemap/?',
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
    r'/feed/?',
    r'/rss/?',
    r'/atom/?',
    r'/api/?',
    r'\.json$',
    r'\.xml$',
    # Auth/account pages
    r'/login/?',
    r'/signin/?',
    r'/signup/?',
    r'/register/?',
    r'/logout/?',
    r'/account/?',
    r'/profile/?',
    r'/settings/?',
    # Admin/backend
    r'/admin/',
    r'/wp-admin/',
    r'/dashboard/?',
    # Common non-content paths
    r'/tag/',
    r'/tags/?',
    r'/category/?',
    r'/categories/?',
    r'/author/',
    r'/archive/?',
    r'/search/?',
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
        self.name = domain
        self.config_file = config_file
        self._domain_settings = {}
        if domain:
            self._load_domain_config(domain)

        # Setup rules
        self.rules = [
            Rule(LxmlLinkExtractor(
                allow_domains=self.allowed_domains,
                restrict_xpaths=self.restrict_xpaths,
                allow=self.allow,
                deny=DEFAULT_DENY+self.deny,
                deny_extensions=self.deny_extensions),
                process_request=self._apply_request_meta,
                callback=self.parse_response,
                follow=True),
        ]

        super().__init__(*args, **kwargs)

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
        if not domain_config.get('allow_query_params', True):
            self.deny.append(r'[?&].+')
        self.restrict_xpaths = domain_config.get('restrict_xpaths', [])
        self.deny_extensions = domain_config.get('deny_extensions', [])

        # Load connection settings
        self.bypass_cf = domain_config.get('bypass_cf', False)
        self.use_proxy = domain_config.get('use_proxy', False)
        self.use_playwright = domain_config.get('use_playwright', False)

        self.logger.info(f'Loaded configuration for domain: {domain}')
        self.logger.info(f'Start URLs: {self.start_urls} | Allowed domains : {self.allowed_domains} | Custom Settings: {domain_config.get("custom_settings", {})}')
        self.logger.info(f'Proxy: {self.use_proxy}, CF Bypass: {self.bypass_cf}, Playwright: {self.use_playwright}')

    async def start(self):
        self.seeds = self.seeds or self.start_urls
        for seed in self.seeds:
            yield scrapy.Request(seed,
                                 meta={'bypass_cf': self.bypass_cf,
                                       'use_proxy': self.use_proxy,
                                       'playwright': self.use_playwright,
                                       'is_start_url': True,
                                       'playwright_page_goto_kwargs': {
                                           'wait_until': 'domcontentloaded',
                                       }}, dont_filter=True,
                                 callback=self.parse_response)

    def _apply_playwright_meta(self, request):
        request.meta['playwright'] = True
        request.meta['playwright_page_goto_kwargs'] = {
            'wait_until': 'domcontentloaded',}

    def _apply_request_meta(self, request, response):
        """Apply domain-specific configuration to request"""
        # if parse_url(request.url).netloc.replace('www.','') not in self.allowed_domains:
        #     self.logger.warning(
        #         f'Request to {request.url} is not allowed by domain settings. ❌')
        #     raise IgnoreRequest
        if self.bypass_cf:
            request.meta['bypass_cf'] = True
        if self.use_proxy:
            request.meta['use_proxy'] = True
        if self.use_playwright:
            self._apply_playwright_meta(request)
        return request

    async def parse_response(self, response: Response):
        """Parse and yield article content"""

        async for item in self._parse(response):
            yield item

        body = response.text

        meta = response.meta
        meta['site'] = self.domain
        meta['body_type'] = 'html'

        self.logger.info(f'Yielding from {response.url} ✅')

        yield CrawlItem(
            url = response.url,
            id=uuid.uuid4(),
            meta=meta,
            body=body
        )
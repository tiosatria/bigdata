
OBVIOUS_EXCLUDES_LIST = [
    "//script",
    "//style",
    "//svg",
    "//noscript",
    "//*[contains(@class,'ads')]",
    "//*[contains(@class,'advertisement')]",
    "//aside",
    "//nav",
    "//footer[contains(@class,'footer')]",
    "//div[contains(@class,'social-share')]",
    "//div[contains(@class,'newsletter')]",
    "//div[contains(@class,'popup')]",
    "//div[contains(@class,'modal')]",
    "//iframe",
    "//*[contains(@class,'related')]",
    "//*[contains(@class,'see-also')]",
    "//*[@role='complementary']",
    "//*[contains(@class,'sidebar')]",
    "//*[contains(@class,'widget')]",
]

DENY_URL_REGEX_LIST = [
    # Authentication and user management
    r'https?://auth\.[^/]+',
    r'https?://login\.[^/]+',
    r'https?://signin\.[^/]+',
    r'https?://account\.[^/]+',
    r'https?://my\.[^/]+',
    r'https?://profile\.[^/]+',
    r'https?://user\.[^/]+',
    r'.*/login[/-]?',
    r'.*/signin[/-]?',
    r'.*/signup[/-]?',
    r'.*/register[/-]?',
    r'.*/logout[/-]?',
    r'.*/account[/-]',
    r'.*/profile[/-]',

    # E-commerce
    r'https?://shop\.[^/]+',
    r'https?://store\.[^/]+',
    r'https?://cart\.[^/]+',
    r'https?://checkout\.[^/]+',
    r'https?://product\.[^/]+',
    r'.*/shop[/-]',
    r'.*/store[/-]',
    r'.*/cart[/-]?',
    r'.*/checkout[/-]?',
    r'.*/products?[/-]',
    r'.*/buy[/-]',
    r'.*/order[/-]',

    # Staging and development
    r'https?://stage\.[^/]+',
    r'https?://staging\.[^/]+',
    r'https?://dev\.[^/]+',
    r'https?://test\.[^/]+',
    r'https?://demo\.[^/]+',
    r'https?://beta\.[^/]+',
    r'https?://preview\.[^/]+',

    # Legal and compliance
    r'https?://dsar\.[^/]+',
    r'.*/privacy[/-]?',
    r'.*/terms[/-]?',
    r'.*/conditions[/-]?',
    r'.*/cookie[/-]?',
    r'.*/gdpr[/-]?',
    r'.*/legal[/-]?',
    r'.*/disclaimer[/-]?',
    r'.*/policy[/-]?',

    # Company pages
    r'.*/contact[/-]?',
    r'.*/about[/-]?',
    r'.*/team[/-]?',
    r'.*/careers[/-]?',
    r'.*/jobs[/-]?',
    r'.*/press[/-]?',
    r'.*/advertise[/-]?',

    # User-generated content (non-article)
    r'.*/comment[/-]',
    r'.*/reply[/-]',
    r'.*/forum[/-]',

    # Functional pages
    r'.*/subscribe[/-]?',
    r'.*/unsubscribe[/-]?',
    r'.*/newsletter[/-]?',

    # Admin and backend
    r'https?://admin\.[^/]+',
    r'.*/admin[/-]',
    r'.*/wp-admin[/-]',
    r'.*/dashboard[/-]',
    r'.*/backend[/-]',

    # Tracking and analytics
    r'.*/track[/-]?',
    r'.*/analytics[/-]?',
    r'.*/pixel[/-]?',
    r'.*/beacon[/-]?',
]


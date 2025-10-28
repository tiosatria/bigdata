from typing import AsyncIterator, Any

import scrapy
from scrapy.http import Response
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor


"""
await fetch("https://www.hercampus.com/wp-admin/admin-ajax.php", {
    "credentials": "omit",
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-GPC": "1",
        "Alt-Used": "www.hercampus.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0"
    },
    "referrer": "https://www.hercampus.com/style/",
    "body": "page=1&catID=40&excludeIDs=%5B1992516%2C1990252%2C1974952%2C1989733%2C1980833%2C2003317%2C1986432%2C1955730%2C1951096%2C1945317%2C1928814%2C1928687%2C2003660%2C2003424%2C1987434%2C1988493%2C1959925%2C994785%2C993583%2C993373%2C996394%2C992352%2C990794%2C987419%2C899494%2C861077%2C872454%2C871884%2C988877%2C862131%2C913276%2C764856%5D&action=hercampus_loadmore_feed",
    "method": "POST",
    "mode": "cors"
});

await fetch("https://www.hercampus.com/wp-admin/admin-ajax.php", {
    "credentials": "omit",
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-GPC": "1",
        "Alt-Used": "www.hercampus.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0"
    },
    "referrer": "https://www.hercampus.com/life/",
    "body": "page=1&catID=9&excludeIDs=%5B1999896%2C1998911%2C1990280%2C1998232%2C1986646%2C1996939%2C1997176%2C1990497%2C1988319%2C1969315%2C1967263%2C1967230%2C1960020%2C1955403%2C1927944%2C1865627%2C1862916%2C1851767%2C930667%2C922823%2C925408%2C900868%2C889976%2C990914%2C699291%2C765996%2C367605%2C331939%2C986462%2C973981%2C232999%2C266052%2C237864%5D&action=hercampus_loadmore_feed",
    "method": "POST",
    "mode": "cors"
});

await fetch("https://www.hercampus.com/wp-admin/admin-ajax.php", {
    "credentials": "omit",
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-GPC": "1",
        "Alt-Used": "www.hercampus.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0"
    },
    "referrer": "https://www.hercampus.com/career/",
    "body": "page=1&catID=37&excludeIDs=%5B1990794%2C1977080%2C1981170%2C1979740%2C1966077%2C1956584%2C1941136%2C1965325%2C1924292%2C1920082%2C1908943%2C1892569%2C1935835%2C1926434%2C1915075%2C1892611%2C1%2C982605%2C987717%2C971745%2C950378%2C958038%2C994703%2C879704%2C991330%2C425705%2C993662%2C994180%2C991724%2C277899%2C991591%2C993582%5D&action=hercampus_loadmore_feed",
    "method": "POST",
    "mode": "cors"
});

"""

class HerCampusSpider(scrapy.Spider):

    name = "hercampus"
    allowed_domains = ["hercampus.com"]

    custom_settings = {
        'LOG_LEVEL': 'DEBUG'
    }

    wellness_dict = {

    }

    @staticmethod
    def create_request_dict(**kwargs):

        page = kwargs.get('page', 1)
        catID = kwargs.get('catID', 43)


        form_data = {
            'page': '1',
            'catID': '43',
            'excludeIDs': '[1986300,2001749,1986431,1958058,1954571,1944891,1941074,1933656,1929122,1998268,1975197,1976842,1975643,1986845,1977004,1965492,1951329,988224,989370,986181,981926,961664,991355,987546,984167,990979,991060,988410,989050,990550,991064]',
            'action': 'hercampus_loadmore_feed'
        }

        return form_data

    async def start(self) -> AsyncIterator[Any]:

        form_data = {
            'page': '1',
            'catID': '43',
            'excludeIDs': '[1986300,2001749,1986431,1958058,1954571,1944891,1941074,1933656,1929122,1998268,1975197,1976842,1975643,1986845,1977004,1965492,1951329,988224,989370,986181,981926,961664,991355,987546,984167,990979,991060,988410,989050,990550,991064]',
            'action': 'hercampus_loadmore_feed'
        }

        yield scrapy.FormRequest(
            url="https://www.hercampus.com/wp-admin/admin-ajax.php",
            method='POST',
            formdata=form_data,
            callback=self.parse_data
        )

    def parse_data(self, response:Response):
        self.logger.info(f"Parsing {response.url}")
        LxmlLinkExtractor(restrict_xpaths="//div[@class='site-inner']/ul",
                          allow_domains=["hercampus.com"]).extract_links(response)


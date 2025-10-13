# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

class ProxyMiddleware:
    def process_request(self, request, spider):
        request.meta['proxy'] = 'http://icpjabta-rotate:v3cylfcqz2p5@p.webshare.io:80'
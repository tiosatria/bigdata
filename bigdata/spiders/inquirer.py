from typing import AsyncIterator, Any

import scrapy


class InquirerSpider(scrapy.Spider):

    name = 'inquirer'
    allowed_domains = ['inquirer.com']

    seeds = [

    ]


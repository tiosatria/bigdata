from abc import ABC
from typing import Optional, Union, Iterable

from bs4 import BeautifulSoup
from lxml import html as lxml_html

import trafilatura

class TagCleaner:

    def clean(self, content:Iterable[str])->Iterable[str]:
        cleaned_tags = []
        for tag in content:
            cleaned_tags.append(tag.strip())
        return cleaned_tags

class HtmlTagCleaner(TagCleaner):

    def clean(self, content:Iterable[str]):
        cleaned_tags = []
        for tag in content:
            try:
                soup = BeautifulSoup(tag, 'html.parser')
                cleaned_tags.append(soup.get_text().strip())
            except:
                cleaned_tags.append(tag.strip())
        return cleaned_tags

class Cleaner(ABC):

    def clean(self, content: str):
        return content

class HtmlCleaner(Cleaner):

    def __init__(self, prune_xpath=None,
                 end_marker:Optional[str]=None, include_image:bool=False):
        self.prune_xpath = prune_xpath
        self.end_marker = end_marker
        self.include_image = include_image

    def clean(self, content:str):
        html=content
        try:
            doc = lxml_html.fromstring(html)
            if self.end_marker:
                end_marker = doc.xpath(self.end_marker)
                if end_marker:
                    target = end_marker[0]
                    parent = target.getparent()
                    # remove everything after this div in the same parent
                    remove = False
                    for child in list(parent):
                        if remove:
                            parent.remove(child)
                        elif child is target:
                            remove = True
                html = lxml_html.tostring(doc, encoding="unicode")
            return trafilatura.extract(html,
                                prune_xpath=self.prune_xpath,
                                include_images=self.include_image)
        except:
            return content

class CleaningPipeline:

    text_cleaners:Optional[list[Cleaner]]=None
    title_cleaners:Optional[list[Cleaner]]=None
    tags_cleaners:Optional[list[TagCleaner]]=None

    def __init__(self, text_cleaners:Optional[list[Cleaner]]=None,
                 title_cleaners: Optional[list[Cleaner]]=None,
                 tags_cleaners: Optional[list[TagCleaner]]=None
                 ):
        self.text_cleaners = text_cleaners
        self.title_cleaners = title_cleaners
        self.tags_cleaners = tags_cleaners

    def process_item(self, item:dict):
        if self.text_cleaners:
            for cleaner in self.text_cleaners:
                item['body'] = cleaner.clean(item['body'])

        if self.title_cleaners:
            for cleaner in self.title_cleaners:
                item['title'] = cleaner.clean(item['title'])

        if self.tags_cleaners:
            for cleaner in self.tags_cleaners:
                item['tags'] = cleaner.clean(item['tags'])

        return item
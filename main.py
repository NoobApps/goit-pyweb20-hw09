import scrapy
from scrapy.crawler import CrawlerProcess
import os
from dotenv import load_dotenv
from mongoengine import connect, Document, StringField, DateField, ReferenceField, ListField
import json
from datetime import datetime


load_dotenv()
MONGO_URI = os.environ.get("MONGO_URI")

if MONGO_URI:
    connect(host=MONGO_URI)
else:
    raise EnvironmentError("MONGO_URI environment variable not set. Cannot connect to MongoDB.")


class Author(Document):
    fullname = StringField(max_length=50, required=True, unique=True)
    born_date = DateField(required=True)
    born_location = StringField(max_length=100, required=True)
    description = StringField(required=True)
    meta = {'collection': 'authors'}


class Quote(Document):
    tags = ListField(StringField(max_length=100))
    author = ReferenceField('Author', required=True)
    quote = StringField(required=True)
    meta = {'collection': 'quotes'}


class AuthorsSpider(scrapy.Spider):
    name = 'authors_detailed'
    allowed_domains = ['quotes.toscrape.com']
    start_urls = ['http://quotes.toscrape.com']
    
    # Налаштування експорту в JSON
    custom_settings = {
        "LOG_LEVEL": "WARNING",  
        "FEEDS": {
            "authors.json": {
                "format": "json",
                "overwrite": True,
                "encoding": "utf8",
                "indent": 4,
            }
        }
    }

    def parse(self, response):
        """Парсинг головної сторінки з цитатами"""
        for quote in response.xpath("//div[@class='quote']"):
            parsed_authors = []
            author = quote.xpath(".//small[@class='author']/text()").get()
            if author not in parsed_authors:
            # Отримуємо відносне посилання на сторінку автора (лінк "(about)")
                parsed_authors.append(author)
                author_url = quote.xpath(".//span/a/@href").get()

                if author_url:
                    yield response.follow(
                        author_url,
                        callback=self.parse_author
                    )

        # Пагінація: перехід на наступну сторінку з цитатами
            next_link = response.xpath("//li[@class='next']/a/@href").get()
            if next_link:
                yield response.follow(next_link, callback=self.parse)

    def parse_author(self, response):
        """Парсинг сторінки конкретного автора (about)"""
        author_info = {
            "fullname" : response.xpath("//h3[@class='author-title']/text()").get(),
            "born_date": response.xpath("//span[@class='author-born-date']/text()").get(),
            "born_location": response.xpath("//span[@class='author-born-location']/text()").get(),
            "description": response.xpath("//div[@class='author-description']/text()").get("").strip(),
        }

        result = {**author_info}
        yield result


class QuotesSpider(scrapy.Spider):
    name = 'quotes'
    allowed_domains = ['quotes.toscrape.com']
    start_urls = ['http://quotes.toscrape.com']
    
    custom_settings = {
        "LOG_LEVEL": "WARNING",
        "FEEDS": {
            "quotes.json": {
                "format": "json",
                "overwrite": True,
                "encoding": "utf8",
                "indent": 4, 
            }
        }
    }

    def parse(self, response):
        for quote in response.xpath("//div[@class='quote']"):
            item = {
                "author": quote.xpath(".//small[@class='author']/text()").get(),
                "quote": quote.xpath(".//span[@class='text']/text()").get(),
                "tags": quote.xpath(".//div[@class='tags']/a/text()").getall(),
            }
            yield item

        next_link = response.xpath("//li[@class='next']/a/@href").get()
        if next_link:
            yield response.follow(next_link, callback=self.parse)

def load_authors(file_path="authors.json"):
    with open(file_path, "r", encoding="utf-8") as file:
        authors_data = json.load(file)
        
    for item in authors_data:
        author = Author.objects(fullname=item["fullname"]).first()
        if not author:
            author = Author(
                fullname=item.get("fullname"),
                born_date=datetime.strptime(item.get("born_date"), "%B %d, %Y").date(),
                born_location=item.get("born_location"),
                description=item.get("description")
            )
            author.save()
            print(f"Додано автора: {author.fullname}")
        else:
            print(f"Автор вже існує: {author.fullname}")

def load_quotes(file_path="quotes.json"):
    with open(file_path, "r", encoding="utf-8") as file:
        quotes_data = json.load(file)

    for item in quotes_data:
        author_name = item["author"]
        author = Author.objects(fullname=author_name).first()

        if author:
            # Перевірка на наявність такої ж цитати
            existing_quote = Quote.objects(quote=item["quote"]).first()
            if not existing_quote:
                quote = Quote(
                    tags=item.get("tags", []),
                    author=author,
                    quote=item["quote"]
                )
                quote.save()
                print(f"Додано цитату автора: {author.fullname}")
            else:
                print(f"Цитата вже існує в БД")
        else:
            print(f"Помилка: Автора '{author_name}' не знайдено в базі даних!")


if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(AuthorsSpider)
    process.crawl(QuotesSpider)
    process.start()
    load_authors()
    load_quotes()
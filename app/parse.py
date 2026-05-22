import httpx
import csv
import logging

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dataclasses import dataclass, fields, asdict

BASE_URL = "https://quotes.toscrape.com/"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: --- %(message)s ---"
)


@dataclass
class Author:
    name: str
    born: str
    description: str

# in README file not say a structure Quote class
@dataclass
class Quote:
    text: str
    author: Author
    tags: list[str]


def parse_author_page(soup: BeautifulSoup) -> Author:
    about_author = soup.select_one("div.author-details")

    name = about_author.select_one("h3").text

    born_date = about_author.select_one("span.author-born-date").text
    born_location = about_author.select_one("span.author-born-location").text
    born_info = f"{born_date} {born_location}"

    description = about_author.select_one("div.author-description").text.strip()
    author = Author(name=name, born=born_info, description=description)
    return author


def parse_quote_page(
    soup: BeautifulSoup, cached_authors: dict[str, Author], client: httpx.Client
) -> list[Quote]:
    quotes_tags = soup.select("div.quote")

    quotes = []
    for quote_tag in quotes_tags:
        text = quote_tag.select_one("span.text").text
        tags = [tag.text for tag in quote_tag.select("a.tag")]

        author_name = quote_tag.select_one("small.author").text
        author = cached_authors.get(author_name)
        if not author:
            author_path = quote_tag.select_one('a[href^="/author/"]')["href"]
            author_url = urljoin(BASE_URL, f"{author_path.rstrip('/')}/")

            author_res = client.get(author_url)
            author_soup = BeautifulSoup(author_res.text, "html.parser")

            author = parse_author_page(soup=author_soup)
            cached_authors[author_name] = author

        quote = Quote(text=text[1:-1], author=author, tags=tags)
        quotes.append(quote)

    return quotes


def get_url_next_page_or_none(soup: BeautifulSoup) -> str | None:
    a_tag = soup.select_one("li.next > a")
    return a_tag["href"] if a_tag else None


def write_scraped_quotes(quotes: list[Quote], output_csv_path: str) -> None:
    with open(output_csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        rows = [
            field.name.capitalize() for field in fields(Quote) if field.name != "author"
        ]
        author_rows_generator = (
            f"Author {field.name.capitalize()}" for field in fields(Author)
        )
        rows.extend(author_rows_generator)

        writer.writerow(rows)

        def get_quote_write_generator(quotes: list[Quote]) -> list:
            for quote in quotes:
                quote_data: dict = asdict(quote)
                author = quote_data.pop("author")

                to_write = [*quote_data.values(), *author.values()]
                yield to_write

        write_generator = get_quote_write_generator(quotes=quotes)
        writer.writerows(write_generator)


def sync_scraper(output_csv_path: str) -> None:
    parse_url = BASE_URL
    cached_authors = {}

    all_quotes = []
    with httpx.Client() as client:
        while True:
            res = client.get(parse_url)
            soup = BeautifulSoup(res.text, "html.parser")

            quotes = parse_quote_page(
                soup=soup, cached_authors=cached_authors, client=client
            )
            all_quotes.extend(quotes)

            next_page = get_url_next_page_or_none(soup=soup)
            if next_page:
                parse_url = urljoin(BASE_URL, next_page)
            else:
                break

    write_scraped_quotes(quotes=all_quotes, output_csv_path=output_csv_path)


def main(output_csv_path: str) -> None:
    sync_scraper(output_csv_path)


if __name__ == "__main__":
    main("quotes.csv")

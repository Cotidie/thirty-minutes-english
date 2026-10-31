"""What the major outlets lead with right now, from their RSS feeds. Reuters and AP publish none any more. Reading
them all takes a second or two."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

from app import net

log = logging.getLogger(__name__)

WORLD_FEEDS = {
    "BBC": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "The New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Financial Times": "https://www.ft.com/rss/home",
}
KOREA_FEEDS = {
    "Yonhap": "https://en.yna.co.kr/RSS/news.xml",
    "The Korea Herald": "https://www.koreaherald.com/rss/newsAll",
    "The Korea Times": "https://www.koreatimes.co.kr/www/rss/rss.xml",
}
FEEDS = {**WORLD_FEEDS, **KOREA_FEEDS}
TITLES_PER_FEED = 25  # a feed opens with what its outlet leads with
TIMEOUT_S = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; thirty-minutes-english)"}


def titles_in(feed: bytes) -> list[str]:
    titles = (" ".join((item.findtext("title") or "").split()) for item in ElementTree.fromstring(feed).iter("item"))
    return [title for title in titles if title][:TITLES_PER_FEED]


def read_headlines(download: Callable[[str], bytes] | None = None) -> list[str]:
    """One line per headline, marked with its outlet. A feed that fails is left out."""
    download = download or _download

    def lines_of(outlet: str, url: str) -> list[str]:
        try:
            return [f"[{outlet}] {title}" for title in titles_in(download(url))]
        except (net.HttpError, ElementTree.ParseError) as e:
            log.warning("could not read the %s feed: %s", outlet, e)
            return []

    with ThreadPoolExecutor(len(FEEDS)) as pool:
        return [line for lines in pool.map(lambda feed: lines_of(*feed), FEEDS.items()) for line in lines]


def _download(url: str) -> bytes:
    return net.request("GET", url, HEADERS, timeout=TIMEOUT_S, follow_redirects=True).content

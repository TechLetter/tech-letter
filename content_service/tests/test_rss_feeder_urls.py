from __future__ import annotations

import pytest

from content_service.app.rss.feeder import RssFeedItem, fetch_rss_feeds


TEST_RSS_URLS = [
    "https://tech.kakao.com/feed/",
    "https://tech.kakaopay.com/rss",
    "https://d2.naver.com/d2.atom",
    "https://tech.remember.co.kr/feed",
    "https://techblog.gccompany.co.kr/feed",
    "https://medium.com/feed/daangn",
    "https://tech.socarcorp.kr/feed",
    "https://meetup.nhncloud.com/rss",
    "https://helloworld.kurly.com/feed",
    "https://toss.tech/rss.xml",
    "https://medium.com/feed/pinkfong",
    "https://techblog.lycorp.co.jp/ko/feed/index.xml",
    "https://devocean.sk.com/blog/rss.do",
    "https://www.44bits.io/ko/feed/all",
    "https://microservices.io/feed.xml",
    "https://www.uber.com/en-US/blog/engineering/rss/",
    "https://insight.infograb.net/blog/rss.xml",
    "https://tech.inflab.com/rss.xml",
    "https://medium.com/feed/yanoljacloud-tech",
]


@pytest.mark.parametrize("rss_url", TEST_RSS_URLS)
def test_fetch_rss_feeds_returns_items(rss_url: str) -> None:
    items = fetch_rss_feeds(rss_url, limit=10)

    assert isinstance(items, list)
    assert len(items) > 0

    for item in items:
        assert isinstance(item, RssFeedItem)
        assert item.title
        assert item.link

"""Tests for extracting the character id from D&D Beyond URLs."""

import pytest
import tableplop


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dndbeyond.com/characters/41000137",
        "https://www.dndbeyond.com/characters/41000137/",
        "https://www.dndbeyond.com/characters/41000137/Ab3dEf",
        "https://dndbeyond.com/characters/41000137",
        "http://www.dndbeyond.com/characters/41000137?foo=bar",
        "https://www.dndbeyond.com/characters/41000137#top",
        "www.dndbeyond.com/characters/41000137",
        "dndbeyond.com/characters/41000137",
        "  https://WWW.DNDBEYOND.COM/characters/41000137  ",
        "<https://www.dndbeyond.com/characters/41000137>",
        "https://www.dndbeyond.com/profile/SomeUser/characters/41000137",
    ],
)
def test_valid_urls(url: str) -> None:
    assert tableplop.parse_character_url(url) == 41000137


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "41000137",
        "hello",
        "https://www.dndbeyond.com/characters/",
        "https://www.dndbeyond.com/characters/abc",
        "https://www.dndbeyond.com/characters/0",
        "https://www.dndbeyond.com/monsters/41000137",
        "https://www.dndbeyond.com/characters",
        "https://evil.com/www.dndbeyond.com/characters/41000137",
        "https://dndbeyond.com.evil.com/characters/41000137",
        "https://notdndbeyond.com/characters/41000137",
        "ftp://www.dndbeyond.com/characters/41000137",
        "javascript:alert(1)",
    ],
)
def test_invalid_urls(url: str) -> None:
    assert tableplop.parse_character_url(url) is None

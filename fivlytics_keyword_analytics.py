"""Fivlytics (Fiverr) keyword analytics command-line interface.
"""
from dataclasses import dataclass

import fire
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://fivlytics.com/keyword-analytics"


@dataclass
class Tokens:
    xsrf_token: str
    session: str
    csrf_token: str


def get_tokens() -> Tokens:
    response = requests.get(BASE_URL)

    cookies = parse_set_cookie(response.headers["set-cookie"])
    xsrf_token = cookies.get("XSRF-TOKEN")
    session = cookies.get("fivlytics_session")

    soup = BeautifulSoup(response.content, "html.parser")
    csrf_token_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_token = csrf_token_meta.attrs["content"]

    return Tokens(xsrf_token, session, csrf_token)


def parse_set_cookie(set_cookie: str) -> dict:
    results = {}

    for item in set_cookie.split():
        item = item.strip()

        if not item:
            continue
        if "=" not in item:
            results[item] = None
            continue

        name, value = item.split("=", 1)
        results[name] = value

    return results


class LevelCount:
    def __init__(self, data: dict):
        self.no_level: int = data["No Level"]
        self.level_one: int = data["Level One"]
        self.level_two: int = data["Level Two"]
        self.top_rated: int = data["Top Rated"]


class Model:
    def __init__(self, data: dict):
        self.total_gigs: int = data["model"]["total_gigs"]
        self.average_price: float = data["model"]["averagePrice"]
        self.average_rating: float = data["model"]["averageReview"]
        self.level_count = LevelCount(data["model"]["levelCount"])


def get_keyword_analytics(tokens: Tokens, keyword: str) -> Model:
    response = requests.post(
        BASE_URL,
        json={"keyword": keyword},
        headers={
            "Cookie": f"XSRF-TOKEN={tokens.xsrf_token}; fivlytics_session={tokens.session}",
            "X-CSRF-TOKEN": tokens.csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    response.raise_for_status()
    data = response.json()
    return Model(data)


def get_analytics(keyword: str):
    tokens = get_tokens()
    model = get_keyword_analytics(tokens, keyword)

    print("Total gigs:", model.total_gigs)
    print("Average price:", model.average_price)
    print("Average rating:", model.average_rating)
    print(
        f"""Level:
        - Top rated: {model.level_count.top_rated}
        - Level Two: {model.level_count.level_two}
        - Level One: {model.level_count.level_one}
        - No level: {model.level_count.no_level}
        """
    )


if __name__ == "__main__":
    try:
        fire.Fire(get_analytics)
    except Exception as e:
        raise e

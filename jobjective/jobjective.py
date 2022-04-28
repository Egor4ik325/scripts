#!/usr/bin/env python
import re

import requests
from bs4 import BeautifulSoup
from fire import Fire

_session = requests.session()


class BaseProvider:
    """Provider of job information"""

    name: str

    def get_jobs_count(self, query: str) -> int:
        """Return total job count based on provided query."""
        raise NotImplementedError()


class HHProvider(BaseProvider):
    """hh.ru job provider."""

    name = "HH"

    def get_jobs_count(self, query: str) -> int:
        response = _session.get(
            f"https://spb.hh.ru/search/vacancy?text={query}", headers={"user-agent": ""}
        )
        soup = BeautifulSoup(response.content, "html.parser")
        e = soup.find(
            "h1", class_="bloko-header-section-3", attrs={"data-qa": "bloko-header-3"}
        )

        if e is None:
            return 0

        count = ""
        for c in e.text.split():
            if c.isdigit():
                count += c
            else:
                break

        return int(count)


class IndeedProvider(BaseProvider):
    """indeed.com job provider."""

    name = "Indeed"

    def get_jobs_count(self, query: str) -> int:
        response = _session.get(f"https://www.indeed.com/q-{query}-jobs.html")
        soup = BeautifulSoup(response.content, "html.parser")

        e = soup.find(id="searchCountPages")
        if e is None:
            return 0

        search_count_pages = e.text

        match = re.search(r"Page 1 of (.+) jobs", search_count_pages)
        if match is None:
            return 0

        return int(match[1].replace(",", ""))


providers = [HHProvider(), IndeedProvider()]


def main(query: str, query2: str | None = None):
    """Print information about number of jobs according to the query."""

    print(f'Number of jobs for query "{query}":')

    for provider in providers:
        jobs_count = provider.get_jobs_count(query)
        print(f"- {provider.name}: {jobs_count:,} jobs")


if __name__ == "__main__":
    Fire(main)

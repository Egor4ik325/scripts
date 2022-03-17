#!/usr/bin/env python
"""GitHub awesome list sorter.

The problem this script is trying to solve is:
determine the most popular (based on stars) GitHub repositories listed in awesome list
in order to check out them in order of popularity (sorted). Most awesome first.

GitHub API and server implement rate limiting (throttling) of incoming requests and
return appropriate 429: Too many request responses.

The awesome list (index) may have a 1000 or more links to GitHub repositories.

- awesome-selfhosted (939 links)
- awesome-python (600 links) => 15 minutes
- https://github.com/wsvincent/awesome-django

Requirements:

- requests
- 'requests-cache[json]'
- ujson
- aiohttp
- bs4
- fire

Checklist:

- [x] API-based data fetching

- [ ] Data scraping

- [ ] Storing cached data for faster access (index)
"""
import asyncio
from dataclasses import dataclass
from time import sleep
from typing import Iterable, cast

import requests
from aiohttp import ClientResponseError, ClientSession, ClientTimeout, TCPConnector
from bs4 import BeautifulSoup
from bs4.element import Tag
from fire import Fire
from regex import findall
from requests import HTTPError
from requests_cache import CachedSession
from tqdm import tqdm

GITHUB_API_BASE_URL = "https://api.github.com/repos/"
GITHUB_RAW_CONTENT_BASE_URL = "https://raw.githubusercontent.com/"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:95.0) Gecko/20100101 Firefox/95.0"
)


class RepositoryNotFoundError(Exception):
    """Repository not found exception."""  # Information used in repr in console when exception occur

    def __init__(self, repo_fullname: str):
        # For API users to format custom exception
        self.repo_fullname = repo_fullname


class AwesomeReadmeNotFound(Exception):
    """Exception when README.md file was not found in awesome list repository."""


class Repo:
    """Dataclass for repo dict."""

    def __init__(
        self,
        html_url: str,
        full_name: str,
        description: str,
        homepage: str,
        stargazers_count: int,
        default_branch: str,
        **kwargs,
    ) -> None:
        self.html_url = html_url
        self.full_name = full_name
        self.description = description
        self.homepage = homepage
        self.stars = stargazers_count
        self.default_branch = default_branch


@dataclass
class RepoScraped:
    """Struct for scraped repo data."""

    full_name: str
    stars: int

    @property
    def url(self) -> str:
        return get_repo_html_url(self.full_name)


def get_repo_html_url(fullname: str) -> str:
    return f"https://github.com/{fullname}"


def get_repo(fullname: str) -> Repo:
    """Fetch repository details from GitHub API.

    Args:
        fullname: repository fullname (username/reponame)

    Raises:
        RepositoryNotFoundError: Repository not found exception
        Exception: Any other not-handled exception (network, syntax, parsing, ...)

    Returns:
        Repo: detailied repository object
    """
    try:
        response = requests.get(f"{GITHUB_API_BASE_URL}{fullname}")
        response.raise_for_status()  # raise HTTPError on bad response
        repo_dict = response.json()
        return Repo(**repo_dict)
    except Exception as e:
        if isinstance(e, HTTPError):
            if e.response.status_code == 404:
                raise RepositoryNotFoundError(fullname)

        raise e


def get_readme(repo: Repo) -> str:
    """Fetch readme text associated with specific GitHub repository.

    Args:
        repo: GitHub repository object.

    Raises:
        AwesomeReadmeNotFound: If README.md file was not found in the repository.

    Returns:
        str: Text of the repository markdown readme file.
    """
    # Form URL to raw README file (https://raw.githubusercontent.com/Egor4ik325/rankrise/main/README.md)
    repo_readme_url = (
        f"{GITHUB_RAW_CONTENT_BASE_URL}{repo.full_name}/{repo.default_branch}/README.md"
    )

    # Get readme text contents
    try:
        readme_response = requests.get(repo_readme_url)
        readme_response.raise_for_status()
    except HTTPError as e:
        if e.response.status_code == 404:
            raise AwesomeReadmeNotFound
        raise e

    return readme_response.text


def get_repo_fullnames(text: str) -> list[str]:
    """Extract GitHub hyperlink repo full names from the text content.

    Args:
        text: String of text content.

    Returns:
        list[str]: List of repository full names.
    """
    github_repo_regex = r"\(https://github\.com/([^\s/]+?/[^\s/#]+)/?#?.*/?\)"
    return findall(github_repo_regex, text)


async def get_repo_async(session: ClientSession, full_name: str) -> RepoScraped:
    repo_html_url = get_repo_html_url(full_name)

    try:
        async with session.get(repo_html_url, ssl=False) as response:
            repo_html = await response.text()
            soup = BeautifulSoup(repo_html, "html.parser")
            starsElement = cast(Tag, soup.find(id="repo-stars-counter-star"))
            stars = int(cast(str, starsElement["title"]).replace(",", ""))

            return RepoScraped(full_name=full_name, stars=stars)
    except asyncio.TimeoutError:
        return RepoScraped(full_name=full_name, stars=0)
    except ClientResponseError as e:
        if e.status == 404:
            return RepoScraped(full_name=full_name, stars=0)

        if e.status == 429:
            pass

        raise e


async def get_repos_async(full_names: list[str]) -> tuple[RepoScraped]:
    """Fetch repository details based on fullnames (async coroutine)."""
    conn = TCPConnector(limit=None, ttl_dns_cache=300)
    async with ClientSession(
        connector=conn,
        raise_for_status=True,
        timeout=ClientTimeout(total=100),
        headers={"User-Agent": USER_AGENT},
    ) as session:
        return await asyncio.gather(
            *[get_repo_async(session, full_name) for full_name in full_names]
        )


# Synchronous scrape-based repo data fetching
#


def get_repo_scraped(session: CachedSession, full_name: str) -> RepoScraped:
    repo_html_url = get_repo_html_url(full_name)

    try:
        response = session.get(repo_html_url)
        response.raise_for_status()
    except HTTPError as e:
        if e.response.status_code == 429:
            # If too many requests wait 60 seconds and retry request
            sleep(60)
            return get_repo_scraped(session, full_name)

        raise e

    repo_html = response.text
    soup = BeautifulSoup(repo_html, "html.parser")
    starsElement = cast(Tag, soup.find(id="repo-stars-counter-star"))
    stars = int(cast(str, starsElement["title"]).replace(",", ""))

    return RepoScraped(full_name=full_name, stars=stars)


def get_repos_scraped(full_names: list[str]) -> Iterable[RepoScraped]:
    session = CachedSession(
        "github_repos_cache", backend="filesystem", serializer="pickle"
    )

    for full_name in tqdm(full_names):
        try:
            yield get_repo_scraped(session, full_name)
        except HTTPError as e:
            if e.response.status_code == 404:
                continue

            raise e


def get_sorted_awesome_list_repos(repo: str, process_count: int) -> list[RepoScraped]:
    # Get repo fullname
    if repo.startswith("https://github.com/"):
        repo_fullname = repo.removeprefix("https://github.com/")
    else:
        repo_fullname = repo

    # Get repo data object
    repo_object = get_repo(repo_fullname)

    # Get readme contents
    readme_text = get_readme(repo_object)

    # Parse to get all repo fullnames (by github links)
    repo_fullnames = get_repo_fullnames(readme_text)

    # Remove duplicate full names
    repo_fullnames = list(set(repo_fullnames))

    print("Fetching started...")
    if process_count is None:
        repos = get_repos_scraped(repo_fullnames)
    else:
        repos = get_repos_scraped(repo_fullnames[:process_count])

    # Sort repos by stars
    return sorted(repos, key=lambda r: r.stars, reverse=True)


def main(repo: str, count: int = 10, process_count: int = None):
    """Main sorter interface entry point.

    Args:
        repo: GitHub awesome list repo URL (https://github.com/user/repo) or fullname (user/repo).
        count: Number of results printed. Defaults to 10.
        process_count: Number of github repositories index (fetched) to determine stars. Defaults to 100.
        None if not process count limit.
    """
    print("Hi")

    try:
        # Get sorted repos
        repos = get_sorted_awesome_list_repos(repo, process_count)
        # Print enumerated repos to the console
        for i, sorted_repo in enumerate(repos[:count]):
            print(
                f"{i+1:3}. {sorted_repo.stars:<6} ⭐️    {sorted_repo.full_name:<50} ({sorted_repo.url})"
            )
    except RepositoryNotFoundError as e:
        print(f'Sorry, repository "{e.repo_fullname}" was not found.')
    except AwesomeReadmeNotFound:
        print("Sorry, README.md was not found in repo.")


if __name__ == "__main__":
    Fire(main)

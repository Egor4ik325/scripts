"""GitHub awesome list sorter.

The problem this script is trying to solve is:
determine the most popular (based on stars) GitHub repositories listed in awesome list
in order to check out them in order of popularity (sorted). Most awesome first.

The awesome list (index) may have a 1000 or more links to GitHub repositories.

- awesome-selfhosted (939 links)
- awesome-python (600 links)
"""
from asyncore import read
from re import S

import requests
from fire import Fire
from regex import findall
from requests import HTTPError


class RepositoryNotFoundError(Exception):
    """Repository not found exception."""  # Information used in repr in console when exception occur

    def __init__(self, repo_fullname: str):
        # For API users to format custom exception
        self.repo_fullname = repo_fullname


class AwesomeReadmeNotFound(Exception):
    """README.md file was not found in awesome list repository."""


GITHUB_API_BASE_URL = "https://api.github.com/repos/"
GITHUB_RAW_CONTENT_BASE_URL = "https://raw.githubusercontent.com/"


class Repo:
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


def get_repo(fullname: str) -> Repo:
    """Fetch repository details from GitHub API.

    Args:
        fullname: repository fullname (username/reponame)

    Raises:
        RepositoryNotFoundError: Repository not found exception
        Exception: Any other not-handled exception (network, syntactic, parsing, ...)

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


def get_sorted_awesome_list_repos(repo: str, process_count: int) -> list[Repo]:
    # Get repo markdown file
    if repo.startswith("https://github.com/"):
        repo_fullname = repo.removeprefix("https://github.com/")
    else:
        repo_fullname = repo

    repo_object = get_repo(repo_fullname)

    # Get readme contents
    readme_text = get_readme(repo_object)

    # Parse to get all repo fullnames (by github links)
    github_repo_regex = r"\(https://github\.com/([^\s/]+?/[^\s/]+?)/?\)"
    repo_fullnames = findall(github_repo_regex, readme_text)

    print("Fetching started...")
    repos: list[Repo] = []
    for repo_fullname in repo_fullnames[:process_count]:
        # Fetch repository details
        try:
            # Get the number of stars using GitHub API and repository name
            repos.append(get_repo(repo_fullname))
        except RepositoryNotFoundError:
            pass

    # Sort repos by stars
    repos.sort(key=lambda r: r.stars, reverse=True)

    # Return count sorted repos
    return repos


def main(repo: str, count: int = 10, process_count: int = 10):
    """Main sorter interface entry point.

    Args:
        repo: GitHub awesome list repo URL (https://github.com/user/repo) or fullname (user/repo).
        count: Number of results printed. Defaults to 10.
        process_count: Number of github repositories index (fetched) to determine stars. Defaults to 100.
    """
    print("Hi")

    # Get sorted repos
    try:
        repos = get_sorted_awesome_list_repos(repo, process_count)
        # Print enumerated repos to the console
        for i, sorted_repo in enumerate(repos[:count]):
            print(
                f"{i+1:3}. {sorted_repo.stars:<6} ⭐️    {sorted_repo.full_name:<50} ({sorted_repo.html_url})"
            )
    except RepositoryNotFoundError as e:
        print(f'Sorry, repository "{e.repo_fullname}" was not found.')
    except AwesomeReadmeNotFound:
        print("Sorry, README.md was not found for awesome list repo.")


if __name__ == "__main__":
    Fire(main)

from __future__ import annotations

import abc
import dataclasses


@dataclasses.dataclass
class Repository(metaclass=abc.ABCMeta):
    """
    A class for representing spec repositories.
    """

    url: str
    type: str = "unknown"
    name: str | None = None


class UnknownRepository(Repository):
    def formatIssueUrl(self) -> str:  # pylint: disable=unused-argument
        # Dunno how to format an arbitrary issue url,
        # so give up and just point to the repo.
        return self.url


class GithubRepository(Repository):
    def __init__(self, ns: str, user: str, repo: str) -> None:
        super().__init__(
            url=f"https://github.{ns}/{user}/{repo}",
            name=f"{user}/{repo}",
            type="github",
        )
        self.ns = ns
        self.user = user
        self.repo = repo
        if ns == "com":
            self.api = "https://api.github.com"
        else:
            self.api = f"https://github.{ns}/api/v3"

    def formatIssueUrl(self, id: str | None = None) -> str:
        if id is None:
            return f"https://github.{self.ns}/{self.user}/{self.repo}/issues/"
        return f"https://github.{self.ns}/{self.user}/{self.repo}/issues/{id}"

    def __str__(self) -> str:
        assert self.name is not None
        return self.name

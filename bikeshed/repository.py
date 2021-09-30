class Repository:
    """
    A class for representing spec repositories.
    """

    def __init__(self, url, name=None, type=None):
        self.ns = "com"
        self.url = url
        self.api = "https://api.github.com"
        if name:
            self.name = name
        else:
            self.name = url

        if type:
            self.type = type
        else:
            self.type = "unknown"

    def formatIssueUrl(self, *args, **kwargs):  # pylint: disable=unused-argument
        # Dunno how to format an arbitrary issue url,
        # so give up and just point to the repo.
        return self.url


class GithubRepository(Repository):
    def __init__(self, ns, user, repo):
        super().__init__(
            f"https://github.{ns}/{user}/{repo}",
            f"{user}/{repo}",
        )
        self.ns = ns
        self.user = user
        self.repo = repo
        self.type = "github"
        if ns == "com":
            self.api = "https://api.github.com"
        else:
            self.api = f"https://github.{ns}/api/v3"

    def formatIssueUrl(self, id=None):
        if id is None:
            return "https://github.{}/{}/{}/issues/".format(self.ns, self.user, self.repo)
        return "https://github.{}/{}/{}/issues/{}".format(self.ns, self.user, self.repo, id)

    def __str__(self):
        return f"{self.user}/{self.repo}"

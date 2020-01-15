# -*- coding: utf-8 -*-



class Repository(object):
    '''
    A class for representing spec repositories.
    '''

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

    def formatIssueUrl(self, *args, **kwargs):
        # Dunno how to format an arbitrary issue url,
        # so give up and just point to the repo.
        return self.url


class GithubRepository(Repository):
    def __init__(self, ns, user, repo):
        super(GithubRepository, self).__init__("https://github.{0}/{1}/{2}".format(ns, user, repo), "{0}/{1}".format(user, repo))
        self.ns = ns
        self.user = user
        self.repo = repo
        self.type = "github"
        if ns == "com":
            self.api = "https://api.github.com"
        else:
            self.api = "https://github.{0}/api/v3".format(ns)

    def formatIssueUrl(self, id=None):
        if id is None:
            return "https://github.{0}/{1}/{2}/issues/".format(self.ns, self.user, self.repo)
        return "https://github.{0}/{1}/{2}/issues/{3}".format(self.ns, self.user, self.repo, id)

    def __str__(self):
        return "{0}/{1}".format(self.user, self.repo)

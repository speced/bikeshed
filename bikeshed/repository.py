# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals


class Repository(object):
    '''
    A class for representing spec repositories.
    '''

    def __init__(self, url, name=None, type=None):
        self.url = url

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
    def __init__(self, user, repo):
        super(GithubRepository, self).__init__("https://github.com/{0}/{1}".format(user, repo), "{0}/{1}".format(user, repo))
        self.user = user
        self.repo = repo
        self.type = "github"

    def formatIssueUrl(self, id=None):
        if id is None:
            return "https://github.com/{0}/{1}/issues/".format(self.user, self.repo)
        return "https://github.com/{0}/{1}/issues/{2}".format(self.user, self.repo, id)

    def __str__(self):
        return "{0}/{1}".format(self.user, self.repo)

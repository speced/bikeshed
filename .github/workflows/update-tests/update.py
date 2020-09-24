import base64
import fnmatch
import io
import os
import re

from github import Github
from github.GithubException import GithubException


def getData():
    '''
    Parses specs.data into a {orgs: [], moreRepos:[], skipRepos: [], moreFiles: [], skipFiles[]}
    '''
    data = {
        "orgs": [],
        "moreRepos": [],
        "skipRepos": [],
        "moreFiles": [],
        "skipFiles": []
    }
    with io.open("specs.data", "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh.readlines(), 1):
            line = line.strip()
            if line == "":
                # Empty lines are allowed
                continue
            if line.startswith("#"):
                # Comments are allowed
                continue
            match = re.match(r"(\+|-)(org|repo|file):\s*([^\s].*)", line)
            if not match:
                raise Exception(
                    "Line {0} of the specs.data file has bad syntax.".format(i))
            [plusMinus, type, path] = match.groups()
            if type == "org":
                if plusMinus == "-":
                    raise Exception(
                        "Line {0} has a -org, which makes no sense.".format(i))
                data['orgs'].append(path)
            elif type == "repo":
                if plusMinus == "+":
                    storage = data['moreRepos']
                else:
                    storage = data['skipRepos']
                storage.append(path)
            elif type == "file":
                if plusMinus == "+":
                    #storage = data['moreFiles']
                    raise Exception(
                        "Line {0} has a +file, which isn't currently supported.".format(i))
                else:
                    storage = data['skipFiles']
                storage.append(path)
    return data


def reposFromOrg(org, skipRepos=None):
    if skipRepos is None:
        skipRepos = set()
    else:
        skipRepos = set(skipRepos)
    print "Searching {0} org for repositories...".format(org.login)
    for repo in org.get_repos():
        if repo.archived:
            print "  * Skipping archived repo {0}".format(repo.full_name)
            continue
        if repo.full_name in skipRepos:
            print "  * Skipping repo {0}".format(repo.full_name)
            continue
        print "  * Found repo {0}".format(repo.full_name)
        yield repo


def filesFromRepo(repo, skipFiles=None):
    if skipFiles is None:
        skipFiles = set()
    else:
        skipFiles = set(skipFiles)
    print "Searching {0} repo for Bikeshed files...".format(repo.full_name)

    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
    except GithubException as err:
        if err.status == 409:  # "Git Repository is empty"
            return
        raise
    for entry in tree.tree:
        path = repo.full_name+"/"+entry.path
        if any(fnmatch.fnmatch(path, pattern) for pattern in skipFiles):
            print "  * Skipping file {0}".format(entry.path)
            continue
        if entry.type == 'blob' and entry.path.endswith('.bs'):
            print "  * Found file {0}".format(entry.path)
            blob = repo.get_git_blob(entry.sha)
            assert blob.encoding == 'base64'
            text = unicode(base64.b64decode(blob.content), encoding="utf-8")
            yield {"path": path, "text": text}


def processFile(file):
    path = os.path.join('tests', file['path'])
    print "Saving file {0}".format(path)
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with io.open(path, 'w+', encoding="utf-8") as f:
        f.write(file['text'])


def main():
    token = os.environ['GH_TOKEN']
    g = Github(token)
    data = getData()
    repos = []
    for orgName in sorted(data['orgs']):
        org = g.get_organization(orgName)
        repos.extend(reposFromOrg(org, data['skipRepos']))
    for repoName in data['moreRepos']:
        repos.append(g.get_repo(repoName))
    files = []
    for repo in sorted(repos, key=lambda x: x.full_name):
        files.extend(filesFromRepo(repo, data['skipFiles']))
    for file in sorted(files, key=lambda x: x['path']):
        processFile(file)


if __name__ == '__main__':
    main()

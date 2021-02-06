import base64
import fnmatch
import io
import math
import os
import re
import time

from github import Github
from github.GithubException import GithubException


this_dir = os.path.dirname(__file__)
root_dir = os.path.join(
    this_dir,
    "..",
    "..",
    "..",
)


def getData():
    """
    Parses specs.data into a {orgs: [], moreRepos:[], skipRepos: [], moreFiles: [], skipFiles[]}
    """
    data = {
        "orgs": [],
        "moreRepos": [],
        "skipRepos": [],
        "moreFiles": [],
        "skipFiles": [],
    }
    with io.open(os.path.join(this_dir, "specs.data"), "r", encoding="utf-8") as fh:
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
                raise Exception(f"Line {i} of the specs.data file has bad syntax.")
            [plusMinus, type, path] = match.groups()
            if type == "org":
                if plusMinus == "+":
                    data["orgs"].append(path)
                else:
                    raise Exception(f"Line {i} has a -org, which makes no sense.")
            elif type == "repo":
                if plusMinus == "+":
                    storage = data["moreRepos"]
                else:
                    storage = data["skipRepos"]
                storage.append(path)
            elif type == "file":
                if plusMinus == "+":
                    raise Exception(
                        f"Line {i} has a +file, which isn't currently supported."
                    )
                else:
                    storage = data["skipFiles"]
                storage.append(path)
    return data


def reposFromOrg(org, skipRepos=None):
    if skipRepos is None:
        skipRepos = set()
    else:
        skipRepos = set(skipRepos)
    print("Searching {0} org for repositories...".format(org.login))
    for repo in org.get_repos():
        if repo.archived:
            print("  * Skipping archived repo {0}".format(repo.full_name))
            continue
        if repo.full_name in skipRepos:
            print("  * Skipping repo {0}".format(repo.full_name))
            continue
        print("  * Found repo {0}".format(repo.full_name))
        yield repo


def filesFromRepo(repo, skipFiles=None):
    if skipFiles is None:
        skipFiles = set()
    else:
        skipFiles = set(skipFiles)
    print("Searching {0} repo for Bikeshed files...".format(repo.full_name))

    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
    except GithubException as err:
        if err.status == 409:  # "Git Repository is empty"
            return
        raise
    for entry in tree.tree:
        path = repo.full_name + "/" + entry.path
        if any(fnmatch.fnmatch(path, pattern) for pattern in skipFiles):
            print("  * Skipping file {0}".format(entry.path))
            continue
        if entry.type == "blob" and entry.path.endswith(".bs"):
            print("  * Found file {0}".format(entry.path))
            blob = repo.get_git_blob(entry.sha)
            assert blob.encoding == "base64"
            text = base64.b64decode(blob.content).decode("utf-8")
            yield {"path": path, "text": text}


def processFile(file):
    path = os.path.join(root_dir, "tests", "github", file["path"])
    print("Saving file {0}".format(os.path.relpath(path, start=root_dir)))
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with io.open(path, "w+", encoding="utf-8") as f:
        f.write(file["text"])


def main():
    try:
        token = os.environ["GITHUB_TOKEN"]
    except KeyError:
        print("Set the GITHUB_TOKEN environment variable and try again.")
    g = Github(token)
    start_secs = time.monotonic()
    initial_rate_limit = g.rate_limiting
    print(
        "Initial rate limit is {0[1]} requests per hour ({0[0]} remaining)".format(
            initial_rate_limit
        )
    )

    def throttle():
        if g.get_rate_limit().search.remaining == 1:
            sleep_time = (
                g.get_rate_limit().search.reset - datetime.utcnow()
            ).total_seconds() + 1
            print(f"Sleeping {sleep_time}s to stay under rate limit.")
            time.sleep(sleep_time)

    data = getData()
    repos = []
    for orgName in sorted(data["orgs"]):
        org = g.get_organization(orgName)
        repos.extend(reposFromOrg(org, data["skipRepos"]))
        throttle()
    for repoName in data["moreRepos"]:
        repos.append(g.get_repo(repoName))
        throttle()
    files = []
    for repo in sorted(repos, key=lambda x: x.full_name):
        files.extend(filesFromRepo(repo, data["skipFiles"]))
        throttle()
    for file in sorted(files, key=lambda x: x["path"]):
        processFile(file)


if __name__ == "__main__":
    main()

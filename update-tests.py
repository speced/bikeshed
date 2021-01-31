import io
import os
import time
from datetime import datetime

from github import Github
from github.GithubException import RateLimitExceededException, GithubException

github_dir = "tests/github"

repos = []

for user in os.listdir("tests/github"):
    for repo in os.listdir(f"{github_dir}/{user}"):
        repos.append(f"{user}/{repo}")

try:
    githubClient = Github(os.environ["GITHUB_SEARCH_TOKEN"])
except KeyError:
    print(
        "GitHub search API limit is limited to 10, unless setting a read token in your environment of GITHUB_SEARCH_TOKEN"
    )
    githubClient = Github()

for repo in repos:
    repo_dir = f"{github_dir}/{repo}"
    # TODO: shutil.rmtree(repo_dir) to clean out possible deleted/renamed specs may be better starting point
    print(f"Searching: {repo}")
    if githubClient.get_rate_limit().search.remaining == 1:
        sleet_time = (
            githubClient.get_rate_limit().search.reset - datetime.utcnow()
        ).total_seconds() + 1
        print(
            f"Rate limit of {githubClient.get_rate_limit().search.limit} to hit, pausing for {sleet_time} seconds"
        )
        time.sleep(sleet_time)

    query_string = f"extension:bs repo:{repo}"
    search = githubClient.search_code(query=query_string)

    try:
        for code in search:
            try:
                with io.open(f"{repo_dir}/{code.path}", "w+", encoding="utf-8") as f:
                    f.write(bytes.decode(code.decoded_content))
            except FileNotFoundError:
                print(f"New BS file found: {code.path}")
                os.makedirs(f"{repo_dir}/{code.path.replace(f'/{code.name}', '')}")
                with io.open(f"{repo_dir}/{code.path}", "x+", encoding="utf-8") as f:
                    f.write(bytes.decode(code.decoded_content))

            print(f"Updated: {repo_dir}/{code.path}")
            # TODO: Maybe programatically call `bikeshed test --rebase` to generate the diff here

    except RateLimitExceededException:
        print(
            "Rate limit hit. Try again later or set GITHUB_SEARCH_TOKEN environment variable"
        )
        exit()

    except GithubException as e:
        print(
            f"Couldn't read query. Possible deleted/renamed repo. Will rename and retry.\n{e}"
        )
        new_repo = githubClient.get_repo(repo).full_name
        os.renames(f"{repo_dir}", f"{github_dir}/{new_repo}")
        repos.append(new_repo)

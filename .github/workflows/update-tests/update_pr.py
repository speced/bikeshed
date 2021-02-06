import os

from github import Github


def create_pr():
    token = os.environ["GITHUB_TOKEN"]
    g = Github(token)
    repo = g.get_repo("tabatkins/bikeshed")
    for pull in repo.get_pulls(state="open"):
        if pull.head.label == "auto-test-update":
            print("Existing PR found:", pull.html_url)
            return
    pull = repo.create_pull(
        title="Automatic test update", body="", base="master", head="auto-test-update"
    )
    print("Created PR:", pull.html_url)


def main():
    create_pr()


if __name__ == "__main__":
    main()

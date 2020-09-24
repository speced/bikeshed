from __future__ import print_function
import os

from github import Github


def create_pr():
    token = os.environ['GH_TOKEN']
    g = Github(token)
    repo = g.get_repo('tabatkins/bikeshed')
    for pull in repo.get_pulls(state='open'):
        if pull.head.label == 'autofoolip:auto-test-update':
            print("Existing PR found:", pull.html_url)
            return
    pull = repo.create_pull(title='Automatic test update',
                            body='By https://github.com/foolip/bikeshed-tests',
                            base='master',
                            head='autofoolip:auto-test-update')
    print('Created PR:', pull.html_url)


def main():
    create_pr()


if __name__ == '__main__':
    main()

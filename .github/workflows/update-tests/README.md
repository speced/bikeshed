# Bikeshed tests auto-updater

These scripts collect *.bs files from GitHub repos and creates PRs to update
Bikeshed's tests in `tests/github/`.

## Adding Your Specs

If you'd like to add your own specs to Bikeshed's regression test-suite,
submit a PR for the `specs.data` file.

This file format is line-based:
to add your entire organization, add a `+org: orgname` line;
to add a single repo, add a `+repo: user/repo` line.
If you need to exclude any repos or files,
use a `-repo: user/repo`
or `-file: user/repo/path/to/file.bs` line.
(`-file` lines can use shell wildcarding conventions to exclude multiple files,
as implemented by the Python [fnmatch](https://docs.python.org/2/library/fnmatch.html) module,
like `-file: */review-drafts/*.bs` to exclude all files in a `review-drafts` folder.)

The files to be processed by this tool must have the `.bs` extension;
if you specify a repo or an org,
the entire repo/org will be crawled for `.bs` files.

Indentation does not matter, but can be used for readability,
to group some `-` lines underneath the larger `+` line that would include them.

Lines starting with `#` are comments and are ignored;
blank lines are also ignored.

## Running locally

You need Python 3. Then install the dependencies:
```bash
pip3 install --user -r requirements.txt
```

The python scripts need `GITHUB_TOKEN` environment variable set to a
[personal access token](https://github.com/settings/tokens/new) with the
"Access public repositories" (public_repo) scope enabled.

To emulate what GitHub Actions does, execute each step in `update-tests.yml` manually.

Developing Bikeshed
===================

If you want to contribute back to Bikeshed,
first make a fork on GitHub,
then do an [editable install](https://tabatkins.github.io/bikeshed/#install-dev) of Bikeshed from your fork.
(Uninstall any pip-installed version you may have beforehand,
or use one of the several separate-environment things Python currently has
(`venv`, `pipenv`, `virtualenv`...)
to isolate it.)
This way your local changes will be reflected when you run the `bikeshed` command,
making it easy to test.

(I recommend `pipenv`;
I find it simple to use,
and it's what I use to develop Bikeshed,
so it has a high chance of working correctly.)

See [my blog post on cleanly handling a fork](https://www.xanthir.com/b4hf0)
for guidance on how to fork responsibly
when you're making small changes to an active project;
you'll save yourself a lot of future pain
if you follow those steps.

Linting
-------

Bikeshed uses a number of services to lint its codebase.
If you don't run these beforehand,
your contributions might fail just due to violating the linting rules.

To lint everything, first install `ruff`, `pylint`, `mypy`, and `black` from `pypi`.
(You can automatically get the versions that the project currently uses by running `pip install -r requirements-dev.txt` from the project root.)

Then, from the root directory of the project, run the `lint` script,
which'll invoke all of these in the correct way for you.
Fix anything that any of these are complaining about;
if they are all happy, you're good.

Running Tests
-------------

Bikeshed has a decent suite of intentional tests,
and a comprehensive suite of real-world specs to test against,
which gives a reasonably good assurance that every codepath is exercised at least once.
We need to keep the tests green,
so running these before submitting a PR is important.

* `bikeshed test` will run all of the tests,
 giving you diffs where there's failures.
* `bikeshed test --rebase` will rebase all of the tests,
    replacing the `.html` files with their new forms,
    and the `.console.txt` files with the console output.
    This can be useful as a general testing strategy;
    git's diff can be easier to read than the simple one `bikeshed test` uses,
    and you might be even an even better diff pager than the default.
    (I highly recommend [using Delta](https://github.com/dandavison/delta)!)

    It's also necessary, however, to actually generate the new test expectations;
    the tests are generated with some special options
    that ensure they can be stably generated across different environments
    (omitting today's date, etc),
    and `bikeshed test --rebase` ensures these are all set up correctly.

* Both of these commands default to running all of the tests,
    but you can run *particular* tests in several ways:

    * passing `--manual` will only run the manually-written tests,
        which are small and very fast,
        skipping all the real-world document tests.

    * passing `--folder FOLDER FOLDER ...` will run any tests
        for which one of the FOLDER values is the name of a folder in their path.
        (exact matches required).

    * passing `--file FILE FILE ...` will run any tests
        for which one fo the FILE values
        is a substring of their filename.
        (That is, exact matches not required.)

* To run Playwright visual tests and tests of client-side user interaction,
    * NodeJS and docker must be installed first.
    * Then, to run all `*_pwtest.js` scripts and compare with existing  __screenshots__ in the same directory, run the following.
        * `npm run pwtests`
    * To update the screenshots after you make changes that should affect the screenshots, run this instead:
        * `npm run pwtests-update`


Managing Requirements
---------------------

Now that Bikeshed's recommended install path is via `pipx`,
which automatically puts it in a clean environment for the user,
I've simplified dependency management back to just relying on `requirements.txt`.

If you add a new dependency, make sure to add it to this file.
Use exact versions **only**, not ranges.
(It makes installs more predictable, and doesn't affect users.
It can affect devs, but they can be expected to know how to use `pipenv`
or similar environment isolation tools.)

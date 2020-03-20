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

See [my blog post on cleanly handling a fork](https://www.xanthir.com/b4hf0)
for guidance on how to fork responsibly
when you're making small changes to an active project;
you'll save yourself a lot of future pain
if you follow those steps.


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
	replacing the `.html` files with their new forms.
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
	but you can run *particular* tests
	by passing them as additional command-line positional args
	(full path, starting below the `/tests/` directory,
	so running the manual tests just requires giving their name, etc).

	Alternately, the `--manual-only` flag
	will run only the manually-written tests,
	which are small and very fast,
	skipping all the real-spec tests.
	This can be worthwhile for a quick check,
	as it takes less than 20s to run them,
	versus several minutes for the full suite.
	However, many code paths are not exercised by these,
	so a full test run/rebase is required to ensure your change is actually fine.
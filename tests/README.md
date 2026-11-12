Bikeshed Testing
================

This is Bikeshed's test suite, currently 100% integration tests.
Run the testsuite with `bikeshed test`.

The `manual/` folder contains hand-written tiny specs,
designed to exercise one feature.
These are all that's run by default,
as they're very fast.

The `github/` folder contains real-world specs
sourced from several standards orgs (mostly the W3C).
To run these, pass the `--all` flag.

You can run individual tests or groups of tests by filtering on their filename or folder,
using the `--file=STR` and/or `--folder=STR` argument.
Each does a substring test, so you don't need to type out the entire name.
When either of these are passed,
it defaults to searching the entire testsuite,
but you can limit it to just the manual tests by passing `--manual`.

Judging Tests
-------------

As these are integration tests,
correctness is verified just by processing `TESTNAME.bs`,
and comparing the serialized output to a golden file (`TESTNAME.html`).
The console output is also checked,
by comparing against `TESTNAME.console.txt`.
Only byte-identical results are considered a pass.

Rebasing Tests
--------------

If golden files need to be updated due to a code change,
run with the `--rebase` flag.
All the filtering flags can be used to scope down the rebase.

Creating New Tests
------------------

New manual tests should be created by adding a new folder under `manual`,
ideally with a name like `feature001`,
and a `feature001.bs` test file.
Use `bikeshed template test > feature001.bs` to give a starting point,
or copy from an existing test.
Then rebase the test with the `bikeshed test --rebase`,
verify both the build output and the console output are what you expect,
and commit the test.
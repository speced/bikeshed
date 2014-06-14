Bikeshed Testing
================

This is the start of an ad-hoc testing system.
No clue if it's a good idea or not,
but I need to be doing *something* for testing,
so let's start.

Each test file should be appropriately named after whatever it's testing,
in the format `[testname][3-digit-zero-padded-number].bs`.
The "golden" generated file should have the same name,
but `.html`.

Run tests by running `bikeshed test`.
If any fail, it'll print the first element mismatch in each file,
with an inline diff from the golden.

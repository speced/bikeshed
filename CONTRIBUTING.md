# Developing bikeshed

After [installing Bikeshed](https://tabatkins.github.io/bikeshed/#installing) you can start making changes to its source code and contribute those changes back via pull requests. (There is no need to install it again after having made changes.)

## Running tests

`bikeshed test` will run all tests which may take a while, for development `bikeshed test --manual-only` is preferred. You can also run `bikeshed test test.bs` to run an individual test, where `test.bs` is a resource in the `tests/` directory. To change the expected outcome of a test, you can run `bikeshed test test.bs --rebase`.

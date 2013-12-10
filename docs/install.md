Installing Bikeshed
===================

If you want to run a local copy of Bikeshed rather than use the cgi version, it’s pretty easy to install.

First, install Python 2.7, PIP, and a few other support libraries:

~~~~
$ sudo apt-get install python2.7 python-dev python-pip libxslt1-dev libxml2-dev
~~~~

The `apt-get` command works on Debian-based systems like Ubuntu; if you work on some other type of system, and can figure out how to get things working on your own, let me know and I'll add instructions for your system.

Then, we'll need to install lxml.

~~~~
$ sudo pip install lxml
~~~~

**Important**: If this command reports that you already have lxml, instead run:

~~~~
$ sudo pip install lxml --upgrade
~~~~

That'll spew a lot of console trash, but don't worry about it.

Second, you’ll need the Bikeshed repository itself.  Run the following in your favorite command line:

~~~~
$ git clone https://github.com/tabatkins/bikeshed.git
~~~~

(This’ll download bikeshed to a `bikeshed` folder, created wherever you’re currently at.  If you think you might want to commit back to Bikeshed, instead download it over SSH. I won’t explain how to do that here.)

Finally, run:

~~~~
$ pip install --editable /path/to/cloned/bikeshed
~~~~

This’ll install Bikeshed, making it available to your Python environment as the `bikeshed` package, and automatically add a `bikeshed` command to your path.

To update bikeshed to its latest version at any time, just enter Bikeshed’s folder, and run:

~~~~
$ git pull --rebase
$ bikeshed update
~~~~

This’ll pull the latest version of Bikeshed, and ensure that you’re looking at the latest version of the data files, rather than whatever stale version is currently sitting in the repo.

See the [Quick Start Guide](quick-start.md) for a quick run-through of how to actually use the processor, and the rest of the docs for more detailed information.

(If anything doesn’t work in here, let me know and I’ll fix it.  It’s very likely I’m accidentally skipping a step or two right now, as I’m writing this long after I’ve actually installed everything necessary myself.)
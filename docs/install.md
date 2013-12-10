Installing Bikeshed
===================

If you want to run a local copy of Bikeshed rather than use the cgi version, it’s pretty easy to install.

First, you’ll need Python 2.7.  Install that however you do that best.  For example, on Ubuntu you would type `sudo apt-get install python2.7` into a console window.

Second, you’ll need Pip, a python package installer.  On an appropriately Linux-compatible system, do:

~~~~
$ sudo apt-get install python-pip
~~~~

or

~~~~
$ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
$ sudo python get-pip.py
~~~~

If you’re on OSX and using MacPorts, install py27-pip from it.

If you’re on some other setup, I don’t know how to best get Pip running.  If you find out, let me know, and I’ll add it to this readme.

You’ll probably also need a few more tools:

~~~~
$ sudo apt-get install python-lxml
$ sudo apt-get install libxslt1-dev
$ sudo apt-get install libxml2-dev
~~~~

Third, you’ll need the Bikeshed repository itself.  Run the following in your favorite command line:

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
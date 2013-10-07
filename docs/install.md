Installing Bikeshed
===================

If you want to run a local copy of Bikeshed rather than use the cgi version, it's pretty easy to install.

First, you'll need Python 2.7.  Install that however you do that best.  For example, on Ubuntu you would type `sudo apt-get install python2.7` into a console window.

Second, you'll need Pip, a python package installer.  On an appropriately Linux-compatible system, do:

~~~~
$ sudo apt-get install python-pip
~~~~

or

~~~~
$ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
$ sudo python get-pip.py
~~~~

If you're on OSX and using MacPorts, install py27-pip from it.

If you're on some other setup, I don't know how to best get Pip running.  If you find out, let me know, and I'll add it to this readme.

Finally, just run `pip install --user git+https://github.com/tabatkins/bikeshed.git`.  This'll download Bikeshed and its dependencies, and automatically install a `css-bikeshed` command that runs Bikeshed.  See the [Quick Start Guide](quick-start.md) for a quick run-through of how to actually use the processor, and the rest of the docs for more detailed information.

If this final command fails when attempting to install lxml, it's probably because it's missing its own dependencies, which can't be automatically installed by Pip.  Manually install `libxml2` and `libxslt` - you can do so with `apt-get` exactly like above, or whatever your particular system does.
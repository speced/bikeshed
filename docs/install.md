Installing Bikeshed
===================

If you use Bikeshed infrequently,
or are okay with requiring a network roundtrip every time you invoke Bikeshed,
you probably want to use the Bikeshed API instead <https://api.csswg.org/bikeshed/>.
In return, the API version is always up-to-date,
so you don't have to remember to update things yourself.

If you want to run a local copy of Bikeshed rather than use the cgi version, it’s pretty easy to install.

You need to install Python 2.7, PIP, and a few other support libraries before installing Bikeshed itself. Here is how to do this on Debian-based Linuxen (anything using `apt`), OS X, and Windows 7/8/10:

Linux steps
-----------

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

From here, you can follow the commons steps outlined below.

OS X steps
----------

These instructions assume that you have [Mac Ports](https://www.macports.org/) installed. If you successfully install Bikeshed using some other method, please contribute to this documentation.

First, get the right packages installed onto your system:
~~~
sudo port install python27 py27-pip py27-lxml py27-html5lib py27-cssselect py27-libxslt py27-libxml2
~~~

Then, activate the python version you just installed as the one the system should use:
~~~
sudo port select --set python python27
~~~

(If you get `ImportError: No module named six` when you first run Bikeshed, additionally run `sudo port install py27-six`.)

Windows steps
-----------

Tested on Windows 7, 8/8.1 & 10

1. Install the latest [Python 2.7](https://www.python.org/download/releases/2.7.8/)
2. Run the following in an elevated command prompt (change the path if your location is different)
~~~
setx /m PATH "%PATH%;C:\Python27;C:\Python27\Scripts"
~~~
3. Install [PIP](https://pip.pypa.io/en/latest/installing.html) by saving [get-pip.py](https://bootstrap.pypa.io/get-pip.py) and just double clicking the file.
4. Install [LXML](http://www.lfd.uci.edu/~gohlke/pythonlibs/#lxml) for your version of Python (it should be lxml-3.4.0win32-py2.7.exe)

From here, you can follow the commons steps outlined below.

Common steps
------------
With the dependencies in place, you can now install the Bikeshed repository itself.  Run the following in your favorite command line:

~~~~
$ git clone https://github.com/tabatkins/bikeshed.git
~~~~

(This’ll download bikeshed to a `bikeshed` folder, created wherever you’re currently at.  If you think you might want to commit back to Bikeshed, instead download it over SSH. I won’t explain how to do that here.)

Finally, run:

For Linux/OSX:

~~~~
$ sudo pip install --editable /path/to/cloned/bikeshed
~~~~

On Windows:

~~~~
python -m pip install --editable /path/to/cloned/bikeshed
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

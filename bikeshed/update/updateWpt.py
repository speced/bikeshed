# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import json
import os
import urllib2
from contextlib import closing

from ..messages import *

def update(path, dryRun=False):
    try:
        say("Downloading web-platform-tests data...")
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/wpt-tests.txt")) as fh:
            data = unicode(fh.read(), encoding="utf-8")
    except Exception, e:
        die("Couldn't download web-platform-tests data.\n{0}", e)
        return

    if not dryRun:
        try:
            with io.open(os.path.join(path, "wpt-tests.txt"), 'w', encoding="utf-8") as f:
                f.write(data)
        except Exception, e:
            die("Couldn't save web-platform-tests data to disk.\n{0}", e)
            return
    say("Success!")

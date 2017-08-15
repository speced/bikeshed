# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import io
import json
import urllib2
from contextlib import closing

from .. import config
from ..messages import *

def update():
    try:
        say("Downloading languages...")
        with closing(urllib2.urlopen("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/languages.json")) as fh:
            data = unicode(fh.read(), encoding="utf-8")
    except Exception, e:
        die("Couldn't download languages data.\n{0}", e)
        return

    if not config.dryRun:
        try:
            with io.open(config.scriptPath + "/spec-data/languages.json", 'w', encoding="utf-8") as f:
                f.write(data)
        except Exception, e:
            die("Couldn't save languages database to disk.\n{0}", e)
            return
    say("Success!")
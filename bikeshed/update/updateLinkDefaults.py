# -*- coding: utf-8 -*-

import io
import json
import os
import urllib.request, urllib.error, urllib.parse
from contextlib import closing

from ..messages import *

def update(path, dryRun=False):
    try:
        say("Downloading link defaults...")
        with closing(urllib.request.urlopen("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/link-defaults.infotree")) as fh:
            data = str(fh.read(), encoding="utf-8")
    except Exception as e:
        die("Couldn't download link defaults data.\n{0}", e)
        return

    if not dryRun:
        try:
            with io.open(os.path.join(path, "link-defaults.infotree"), 'w', encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            die("Couldn't save link-defaults database to disk.\n{0}", e)
            return
    say("Success!")

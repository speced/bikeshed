# -*- coding: utf-8 -*-

import io
import os
import requests

from ..messages import *

def update(path, dryRun=False):
    try:
        say("Downloading link defaults...")
        data = requests.get("https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/link-defaults.infotree").text
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

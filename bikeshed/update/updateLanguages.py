import os

import requests

from ..messages import *


def update(path, dryRun=False):
    try:
        say("Downloading languages...")
        data = requests.get(
            "https://raw.githubusercontent.com/tabatkins/bikeshed/master/bikeshed/spec-data/readonly/languages.json"
        ).text
    except Exception as e:
        die("Couldn't download languages data.\n{0}", e)
        return

    if not dryRun:
        try:
            with open(os.path.join(path, "languages.json"), "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            die("Couldn't save languages database to disk.\n{0}", e)
            return
    say("Success!")

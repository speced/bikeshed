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
        die(f"Couldn't download languages data.\n{e}")
        return

    if not dryRun:
        try:
            with open(os.path.join(path, "languages.json"), "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            die(f"Couldn't save languages database to disk.\n{e}")
            return
    say("Success!")

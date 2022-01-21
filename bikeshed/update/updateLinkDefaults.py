import os

import requests

from .. import messages as m


def update(path, dryRun=False):
    try:
        m.say("Downloading link defaults...")
        data = requests.get(
            "https://raw.githubusercontent.com/tabatkins/bikeshed/main/bikeshed/spec-data/readonly/link-defaults.infotree"
        ).text
    except Exception as e:
        m.die(f"Couldn't download link defaults data.\n{e}")
        return

    if not dryRun:
        try:
            with open(os.path.join(path, "link-defaults.infotree"), "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            m.die(f"Couldn't save link-defaults database to disk.\n{e}")
            return
    m.say("Success!")

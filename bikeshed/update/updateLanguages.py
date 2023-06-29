from __future__ import annotations

import os

import requests

from .. import messages as m


def update(path: str, dryRun: bool = False) -> set[str] | None:
    try:
        m.say("Downloading languages...")
        data = requests.get(
            "https://raw.githubusercontent.com/speced/bikeshed/main/bikeshed/spec-data/readonly/languages.json",
            timeout=5,
        ).text
    except Exception as e:
        m.die(f"Couldn't download languages data.\n{e}")
        return None

    filePath = os.path.join(path, "languages.json")

    if not dryRun:
        try:
            with open(filePath, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            m.die(f"Couldn't save languages database to disk.\n{e}")
            return None
    m.say("Success!")
    return {filePath}

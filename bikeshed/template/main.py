from __future__ import annotations

from .. import config
from .. import messages as m


def getTemplate(variant: str) -> str | None:
    match variant:
        case "spec" | "minimal" | "test":
            with open(config.scriptPath("template", f"{variant}.bs"), "r", encoding="utf-8") as fh:
                return fh.read()
        case "wpt":
            with open(config.scriptPath("template", "wpt.html"), "r", encoding="utf-8") as fh:
                return fh.read()
        case _:
            m.die(f"Unknown template variant '{variant}'.")
            return None

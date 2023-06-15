from __future__ import annotations

from . import constants, retrieve, t


def load(doc: t.SpecT) -> None:
    code = retrieve.retrieveBoilerplateFile(doc, "bs-extensions", allowLocal=constants.executeCode)
    exec(code, globals())

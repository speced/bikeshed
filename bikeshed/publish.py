# pylint: disable=R1732

from __future__ import annotations

import contextlib
import logging
import os
import tarfile
import tempfile

from . import extensions, t
from . import messages as m


def publishEchidna(
    doc: t.SpecT,
    username: str,
    password: str,
    decision: str,
    additionalDirectories: list[str] | None = None,
    cc: str | None = None,
    editorial: bool = False,
) -> None:
    import requests

    logging.captureWarnings(True)  # Silence SNIMissingWarning
    tarBytes = prepareTar(doc, additionalDirectories=additionalDirectories)
    # curl 'https://labs.w3.org/echidna/api/request' --user '<username>:<password>' -F "tar=@/some/path/spec.tar" -F "decision=<decisionUrl>"
    data = {
        "decision": decision,
    }
    if cc:
        data["cc"] = cc
    if editorial:
        data["editorial"] = "true"
    r = requests.post(
        "https://labs.w3.org/echidna/api/request",
        auth=(username, password),
        data=data,
        files={"tar": tarBytes},
        timeout=3,
    )

    if r.status_code == 202:
        m.say("Successfully pushed to Echidna!")
        m.say("Check the URL in a few seconds to see if it was published successfully:")
        m.say("https://labs.w3.org/echidna/api/status?id=" + r.text)
    else:
        m.say("There was an error publishing your spec. Here's some information that might help?")
        m.say(str(r.status_code))
        m.say(r.text)
        m.say(str(r.headers))


def prepareTar(doc: t.SpecT, additionalDirectories: list[str] | None = None) -> bytes:
    if additionalDirectories is None:
        additionalDirectories = ["images", "diagrams", "examples"]
    # Finish the spec
    specOutput = tempfile.NamedTemporaryFile(delete=False)
    doc.finish(outputFilename=specOutput.name)
    # Build the TAR file
    f = tempfile.NamedTemporaryFile(delete=False)
    tar = tarfile.open(fileobj=f, mode="w")
    tar.add(specOutput.name, arcname="Overview.html")
    # Loaded from .include files
    additionalFiles = extensions.BSPublishAdditionalFiles(additionalDirectories)  # type: ignore # pylint: disable=no-member
    for fname in additionalFiles:
        if isinstance(fname, str):
            inputPath = str(doc.inputSource.relative(fname))
            outputPath = fname
        else:
            inputPath = str(doc.inputSource.relative(fname[0]))
            outputPath = fname[1]
        with contextlib.suppress(OSError):
            tar.add(inputPath, outputPath)
    tar.close()
    specOutput.close()
    os.remove(specOutput.name)
    f.seek(0)
    tarBytes = f.read()
    f.close()
    return tarBytes

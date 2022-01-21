import json
import os
from collections import OrderedDict

import requests

from .. import messages as m


def update(path, dryRun=False):
    m.say("Downloading MDN Spec Links data...")
    specMapURL = "https://w3c.github.io/mdn-spec-links/SPECMAP.json"
    try:
        response = requests.get(specMapURL)
    except Exception as e:
        m.die(f"Couldn't download the MDN Spec Links data.\n{e}")
        return

    try:
        data = response.json(encoding="utf-8", object_pairs_hook=OrderedDict)
    except Exception as e:
        m.die(f"The MDN Spec Links data wasn't valid JSON for some reason. Try downloading again?\n{e}")
        return
    writtenPaths = set()
    if not dryRun:
        try:
            mdnSpecLinksDir = os.path.join(path, "mdn")
            if not os.path.exists(mdnSpecLinksDir):
                os.makedirs(mdnSpecLinksDir)
            p = os.path.join(path, "mdn.json")
            writtenPaths.add(p)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False))
            # SPECMAP.json format:
            # {
            #     "https://compat.spec.whatwg.org/": "compat.json",
            #     "https://console.spec.whatwg.org/": "console.json",
            #     "https://dom.spec.whatwg.org/": "dom.json",
            #     ...
            # }
            for specFilename in data.values():
                p = os.path.join(mdnSpecLinksDir, specFilename)
                writtenPaths.add(p)
                mdnSpecLinksBaseURL = "https://w3c.github.io/mdn-spec-links/"
                try:
                    fileContents = requests.get(mdnSpecLinksBaseURL + specFilename).text
                except Exception as e:
                    m.die(f"Couldn't download the MDN Spec Links {specFilename} file.\n{e}")
                    return
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(fileContents)
        except Exception as e:
            m.die(f"Couldn't save MDN Spec Links data to disk.\n{e}")
            return
    m.say("Success!")
    return writtenPaths

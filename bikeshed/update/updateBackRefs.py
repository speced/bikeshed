from __future__ import annotations

import os

from .. import config, t

TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))


def findTestFiles() -> t.Generator[str, None, None]:
    for root, _, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            if filename.endswith(".bs") and "/github/" in root:
                yield os.path.join(root, filename)


def testNameForPath(path: str) -> str:
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR) + 1 :]
    return path


def update(path: str, dryRun: bool = False) -> set[str] | None:  # pylint: disable=unused-argument
    return None  # early exit while working on this...
    # say("Downloading backref data...")
    # constants.quiet = float("inf")
    # if not dryRun:
    #     backrefs = defaultdict(lambda: defaultdict(list))
    #     for i, testPath in enumerate(findTestFiles()):
    #         if i > 1:
    #             break
    #         print(i, testNameForPath(testPath))
    #         doc = Spec(inputFilename=testPath)
    #         doc.preprocess()
    #         if doc.md.ED:
    #             url = doc.md.ED
    #         elif doc.md.TR:
    #             url = doc.md.TR
    #         else:
    #             continue
    #         referencingShortname = doc.md.vshortname
    #         for ref in processRefs(doc.externalRefsUsed):
    #             _, _, referencedID = ref.url.partition("#")
    #             referencedID = urllib.parse.unquote(referencedID)
    #             referencedShortname = ref.spec
    #             referencingLinks = findAll(f"[href='{ref.url}']", doc)
    #             referencingIDs = [
    #                 link.get("id") for link in referencingLinks if link.get("id")
    #             ]
    #             referencingURLs = [f"{url}#{id}" for id in referencingIDs]
    #             backrefs[referencedShortname][referencedID].append(
    #                 {"shortname": referencingShortname, "urls": referencingURLs}
    #             )

    # print(printjson.printjson(backrefs))


def processRefs(refs: t.Any) -> t.Any:
    seenRefs = set()
    # shape is {spec: {reftext: {forKey: ref}}}, just collect all the refs
    for keysByText in refs.values():
        for refsByKey in keysByText.values():
            for ref in refsByKey.values():
                key = (ref.url, ref.spec)
                if key not in seenRefs:
                    yield ref
                    seenRefs.add(key)


ignoredSpecs = {
    "css-foo-1",
    "css-typed-om-2",
    "css-2015-0",
    "d0???-1",
    "svg-color-1",
    "{{repo}}-1",
}

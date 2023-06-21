from __future__ import annotations

import os

from .. import config, t
from .. import messages as m
from . import (
    manifest,
    updateBackRefs,
    updateBiblio,
    updateBoilerplates,
    updateCanIUse,
    updateCrossRefs,
    updateLanguages,
    updateLinkDefaults,
    updateMdn,
    updateWpt,
)


def update(
    anchors: bool = False,
    backrefs: bool = False,
    biblio: bool = False,
    boilerplate: bool = False,
    caniuse: bool = False,
    linkDefaults: bool = False,
    mdn: bool = False,
    languages: bool = False,
    wpt: bool = False,
    path: str | None = None,
    dryRun: bool = False,
    manifestMode: str | None = None,
) -> manifest.Manifest | None:
    if path is None:
        path = config.scriptPath("spec-data")
    assert path is not None

    # Update via manifest by default, falling back to a full update only if failed or forced.
    if manifestMode is None or manifestMode == "force":
        success = manifest.updateByManifest(path=path, dryRun=dryRun, force=manifestMode == "force")
        if success:
            return None
        else:
            m.say("Falling back to a manual update...")

    # fmt: off
    # If all are False, update everything
    if anchors == backrefs == biblio == boilerplate == caniuse == linkDefaults == mdn == languages == wpt == False:  # noqa: E712
        anchors = backrefs =  biblio =  boilerplate =  caniuse =  linkDefaults =  mdn =  languages =  wpt =  True

    touchedPaths: dict[str, set[str]|None] = {
        "anchors": updateCrossRefs.update(path=path, dryRun=dryRun) if anchors else None,
        "backrefs": updateBackRefs.update(path=path, dryRun=dryRun) if backrefs else None,
        "biblio": updateBiblio.update(path=path, dryRun=dryRun) if biblio else None,
        "boilerplate": updateBoilerplates.update(path=path, dryRun=dryRun) if boilerplate else None,
        "caniuse": updateCanIUse.update(path=path, dryRun=dryRun) if caniuse else None,
        "mdn": updateMdn.update(path=path, dryRun=dryRun) if mdn else None,
        "linkDefaults": updateLinkDefaults.update(path=path, dryRun=dryRun) if linkDefaults else None,
        "languages": updateLanguages.update(path=path, dryRun=dryRun) if languages else None,
        "wpt": updateWpt.update(path=path, dryRun=dryRun) if wpt else None,
    }
    # fmt: on

    cleanupFiles(path, touchedPaths=touchedPaths, dryRun=dryRun)
    return manifest.createManifest(path=path, dryRun=dryRun)


def fixupDataFiles(skipUpdate: bool = False) -> None:
    """
    Checks the readonly/ version is more recent than your current mutable data files.
    This happens if I changed the datafile format and shipped updated files as a result;
    using the legacy files with the new code is quite bad!
    """
    try:
        with open(livePath("manifest.txt"), encoding="utf-8") as fh:
            liveManifest = manifest.Manifest.fromString(fh.read())
    except:  # pylint: disable=bare-except
        liveManifest = None
    try:
        with open(readonlyPath("manifest.txt"), encoding="utf-8") as fh:
            readonlyManifest = manifest.Manifest.fromString(fh.read())
    except:  # pylint: disable=bare-except
        readonlyManifest = None

    if liveManifest and readonlyManifest and readonlyManifest.version > liveManifest.version:
        # If I've updated the readonly files more recently
        # than whatever version you're on,
        # I need to switch you over to the new version.
        try:
            for filename in os.listdir(readonlyPath()):
                copyanything(readonlyPath(filename), livePath(filename))
        except Exception as err:
            m.warn(
                f"Bikeshed's datafile format has changed, but I couldn't copy the new files over from cache. Bikeshed might be unstable; try running `bikeshed update`.\n  {err}",
            )
            return

    # Now see if the local datafiles are likely out-of-date.
    if skipUpdate:
        return
    if liveManifest is None:
        m.warn("Couldn't find manifest from previous update run.\nTriggering a datafiles update to be safe...")
        update()
        return
    if liveManifest.daysOld() >= 7:
        m.say("Bringing data files up-to-date...")
        update()


def updateReadonlyDataFiles() -> None:
    """
    Like fixupDataFiles(), but in the opposite direction --
    copies all my current mutable data files into the readonly directory.
    This is a debugging tool to help me quickly update the built-in data files,
    and will not be called as part of normal operation.
    """
    try:
        for filename in os.listdir(livePath()):
            if filename.startswith("readonly"):
                continue
            copyanything(livePath(filename), readonlyPath(filename))
    except Exception as err:
        m.warn(f"Error copying over the datafiles:\n{err}")
        return


def cleanupFiles(root: str, touchedPaths: dict[str, set[str] | None], dryRun: bool = False) -> None:
    if dryRun:
        return
    # The paths of all files that were updated this run.
    paths = set()
    # Top-level files that will be deleted if they weren't updated.
    deletableFiles = ["test-suites.json"]
    # Folders that will have everything deleted that wasn't updated.
    deletableFolders = []
    if touchedPaths["anchors"] is not None:
        deletableFiles.extend(["specs.json", "methods.json", "fors.json"])
        deletableFolders.extend(["headings", "anchors"])
        paths.update(touchedPaths["anchors"])
    if touchedPaths["biblio"] is not None:
        deletableFiles.extend(["biblio-keys.json", "biblio-numeric-suffixes.json"])
        deletableFolders.extend(["biblio"])
        paths.update(touchedPaths["biblio"])
    if touchedPaths["caniuse"] is not None:
        deletableFiles.extend(["caniuse.json"])
        deletableFolders.extend(["caniuse"])
        paths.update(touchedPaths["caniuse"])
    if touchedPaths["mdn"] is not None:
        deletableFolders.extend(["mdn"])
        paths.update(touchedPaths["mdn"])
    if touchedPaths["boilerplate"] is not None:
        deletableFolders.extend(["boilerplate"])
        paths.update(touchedPaths["boilerplate"])

    m.say("Cleaning up old data files...")
    oldPaths = []
    for absPath, relPath in getDatafilePaths(root):
        if "/" not in relPath and relPath not in deletableFiles:
            continue
        if "/" in relPath and relPath.partition("/")[0] not in deletableFolders:
            continue
        if absPath not in paths:
            os.remove(absPath)
            oldPaths.append(relPath)
    if oldPaths:
        m.say(f"Success! Deleted {len(oldPaths)} old files.")
    else:
        m.say("Success! Nothing to delete.")


def copyanything(src: str, dst: str) -> None:
    import errno
    import shutil

    try:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    except OSError as exc:
        if exc.errno in [errno.ENOTDIR, errno.EINVAL]:
            shutil.copy(src, dst)
        else:
            raise


def livePath(*segs: str) -> str:
    return config.scriptPath("spec-data", *segs)


def readonlyPath(*segs: str) -> str:
    return config.scriptPath("spec-data", "readonly", *segs)


def getDatafilePaths(basePath: str) -> t.Generator[tuple[str, str], None, None]:
    for root, _, files in os.walk(basePath):
        for filename in files:
            filePath = os.path.join(root, filename)
            yield filePath, os.path.relpath(filePath, basePath)

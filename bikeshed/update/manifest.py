import asyncio
import hashlib
import os
import time
from datetime import datetime

import aiofiles
import aiohttp
import requests
import tenacity
from result import Err, Ok

from ..messages import *

# Manifest creation relies on these data structures.
# Add to them whenever new types of data files are created.
knownFiles = [
    "biblio-keys.json",
    "biblio-numeric-suffixes.json",
    "bikeshed-version.txt",
    "fors.json",
    "languages.json",
    "link-defaults.infotree",
    "mdn.json",
    "methods.json",
    "specs.json",
    "test-suites.json",
    "version.txt",
    "wpt-tests.txt",
]
knownFolders = [
    "anchors",
    "biblio",
    "caniuse",
    "headings",
    "mdn",
]

ghPrefix = "https://raw.githubusercontent.com/tabatkins/bikeshed-data/master/data/"

# To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
if sys.platform.startswith("win") and sys.version_info >= (3, 8):
    try:
        from asyncio import WindowsSelectorEventLoopPolicy
    except ImportError:
        pass
    else:
        if not isinstance(
            asyncio.get_event_loop_policy(), WindowsSelectorEventLoopPolicy
        ):
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())


def createManifest(path, dryRun=False):
    """Generates a manifest file for all the data files."""
    manifests = []
    for absPath, relPath in getDatafilePaths(path):
        if relPath in knownFiles:
            pass
        elif relPath.partition("/")[0] in knownFolders:
            pass
        else:
            continue
        with open(absPath, encoding="utf-8") as fh:
            manifests.append((relPath, hashFile(fh)))

    manifest = str(datetime.utcnow()) + "\n"
    for p, h in sorted(manifests, key=keyManifest):
        manifest += f"{h} {p}\n"

    if not dryRun:
        with open(os.path.join(path, "manifest.txt"), "w", encoding="utf-8") as fh:
            fh.write(manifest)

    return manifest


def keyManifest(manifest):
    name = manifest[0]
    if "/" in name:
        dir, _, file = name.partition("/")
        return 1, dir, file
    else:
        return 0, len(name), name


def hashFile(fh):
    return hashlib.md5(fh.read().encode("ascii", "xmlcharrefreplace")).hexdigest()


def getDatafilePaths(basePath):
    for root, dirs, files in os.walk(basePath):
        if "readonly" in dirs:
            continue
        for filename in files:
            if filename == "":
                continue
            filePath = os.path.join(root, filename)
            yield filePath, os.path.relpath(filePath, basePath)


def updateByManifest(path, dryRun=False):
    """
    Attempts to update only the recently updated datafiles by using a manifest file.
    Returns False if updating failed and a full update should be performed;
    returns True if updating was a success.
    """
    say("Updating via manifest...")

    say("Gathering local manifest data...")
    # Get the last-update time from the local manifest
    try:
        with open(os.path.join(path, "manifest.txt"), encoding="utf-8") as fh:
            localDt = dtFromManifest(fh.readlines())
    except Exception as e:
        localDt = "error"
        warn("Couldn't find local manifest file.\n{0}", e)

    # Get the actual file data by regenerating the local manifest,
    # to guard against mistakes or shenanigans
    localManifest = createManifest(path, dryRun=True).split("\n")
    localFiles = dictFromManifest(localManifest)

    say("Fetching remote manifest data...")
    try:
        remoteManifest = requests.get(ghPrefix + "manifest.txt").text.splitlines()
        remoteDt = dtFromManifest(remoteManifest)
        remoteFiles = dictFromManifest(remoteManifest)
    except Exception as e:
        warn(
            "Couldn't download remote manifest file, so can't update. Please report this!\n{0}",
            e,
        )
        warn("Update manually with `bikeshed update --skip-manifest`.")
        return False

    if remoteDt is None:
        die(
            "Something's gone wrong with the remote data; I can't read its timestamp. Please report this!"
        )
        return

    if localDt == "error":
        # A previous update run didn't complete successfully,
        # so I definitely need to try again.
        warn("Previous update had some download errors, so re-running...")
    elif localDt is not None:
        if (remoteDt - datetime.utcnow()).days >= 2:
            warn(
                "Remote data is more than two days old; the update process has probably fallen over. Please report this!"
            )
        if localDt == remoteDt and localDt != 0:
            say(
                "Local data is already up-to-date with remote ({0})",
                localDt.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return True
        elif localDt > remoteDt:
            # No need to update, local data is more recent.
            say(
                "Local data is fresher ({0}) than remote ({1}), so nothing to update.",
                localDt.strftime("%Y-%m-%d %H:%M:%S"),
                remoteDt.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return True

    if len(localFiles) == 0:
        say("The local manifest is borked or missing; re-downloading everything...")
    if len(remoteFiles) == 0:
        die("The remote data doesn't have any data in it. Please report this!")
        return
    newPaths = []
    for filePath, hash in remoteFiles.items():
        if hash != localFiles.get(filePath):
            newPaths.append(filePath)

    if not dryRun:
        deletedPaths = []
        for filePath in localFiles:
            if filePath not in remoteFiles and os.path.exists(
                localizePath(path, filePath)
            ):
                os.remove(localizePath(path, filePath))
                deletedPaths.append(filePath)
        if deletedPaths:
            print(
                "Deleted {} old data file{}.".format(
                    len(deletedPaths), "s" if len(deletedPaths) > 1 else ""
                )
            )

    if not dryRun:
        if newPaths:
            say(
                "Updating {0} file{1}...",
                len(newPaths),
                "s" if len(newPaths) > 1 else "",
            )
        goodPaths, badPaths = asyncio.run(updateFiles(path, newPaths))
        try:
            with open(os.path.join(path, "manifest.txt"), "w", encoding="utf-8") as fh:
                fh.write(createFinishedManifest(remoteManifest, goodPaths, badPaths))
        except Exception as e:
            warn("Couldn't save new manifest file.\n{0}", e)
            return False
    if not badPaths:
        say("Done!")
        return True
    else:
        phrase = f"were {len(badPaths)} errors" if len(badPaths) > 1 else "was 1 error"
        die(
            f"Done, but there {phrase} (of {len(newPaths)} total) in downloading or saving. Run `bikeshed update` again to retry."
        )
        return True


async def updateFiles(localPrefix, newPaths):
    tasks = set()
    async with aiohttp.ClientSession() as session:
        for filePath in newPaths:
            coro = updateFile(localPrefix, filePath, session=session)
            tasks.add(coro)

        lastMsgTime = time.time()
        messageDelta = 2
        goodPaths = []
        badPaths = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result.is_ok():
                goodPaths.append(result.value)
            else:
                badPaths.append(result.value)
            currFileTime = time.time()
            if (currFileTime - lastMsgTime) >= messageDelta:
                if not badPaths:
                    say("Updated {0}/{1}...", len(goodPaths), len(newPaths))
                else:
                    say(
                        "Updated {0}/{1}, {2} errors...",
                        len(goodPaths),
                        len(newPaths),
                        len(badPaths),
                    )
                lastMsgTime = currFileTime
    return goodPaths, badPaths


async def updateFile(localPrefix, filePath, session):
    remotePath = ghPrefix + filePath
    localPath = localizePath(localPrefix, filePath)
    res = await downloadFile(remotePath, session)
    if res.is_ok():
        res = await saveFile(localPath, res.ok())
    else:
        warn(
            f"Error downloading {filePath}, full error was:\n{await errorFromAsyncErr(res)}"
        )
    if res.is_err():
        res = Err(filePath)
    return res


async def errorFromAsyncErr(res):
    if res.is_ok():
        return res.ok()
    try:
        await res.err()
    except Exception as e:
        return e


def wrapError(retry_state):
    return Err(asyncio.wrap_future(retry_state.outcome))


@tenacity.retry(
    reraise=True,
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_random(1, 2),
    retry_error_callback=wrapError,
)
async def downloadFile(path, session):
    resp = await session.request(method="GET", url=path)
    resp.raise_for_status()
    return Ok(await resp.text())


@tenacity.retry(
    reraise=True,
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_random(1, 2),
    retry_error_callback=wrapError,
)
async def saveFile(path, data):
    dirPath = os.path.dirname(path)
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    async with aiofiles.open(path, "w", encoding="utf-8") as fh:
        await fh.write(data)
        return Ok(path)


def localizePath(root, relPath):
    return os.path.join(root, *relPath.split("/"))


def dictFromManifest(lines):
    """
    Converts a manifest file, where each line is
    <hash>[space]<filepath>
    into a dict of {path:hash}.
    First line of file is a datetime string, which we skip.
    """
    if len(lines) < 10:
        # There's definitely more than 10 entries in the manifest;
        # something borked
        return {}
    ret = {}
    for line in lines[1:]:
        if line == "":
            continue
        hash, _, path = line.strip().partition(" ")
        ret[path] = hash
    return ret


def dtFromManifest(lines):
    if lines[0].strip() == "error":
        return "error"
    try:
        return datetime.strptime(lines[0].strip(), "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        # Sigh, something borked
        return


def createFinishedManifest(
    manifestLines, goodPaths, badPaths
):  # pylint: disable=unused-argument
    if not badPaths:
        return "\n".join(manifestLines)

    # Ah, some errors.
    # First, indicate that errors happened in the timestamp,
    # so I won't spuriously refuse to re-update.

    manifestLines[0] = "error"

    # Now go thru and blank out the hashes for the bad paths,
    # so I'll definitely try to regenerate them later.

    badPaths = set(badPaths)
    for i, line in enumerate(manifestLines[1:], 1):
        prefix, _, path = line.strip().rpartition(" ")
        if path in badPaths:
            manifestLines[i] = (
                "error" + ("-" * (len(prefix) - len("error"))) + " " + path
            )

    return "\n".join(manifestLines)

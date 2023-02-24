from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import time
from datetime import datetime

import aiofiles
import aiohttp
import requests
import tenacity
from result import Err, Ok, Result

from .. import messages as m, t


def isOk(x: t.Any) -> t.TypeGuard[Ok]:
    return isinstance(x, Ok)


def isErr(x: t.Any) -> t.TypeGuard[Err]:
    return isinstance(x, Err)


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
    "boilerplate",
    "caniuse",
    "headings",
    "mdn",
]

ghPrefix = "https://raw.githubusercontent.com/speced/bikeshed-data/master/data/"

# To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
if sys.platform.startswith("win") and sys.version_info >= (3, 8):
    try:
        from asyncio import WindowsSelectorEventLoopPolicy
    except ImportError:
        pass
    else:
        if not isinstance(asyncio.get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())


def createManifest(path: str, dryRun: bool = False) -> str:
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


def keyManifest(manifest: tuple[str, str]) -> tuple[int, int | str, str]:
    name = manifest[0]
    if "/" in name:
        dir, _, file = name.partition("/")
        return 1, dir, file
    else:
        return 0, len(name), name


def hashFile(fh: t.TextIO) -> str:
    return hashlib.md5(fh.read().encode("ascii", "xmlcharrefreplace")).hexdigest()


def getDatafilePaths(basePath: str) -> t.Generator[tuple[str, str], None, None]:
    for root, dirs, files in os.walk(basePath):
        if "readonly" in dirs:
            continue
        for filename in files:
            if filename == "":
                continue
            filePath = os.path.join(root, filename)
            yield filePath, os.path.relpath(filePath, basePath)


def updateByManifest(path: str, dryRun: bool = False, force: bool = False) -> str | None:
    """
    Attempts to update only the recently updated datafiles by using a manifest file.
    Returns None if updating failed and a full update should be performed;
    returns the manifest if updating was a success.
    """
    m.say("Updating via manifest...")

    m.say("Gathering local manifest data...")
    # Get the last-update time from the local manifest
    try:
        with open(os.path.join(path, "manifest.txt"), encoding="utf-8") as fh:
            localDt = dtFromManifest(fh.readlines())
    except Exception as e:
        localDt = "error"
        m.warn(f"Couldn't find local manifest file.\n{e}")

    # Get the actual file data by regenerating the local manifest,
    # to guard against mistakes or shenanigans
    localManifest = createManifest(path, dryRun=True).split("\n")
    localFiles = dictFromManifest(localManifest)

    m.say("Fetching remote manifest data...")
    try:
        remoteManifest = requests.get(ghPrefix + "manifest.txt").text.splitlines()
        remoteDt = dtFromManifest(remoteManifest)
        remoteFiles = dictFromManifest(remoteManifest)
    except Exception as e:
        m.warn(
            f"Couldn't download remote manifest file, so can't update. Please report this!\n{e}",
        )
        m.warn("Update manually with `bikeshed update --skip-manifest`.")
        return None

    if not isinstance(remoteDt, datetime):
        m.die("Something's gone wrong with the remote data; I can't read its timestamp. Please report this!")
        return None

    if localDt == "error":
        # A previous update run didn't complete successfully,
        # so I definitely need to try again.
        m.warn("Previous update had some download errors, so re-running...")
    elif isinstance(localDt, datetime):
        if (remoteDt - datetime.utcnow()).days >= 2:
            m.warn(
                f"Remote data ({remoteDt.strftime('%Y-%m-%d %H:%M:%S')}) is more than two days older than local time ({datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}); either your local time is wrong (no worries, this warning will just repeat each time) or the update process has fallen over (please report this!)."
            )
        if not force:
            if localDt == remoteDt and localDt != 0:
                m.say(f"Local data is already up-to-date with remote ({localDt.strftime('%Y-%m-%d %H:%M:%S')})")
                return "\n".join(localManifest)
            elif localDt > remoteDt:
                # No need to update, local data is more recent.
                m.say(
                    f"Local data is fresher ({localDt.strftime('%Y-%m-%d %H:%M:%S')}) than remote ({remoteDt.strftime('%Y-%m-%d %H:%M:%S')}), so nothing to update.",
                )
                return "\n".join(localManifest)

    if len(localFiles) == 0:
        m.say("The local manifest is borked or missing; re-downloading everything...")
    if len(remoteFiles) == 0:
        m.die("The remote data doesn't have any data in it. Please report this!")
        return None
    newPaths = []
    for filePath, hash in remoteFiles.items():
        if hash != localFiles.get(filePath):
            newPaths.append(filePath)
    if not dryRun:
        deletedPaths = []
        for filePath in localFiles:
            if filePath not in remoteFiles and os.path.exists(localizePath(path, filePath)):
                os.remove(localizePath(path, filePath))
                deletedPaths.append(filePath)
        if deletedPaths:
            print("Deleted {} old data file{}.".format(len(deletedPaths), "s" if len(deletedPaths) > 1 else ""))

    newManifest = None
    if not dryRun:
        if newPaths:
            m.say(f"Updating {len(newPaths)} file{'s' if len(newPaths) > 1 else ''}...")
        goodPaths, badPaths = asyncio.run(updateFiles(path, newPaths))
        newManifest = createFinishedManifest(remoteManifest, goodPaths, badPaths)
        try:
            with open(os.path.join(path, "manifest.txt"), "w", encoding="utf-8") as fh:
                fh.write(newManifest)
        except Exception as e:
            m.warn(f"Couldn't save new manifest file.\n{e}")
            return None
    if newManifest is None:
        newManifest = createManifest(path, dryRun=True)

    if not badPaths:
        m.say("Done!")
        return newManifest
    else:
        phrase = f"were {len(badPaths)} errors" if len(badPaths) > 1 else "was 1 error"
        m.die(
            f"Done, but there {phrase} (of {len(newPaths)} total) in downloading or saving. Run `bikeshed update` again to retry."
        )
        return newManifest


async def updateFiles(localPrefix: str, newPaths: list[str]) -> tuple[list[str], list[str]]:
    tasks = set()
    async with aiohttp.ClientSession() as session:
        for filePath in newPaths:
            coro = updateFile(localPrefix, filePath, session=session)
            tasks.add(coro)

        lastMsgTime = time.time()
        messageDelta = 2
        goodPaths = []
        badPaths = []
        for future in asyncio.as_completed(tasks):
            result = await future
            if isOk(result):
                goodPaths.append(result.value)
            else:
                badPaths.append(result.value)
            currFileTime = time.time()
            if (currFileTime - lastMsgTime) >= messageDelta:
                if not badPaths:
                    m.say(f"Updated {len(goodPaths)}/{len(newPaths)}...")
                else:
                    m.say(f"Updated {len(goodPaths)}/{len(newPaths)}, {len(badPaths)} errors...")
                lastMsgTime = currFileTime
    return goodPaths, badPaths


async def updateFile(localPrefix: str, filePath: str, session: t.Any) -> Result[str, str]:
    remotePath = ghPrefix + filePath
    localPath = localizePath(localPrefix, filePath)
    res = await downloadFile(remotePath, session)
    if isOk(res):
        res = await saveFile(localPath, res.ok())
    else:
        m.warn(f"Error downloading {filePath}, full error was:\n{await errorFromAsyncErr(res)}")
    ret: Result[str, str]
    if isErr(res):
        ret = Err(filePath)
    else:
        ret = t.cast("Ok[str]", res)
    return ret


async def errorFromAsyncErr(res: Result[str, t.Awaitable[str]]) -> str | Exception:
    if isOk(res):
        return t.cast(str, res.ok())
    try:
        x = await t.cast("t.Awaitable[str]", res.err())
    except Exception as e:
        return e
    return x


def wrapError(retry_state: t.Any) -> Err[t.Awaitable[str]]:
    return Err(asyncio.wrap_future(retry_state.outcome))


@tenacity.retry(
    reraise=True,
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_random(1, 2),
    retry_error_callback=wrapError,
)
async def downloadFile(path: str, session: t.Any) -> Result[str, t.Awaitable[str]]:
    resp = await session.request(method="GET", url=path)
    resp.raise_for_status()
    return Ok(await resp.text())


@tenacity.retry(
    reraise=True,
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_random(1, 2),
    retry_error_callback=wrapError,
)
async def saveFile(path: str, data: str) -> Result[str, t.Awaitable[str]]:
    dirPath = os.path.dirname(path)
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    async with aiofiles.open(path, "w", encoding="utf-8") as fh:
        await fh.write(data)
        return Ok(path)


def localizePath(root: str, relPath: str) -> str:
    return os.path.join(root, *relPath.split("/"))


def dictFromManifest(lines: list[str]) -> dict[str, str]:
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


def dtFromManifest(lines: list[str]) -> datetime | str | None:
    if lines[0].strip() == "error":
        return "error"
    try:
        return datetime.strptime(lines[0].strip(), "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        # Sigh, something borked
        return None


def createFinishedManifest(
    manifestLines: list[str],
    goodPaths: list[str],  # pylint: disable=unused-argument
    badPaths: list[str],
) -> str:
    if not badPaths:
        return "\n".join(manifestLines)

    # Ah, some errors.
    # First, indicate that errors happened in the timestamp,
    # so I won't spuriously refuse to re-update.

    manifestLines[0] = "error"

    # Now go thru and blank out the hashes for the bad paths,
    # so I'll definitely try to regenerate them later.

    for i, line in enumerate(manifestLines[1:], 1):
        prefix, _, path = line.strip().rpartition(" ")
        if path in badPaths:
            manifestLines[i] = "error" + ("-" * (len(prefix) - len("error"))) + " " + path

    return "\n".join(manifestLines)

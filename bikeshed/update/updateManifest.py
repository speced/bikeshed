from __future__ import annotations

import asyncio
import dataclasses
import os
import sys
import time
from datetime import datetime, timezone

import aiofiles
import aiohttp
import requests
import tenacity

from .. import messages as m
from .. import t
from ..bsresult import Err, Ok, Result, isErr, isOk
from .manifest import Manifest
from .mode import UpdateMode

# Manifest creation relies on these data structures.
# Add to them whenever new types of data files are created.
KNOWN_FILES = [
    "biblio-keys.json",
    "biblio-numeric-suffixes.json",
    "fors.json",
    "languages.json",
    "link-defaults.infotree",
    "mdn.json",
    "methods.json",
    "specs.json",
    "wpt-tests.txt",
]
KNOWN_FOLDERS = [
    "anchors",
    "biblio",
    "boilerplate",
    "caniuse",
    "headings",
    "mdn",
]

ghPrefix = "https://raw.githubusercontent.com/speced/bikeshed-data/main/data/"


# To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
if sys.platform.startswith("win") and sys.version_info >= (3, 8):
    try:
        from asyncio import WindowsSelectorEventLoopPolicy  # pylint: disable=deprecated-class
    except ImportError:
        pass
    else:
        if not isinstance(asyncio.get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())


def createManifest(path: str, dryRun: bool = False) -> Manifest:
    """Generates a manifest file for all the data files."""
    manifest = Manifest.fromPath(path, allowedFiles=KNOWN_FILES, allowedFolders=KNOWN_FOLDERS)
    if not dryRun:
        manifest.save(path)
    return manifest


def updateByManifest(path: str, dryRun: bool = False, updateMode: UpdateMode = UpdateMode.MANIFEST) -> Manifest | None:
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
            oldManifest = Manifest.fromString(fh.read())
    except Exception as e:
        oldManifest = None
        m.warn(f"Couldn't find manifest from previous update run:\n  {e}")

    # Get the actual file data by regenerating the local manifest,
    # to guard against mistakes or shenanigans
    localManifest = Manifest.fromPath(path, allowedFiles=KNOWN_FILES, allowedFolders=KNOWN_FOLDERS)
    if oldManifest:
        localManifest.dt = oldManifest.dt
    else:
        # Ensure it thinks it's old
        localManifest.dt = dtZero()

    m.say("Fetching remote manifest data...")
    try:
        remoteManifestText = requests.get(ghPrefix + "manifest.txt", timeout=5).text
    except Exception as e:
        m.warn(
            f"Couldn't download remote manifest file, so can't update. Please report this!\n{e}",
        )
        m.warn("If absolutely necessary, you can update manually with `bikeshed update --skip-manifest`.")
        return None
    remoteManifest = Manifest.fromString(remoteManifestText)

    if remoteManifest is None:
        m.die("Something's gone wrong with the remote data; I can't read its timestamp. Please report this!")
        return None

    if oldManifest and oldManifest.hasError():
        # A previous update run didn't complete successfully,
        # so I definitely need to try again.

        m.warn("Previous update had some download errors, so re-running...")
    else:
        if remoteManifest.daysOld() > 2:
            m.warn(
                f"Remote data ({printDt(remoteManifest.dt)}) is more than two days older than local time ({printDt(dtNow())}); either your local time is wrong (no worries, this warning will just repeat each time) or the update process has fallen over (please report this!).",
            )
        if not (updateMode & UpdateMode.FORCE):
            # If the update isn't forced, allow it to be skipped
            # if the data is already sufficiently fresh.
            if localManifest.dt == remoteManifest.dt and localManifest.dt == dtZero():
                m.say(f"Local data is already up-to-date with remote ({printDt(localManifest.dt)})")
                return localManifest
            elif localManifest.dt > remoteManifest.dt:
                # No need to update, local data is more recent.
                m.say(
                    f"Local data is fresher ({printDt(localManifest.dt)}) than remote ({printDt(remoteManifest.dt)}), so nothing to update.",
                )
                return localManifest

    if not oldManifest or len(oldManifest.entries) == 0:
        m.say("The local manifest is borked or missing; re-downloading everything...")
    if len(remoteManifest.entries) == 0:
        m.die("The remote data doesn't have any data in it. Please report this!")
        return None
    newPaths = []
    for filePath, hash in remoteManifest.entries.items():
        if hash != localManifest.entries.get(filePath):
            # print(f"{hash} {filePath} {localManifest.entries.get(filePath)}")
            newPaths.append(filePath)
    if not dryRun:
        deletedPaths = []
        for filePath in localManifest.entries:
            relPath = localizePath(path, filePath)
            if filePath not in remoteManifest.entries and os.path.exists(relPath):
                os.remove(relPath)
                deletedPaths.append(filePath)
        if deletedPaths:
            m.say("Deleted {} old data file{}.".format(len(deletedPaths), "s" if len(deletedPaths) > 1 else ""))

    newManifest = None
    if not dryRun:
        if newPaths:
            m.say(f"Updating {len(newPaths)} file{'s' if len(newPaths) > 1 else ''}...")
        _, badPaths = asyncio.run(updateFiles(path, newPaths))
        newManifest = dataclasses.replace(remoteManifest)
        for badPath in badPaths:
            newManifest.entries[badPath] = None
        try:
            with open(os.path.join(path, "manifest.txt"), "w", encoding="utf-8") as fh:
                fh.write(str(newManifest))
        except Exception as e:
            m.warn(f"Couldn't save new manifest file.\n{e}")
            return None
    if newManifest is None:
        newManifest = Manifest.fromPath(path, allowedFiles=KNOWN_FILES, allowedFolders=KNOWN_FOLDERS)

    if not badPaths:
        m.say("Done!")
        return newManifest
    else:
        phrase = f"were {len(badPaths)} errors" if len(badPaths) > 1 else "was 1 error"
        m.die(
            f"Done, but there {phrase} (of {len(newPaths)} total) in downloading or saving. Run `bikeshed update` again to retry.",
        )
        return newManifest


async def updateFiles(localPrefix: str, newPaths: list[str]) -> tuple[list[str], list[str]]:
    tasks = set()
    async with aiohttp.ClientSession(trust_env=True) as session:
        for filePath in newPaths:
            coro = updateFile(localPrefix, filePath, session=session)
            tasks.add(coro)

        lastMsgTime = time.time()
        messageDelta = 2
        goodPaths: list[str] = []
        badPaths: list[str] = []
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


def printDt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def formatDt(dt: datetime) -> str:
    return datetime.strftime(dt, "%Y-%m-%d %H:%M:%S.%f")


def dtNow() -> datetime:
    return datetime.now(timezone.utc)


def dtZero() -> datetime:
    return datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

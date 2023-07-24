from __future__ import annotations

import asyncio
import os
import time

import aiofiles
import aiohttp
import requests
import tenacity
from result import Err, Ok, Result

from .. import messages as m
from .. import t


def isOk(x: t.Any) -> t.TypeGuard[Ok]:
    return isinstance(x, Ok)


def isErr(x: t.Any) -> t.TypeGuard[Err]:
    return isinstance(x, Err)


ghPrefix = "https://raw.githubusercontent.com/speced/bikeshed-boilerplate/main/"


def update(path: str, dryRun: bool = False) -> set[str] | None:
    try:
        m.say("Downloading boilerplates...")
        data = requests.get(ghPrefix + "manifest.txt", timeout=5).text
    except Exception as e:
        m.die(f"Couldn't download boilerplates manifest.\n{e}")
        return None

    newPaths = pathsFromManifest(data)

    if not dryRun:
        m.say(
            f"Updating {len(newPaths)} file{'s' if len(newPaths) > 1 else ''}...",
        )
        goodPaths, badPaths = asyncio.run(updateFiles(path, newPaths))
    if not badPaths:
        m.say("Done!")
        return set(goodPaths)
    else:
        phrase = f"were {len(badPaths)} errors" if len(badPaths) > 1 else "was 1 error"
        m.die(
            f"Done, but there {phrase} (of {len(newPaths)} total) in downloading or saving. Run `bikeshed update` again to retry.",
        )
        return set(goodPaths)


def pathsFromManifest(manifest: str) -> list[str]:
    lines = manifest.split("\n")[1:]
    return [line.partition(" ")[2] for line in lines if line != ""]


async def updateFiles(localPrefix: str, newPaths: t.Sequence[str]) -> tuple[list[str], list[str]]:
    tasks = set()
    async with aiohttp.ClientSession(trust_env=True) as session:
        for filePath in newPaths:
            coro = updateFile(localPrefix, filePath, session=session)
            tasks.add(coro)

        lastMsgTime = time.time()
        messageDelta = 2
        goodPaths = []
        badPaths = []
        for future in asyncio.as_completed(tasks):
            result = await future
            if result.is_ok():
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

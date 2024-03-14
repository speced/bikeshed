from __future__ import annotations

import json
import re

import requests

from .. import messages as m
from .. import t


def checkEchidna(pubToken: str) -> None:
    match = re.match(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", pubToken)
    if not match:
        m.die(
            f"Publication id doesn't appear to be valid. It should be a UUID, consisting of 8-4-4-4-12 hex digits. Got:\n{pubToken}",
        )
        return None

    url = f"https://labs.w3.org/echidna/api/status?id={pubToken}"
    try:
        response = requests.get(url, timeout=5)
    except Exception as e:
        m.die(f"Error retrieving the publication data.\n{e}")
        return None

    text = response.text
    if text.startswith("No job found with"):
        m.say(
            "Either the publication id is no longer valid, or the job hasn't been started yet. Try again in 10-15 seconds.",
        )

    try:
        data = json.loads(text)
    except Exception as e:
        m.die(f"Error parsing the publication data as JSON:\n{e}")

    if "results" in data:
        results = data["results"]

        if results["status"] == "started":
            printProgress(results["jobs"])
        elif results["status"] == "success":
            printSuccess(results["history"])
        else:
            m.say(f"Some sort of failure; this error message will be improved.\n{text}")


def printSuccess(history: t.JSONT) -> None:
    for item in history.values():
        text = item["fact"]
        match = re.match("The document has been published.*", text)
        if not match:
            continue
        match = re.search(">([^<]+)</a>", text)
        if not match:
            m.say(f"Successfully published, but can't figure out where. Here's the text I tried to parse:\n{text}")
            return
        url = match.group(1)
        break
    else:
        m.say(
            f"Echidna claims it was published, but I couldn't find the publication entry in the history. Full history:\n{json.dumps(history, indent=2)}",
        )
        return None

    m.success(f"Published to {url}")


def printProgress(jobs: t.JSONT) -> None:
    for jobName, jobData in jobs.items():
        if jobData["status"] == "ok":
            continue
        elif jobData["status"] == "pending":
            m.say(f"Currently pending on {printJobName(jobName)}, please wait.")
            return
        elif jobData["status"] == "error":
            m.failure(f"Publication failed on {printJobName(jobName)}, errors are:\n{printErrors(jobData['errors'])}")
        else:
            m.say(
                f"Unknown job status '{jobData['status']}' on {printJobName(jobName)}, so status is unknown. Here's the full job:\n{json.dumps({jobName: jobData}, indent=2)}",
            )


def printJobName(name: str) -> str:
    return name


def printErrors(errors: list[str]) -> str:
    return "\n".join(errors)

from __future__ import annotations

import email.utils
import errno
import os
import sys
import urllib.parse
from abc import abstractmethod
from datetime import datetime
from typing import List, Optional

import attr
import requests
import tenacity

from .Line import Line


@attr.s(auto_attribs=True)
class InputContent:
    rawLines: List[str]
    date: Optional[datetime.date]

    @property
    def lines(self) -> List[Line]:
        return [Line(i, line) for i, line in enumerate(self.rawLines, 1)]

    @property
    def content(self) -> str:
        return "".join(self.rawLines)


class InputSource:
    """Represents a thing that can produce specification input text.

    Input can be read from stdin ("-"), an HTTPS URL, or a file. Other
    InputSources can be found relative to URLs and files, and there's a context
    manager for temporarily switching to the directory of a file InputSource.
    """

    def __new__(cls, sourceName: str):
        """Dispatches to the right subclass."""
        if cls != InputSource:
            # Only take control of calls to InputSource(...) itself.
            return super().__new__(cls)

        if sourceName == "-":
            return StdinInputSource(sourceName)
        if sourceName.startswith("https:"):
            return UrlInputSource(sourceName)
        return FileInputSource(sourceName)

    @abstractmethod
    def __str__(self) -> str:
        pass

    def __repr__(self) -> str:
        return "{}({!r})".format(self.__class__.__name__, str(self))

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    @abstractmethod
    def read(self) -> InputContent:
        """Fully reads the source."""

    def hasDirectory(self) -> bool:
        """Only some InputSources have a directory."""
        return False

    def directory(self) -> str:
        """Suitable for passing to subprocess(cwd=)."""
        raise TypeError("{} instances don't have directories.".format(type(self)))

    def relative(self, _) -> Optional[InputSource]:
        """Resolves relativePath relative to this InputSource.

        For example, InputSource("/foo/bar/baz.txt").relative("quux/fuzzy.txt")
        will be InputSource("/foo/bar/quux/fuzzy.txt").

        If this source type can't find others relative to itself, returns None.
        """
        return None

    def mtime(self) -> Optional[float]:
        """Returns the last modification time of this source, if that's known."""
        return None

    def cheaplyExists(self, _) -> Optional[bool]:
        """If it's cheap to determine, returns whether relativePath exists.

        Otherwise, returns None.
        """
        return None

    def __getattr__(self, name):
        """Hack to make pylint happy, since all the attrs are defined
        on the subclasses that __new__ dynamically dispatches to.
        See https://stackoverflow.com/a/60731663/455535
        """
        print(f"No member '{name}' contained in InputSource.")
        return ""


class StdinInputSource(InputSource):
    def __init__(self, sourceName: str):
        assert sourceName == "-"
        self.type = "stdin"
        self.sourceName = sourceName
        self.content = None

    def __str__(self) -> str:
        return "-"

    def read(self) -> InputContent:
        return InputContent(sys.stdin.readlines(), None)


class UrlInputSource(InputSource):
    def __init__(self, sourceName: str):
        assert sourceName.startswith("https:")
        self.sourceName = sourceName
        self.type = "url"

    def __str__(self) -> str:
        return self.sourceName

    @tenacity.retry(
        reraise=True,
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_random(1, 2),
    )
    def _fetch(self):
        response = requests.get(self.sourceName, timeout=10)
        if response.status_code == 404:
            # This matches the OSErrors expected by older uses of
            # FileInputSource. It skips the retry, since the server has given us
            # a concrete, expected answer.
            raise FileNotFoundError(errno.ENOENT, response.text, self.sourceName)
        response.raise_for_status()
        return response

    def read(self) -> InputContent:
        response = self._fetch()
        date = None
        if "Date" in response.headers:
            # Use the response's Date header, although servers don't always set
            # this according to the last change to the file.
            date = email.utils.parsedate_to_datetime(response.headers["Date"]).date()
        return InputContent(response.text.splitlines(True), date)

    def relative(self, relativePath) -> UrlInputSource:
        return UrlInputSource(urllib.parse.urljoin(self.sourceName, relativePath))


class FileInputSource(InputSource):
    def __init__(self, sourceName: str):
        self.sourceName = sourceName
        self.type = "file"
        self.content = None

    def __str__(self) -> str:
        return self.sourceName

    def read(self) -> InputContent:
        with open(self.sourceName, encoding="utf-8") as f:
            return InputContent(
                f.readlines(),
                datetime.fromtimestamp(os.path.getmtime(self.sourceName)).date(),
            )

    def hasDirectory(self) -> bool:
        return True

    def directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.sourceName))

    def relative(self, relativePath) -> FileInputSource:
        return FileInputSource(os.path.join(self.directory(), relativePath))

    def cheaplyExists(self, relativePath) -> bool:
        return os.access(self.relative(relativePath).sourceName, os.R_OK)

    def mtime(self) -> Optional[float]:
        """Returns the last modification time of this file, or None if it doesn't exist."""
        try:
            return os.stat(self.sourceName).st_mtime
        except FileNotFoundError:
            return None

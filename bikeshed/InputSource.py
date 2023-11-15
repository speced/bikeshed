from __future__ import annotations

import datetime
import email.utils
import errno
import os
import sys
import tarfile
import urllib.parse
from abc import abstractmethod

import attr
import requests
import tenacity

from . import config, constants, line, t
from . import messages as m


@attr.s(auto_attribs=True)
class InputContent:
    rawLines: list[str]
    date: datetime.date | None

    @property
    def lines(self) -> list[line.Line]:
        ret = []
        offset = 0
        for i, text in enumerate(self.rawLines, 1):
            lineNo = i + offset
            # The early HTML parser can change how nodes print,
            # so they occupy a different number of lines than they
            # had in the source. Markdown parser needs to know
            # the correct source lines, tho, so when this happens,
            # the nodes will insert special PUA chars to indicate that.
            # I can remove them here and properly adjust the line number.
            # Current known causes of this:
            # * line-ending -- turned into em dashes
            # * multi-line start tags
            # * multi-line markdown code spans;
            #     - the text loses its newlines
            #     - the original text goes into an attribute on the start
            #       tag now
            ilcc = constants.incrementLineCountChar
            dlcc = constants.decrementLineCountChar
            if ilcc in text:
                offset += text.count(ilcc)
                text = text.replace(ilcc, "")
            if dlcc in text:
                offset -= text.count(dlcc)
                text = text.replace(dlcc, "")

            ret.append(line.Line(lineNo, text))

        return ret

    @property
    def content(self) -> str:
        return "".join(self.rawLines)


def inputFromName(sourceName: str, **kwargs: t.Any) -> InputSource:
    if sourceName == "-":
        return StdinInputSource(sourceName)
    if sourceName.startswith("https:"):
        return UrlInputSource(sourceName)
    if not sourceName.endswith((".bs", ".src.html")) and os.path.exists(sourceName) and tarfile.is_tarfile(sourceName):
        return TarInputSource(sourceName, **kwargs)
    return FileInputSource(sourceName, **kwargs)


class InputSource:
    """Represents a thing that can produce specification input text.

    Input can be read from stdin ("-"), an HTTPS URL, or a file. Other
    InputSources can be found relative to URLs and files, and there's a context
    manager for temporarily switching to the directory of a file InputSource.
    """

    @abstractmethod
    def __str__(self) -> str:
        pass

    def __repr__(self) -> str:
        return "{}({!r})".format(self.__class__.__name__, str(self))

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        return str(self) == str(other)

    @abstractmethod
    def read(self) -> InputContent:
        """Fully reads the source."""

    def hasDirectory(self) -> bool:
        """Only some InputSources have a directory."""
        return False

    def directory(self) -> str:
        """Suitable for passing to subprocess(cwd=)."""
        msg = f"{type(self)} instances don't have directories."
        raise TypeError(msg)

    def relative(self, _: t.Any) -> InputSource | None:
        """Resolves relativePath relative to this InputSource.

        For example, InputSource("/foo/bar/baz.txt").relative("quux/fuzzy.txt")
        will be InputSource("/foo/bar/quux/fuzzy.txt").

        If this source type can't find others relative to itself, returns None.
        """
        return None

    def mtime(self) -> float | None:
        """Returns the last modification time of this source, if that's known."""
        return None

    def cheaplyExists(self, _: t.Any) -> bool | None:
        """If it's cheap to determine, returns whether relativePath exists.

        Otherwise, returns None.
        """
        return None

    def __getattr__(self, name: str) -> str:
        """Hack to make pylint happy, since all the attrs are defined
        on the subclasses that __new__ dynamically dispatches to.
        See https://stackoverflow.com/a/60731663/455535
        """
        m.warn(f"No member '{name}' contained in InputSource.")
        return ""


class StdinInputSource(InputSource):
    def __init__(self, sourceName: str, **kwargs: t.Any) -> None:  # pylint: disable=unused-argument
        assert sourceName == "-"
        self.type = "stdin"
        self.sourceName = sourceName
        self.content = None

    def __str__(self) -> str:
        return "-"

    def read(self) -> InputContent:
        return InputContent(sys.stdin.readlines(), None)


class UrlInputSource(InputSource):
    def __init__(self, sourceName: str, **kwargs: t.Any) -> None:  # pylint: disable=unused-argument
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
    def _fetch(self) -> requests.Response:
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
        return InputContent([x + "\n" for x in response.text.splitlines(False)], date)

    def relative(self, relativePath: str) -> UrlInputSource:
        return UrlInputSource(urllib.parse.urljoin(self.sourceName, relativePath))


class FileInputSource(InputSource):
    def __init__(self, sourceName: str, *, chroot: bool, chrootPath: str | None = None) -> None:
        self.sourceName = sourceName
        self.chrootPath = chrootPath
        self.type = "file"
        self.content = None

        if chroot and self.chrootPath is None:
            self.chrootPath = self.directory()
        if self.chrootPath is not None:
            self.sourceName = config.chrootPath(self.chrootPath, self.sourceName)

    def __str__(self) -> str:
        return self.sourceName

    def read(self) -> InputContent:
        with open(self.sourceName, encoding="utf-8") as f:
            return InputContent(
                f.readlines(),
                datetime.datetime.fromtimestamp(os.path.getmtime(self.sourceName)).date(),
            )

    def hasDirectory(self) -> bool:
        return True

    def directory(self) -> str:
        return os.path.dirname(os.path.abspath(self.sourceName))

    def relative(self, relativePath: str) -> FileInputSource:
        return FileInputSource(
            os.path.join(self.directory(), relativePath),
            chroot=False,
            chrootPath=self.chrootPath,
        )

    def cheaplyExists(self, relativePath: str) -> bool:
        return os.access(self.relative(relativePath).sourceName, os.R_OK)

    def mtime(self) -> float | None:
        """Returns the last modification time of this file, or None if it doesn't exist."""
        try:
            return os.stat(self.sourceName).st_mtime
        except FileNotFoundError:
            return None


class TarInputSource(InputSource):
    def __init__(self, sourceName: str, *, tarMemberName: str = "index.bs", **_: t.Any) -> None:
        self.sourceName = sourceName
        self.tarMemberName = tarMemberName
        self.type = "tar"
        self.content = None

    def __str__(self) -> str:
        return self.sourceName + ":" + self.tarMemberName

    def read(self) -> InputContent:
        with self._openTarFile() as tarFile:
            mtime = self.mtime()
            if mtime is None:
                ts = None
            else:
                ts = datetime.datetime.fromtimestamp(mtime).date()
            try:
                taritem = tarFile.extractfile(self.tarMemberName)
                if taritem is None:
                    raise FileNotFoundError(
                        errno.ENOENT,
                        f"{self.tarMemberName} is in the tar file, but isn't a file itself.",
                    )
                with taritem as f:
                    # Decode the `bytes` to a `str`. (extractfile can't read as text.)
                    file_contents = f.read().decode(encoding="utf-8").splitlines(keepends=True)
                return InputContent(file_contents, ts)
            except KeyError as e:
                raise FileNotFoundError(errno.ENOENT, "Not found inside tar file", self.tarMemberName) from e

    def hasDirectory(self) -> bool:
        return False

    def directory(self) -> str:
        # It would be possible to produce a file listing. But not a meaningful directory path.
        msg = f"{type(self)} instances don't have directories."
        raise TypeError(msg)

    def relative(self, relativePath: str) -> TarInputSource:
        """Returns an InputSource relative to this file. Since a TarInputSource is always inside the
        tar file, any relative InputSource is also inside the tar file."""
        memberPath = os.path.join(os.path.dirname(self.tarMemberName), relativePath)
        return TarInputSource(self.sourceName, tarMemberName=memberPath)

    def cheaplyExists(self, relativePath: str) -> bool | None:
        memberPath = os.path.join(os.path.dirname(self.tarMemberName), relativePath)
        with self._openTarFile() as tarFile:
            members = tarFile.getnames()
            return memberPath in members

    def mtime(self) -> float | None:
        """Returns the last modification time of this file, or None if it doesn't exist."""
        try:
            return os.stat(self.sourceName).st_mtime
        except FileNotFoundError:
            return None

    def _openTarFile(self) -> tarfile.TarFile:
        """Open the tar file so archive members can be read."""
        # The same file gets opened numerous times in a single build, but it doesn't seem to be very
        # costly, and it's easier than trying to manually manage the TarFile resource lifetime.

        # "r:" specifies the tar file must be uncompressed.
        return tarfile.open(self.sourceName, mode="r:", encoding="utf-8")

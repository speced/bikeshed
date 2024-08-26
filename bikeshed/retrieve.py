# pylint: disable=R1732

from __future__ import annotations

import io
import os

from . import InputSource, config, t
from . import messages as m

if t.TYPE_CHECKING:
    from .doctypes import Group, Org, Status


class DataFileRequester:
    def __init__(self, fileType: str | None = None, fallback: DataFileRequester | None = None) -> None:
        if fileType not in ("readonly", "latest"):
            msg = f"Bad value for DataFileRequester.type, got '{fileType}'."
            raise Exception(msg)
        self.fileType: str = fileType
        # fallback is another requester, used if the main one fails.
        self.fallback = fallback

    def path(self, *segs: str, fileType: str | None = None) -> str:
        return self._buildPath(segs=segs, fileType=fileType or self.fileType)

    @t.overload
    def fetch(self, *segs: str, str: t.Literal[True], okayToFail: bool = False, fileType: str | None = None) -> str: ...

    @t.overload
    def fetch(
        self,
        *segs: str,
        str: t.Literal[False],
        okayToFail: bool = False,
        fileType: str | None = None,
    ) -> io.TextIOWrapper: ...

    @t.overload
    def fetch(self, *segs: str, okayToFail: bool = False, fileType: str | None = None) -> io.TextIOWrapper: ...

    def fetch(
        self,
        *segs: str,
        str: bool = False,
        okayToFail: bool = False,
        fileType: str | None = None,
    ) -> str | io.TextIOWrapper:
        location = self._buildPath(segs=segs, fileType=fileType or self.fileType)
        try:
            if str:
                with open(location, encoding="utf-8") as fh:
                    return fh.read()
            else:
                return open(location, encoding="utf-8")  # noqa: SIM115
        except OSError:
            if self.fallback:
                try:
                    if str:
                        return self.fallback.fetch(*segs, str=True, okayToFail=okayToFail)
                    else:
                        return self.fallback.fetch(*segs, str=False, okayToFail=okayToFail)
                except OSError:
                    if str:
                        return self._fail(location, str=True, okayToFail=okayToFail)
                    else:
                        return self._fail(location, str=False, okayToFail=okayToFail)
            return self._fail(location, str, okayToFail)

    def walkFiles(self, *segs: str, fileType: str | None = None) -> t.Generator[str, None, None]:
        for _, _, files in os.walk(self._buildPath(segs, fileType=fileType or self.fileType)):
            yield from files

    def _buildPath(self, segs: t.Sequence[str], fileType: str | None = None) -> str:
        if fileType is None:
            fileType = self.fileType
        if fileType == "readonly":
            return config.scriptPath("spec-data", "readonly", *segs)
        else:
            return config.scriptPath("spec-data", *segs)

    @t.overload
    def _fail(self, location: str, str: t.Literal[True], okayToFail: bool) -> str: ...

    @t.overload
    def _fail(self, location: str, str: t.Literal[False], okayToFail: bool) -> io.TextIOWrapper: ...

    @t.overload
    def _fail(self, location: str, str: bool, okayToFail: bool) -> str | io.TextIOWrapper: ...

    def _fail(self, location: str, str: bool, okayToFail: bool) -> str | io.TextIOWrapper:
        if okayToFail:
            if str:
                return ""
            else:
                return io.StringIO("")
        msg = f"Couldn't find file '{location}'"
        raise OSError(msg)


defaultRequester = DataFileRequester(fileType="latest", fallback=DataFileRequester(fileType="readonly"))


def retrieveBoilerplateFile(
    doc: t.SpecT,
    name: str,
    group: Group | None = None,
    status: Status | None = None,
    org: Org | None = None,
    quiet: bool = False,
    allowLocal: bool = True,
    fileRequester: DataFileRequester | None = None,
) -> str:
    # Looks in three or four locations, in order:
    # the folder the spec source is in, the group's boilerplate folder, the megagroup's boilerplate folder, and the generic boilerplate folder.
    # In each location, it first looks for the file specialized on status, and then for the generic file.
    # Filenames must be of the format NAME.include or NAME-STATUS.include
    if fileRequester is None:
        dataFile = doc.dataFile
    else:
        dataFile = fileRequester

    if group is None:
        group = doc.doctype.group
    groupName = group.name.lower() if group else None
    if status is None:
        status = doc.doctype.status
    statusName = status.name.upper() if status else None
    if org is None:
        org = doc.doctype.org
    orgName = org.name.lower() if org else None

    searchLocally = allowLocal and doc.md.localBoilerplate[name]

    def boilerplatePath(*segs: str) -> str:
        return dataFile.path("boilerplate", *segs)

    filenames = []
    if statusName:
        filenames.append(f"{name}-{statusName}.include")
    filenames.append(f"{name}.include")

    sources: list[InputSource.InputSource] = []
    # 1: Look locally
    if searchLocally:
        for fn in filenames:
            source = doc.inputSource.relative(fn)
            if source:
                sources.append(source)
    else:
        for fn in filenames:
            if doc.inputSource.cheaplyExists(fn):
                m.warn(
                    f"Found {fn} next to the specification without a matching\n"
                    + f"Local Boilerplate: {name} yes\n"
                    + "in the metadata. This include won't be found when building via a URL.",
                )
                # We should remove this after giving specs time to react to the warning:
                source = doc.inputSource.relative(fn)
                if source:
                    sources.append(source)
    # 2: Look in the group's folder
    if groupName:
        sources.extend(InputSource.FileInputSource(boilerplatePath(groupName, fn), chroot=False) for fn in filenames)
    # 3: Look in the org's folder
    if orgName:
        sources.extend(InputSource.FileInputSource(boilerplatePath(orgName, fn), chroot=False) for fn in filenames)
    # 4: Look in the generic defaults
    sources.extend(InputSource.FileInputSource(boilerplatePath(fn), chroot=False) for fn in filenames)

    # Watch all the possible sources, not just the one that got used, because if
    # an earlier one appears, we want to rebuild.
    doc.recordDependencies(*sources)

    for source in sources:
        try:
            content = source.read().content
            return content
        except OSError:
            # That input doesn't exist.
            pass
    if not quiet:
        components = []
        if orgName:
            components.append(f"Org '{orgName}'")
        if groupName:
            components.append(f"Group '{groupName}'")
        if statusName:
            components.append(f"Status '{statusName}'")
        msg = "Couldn't find an appropriate include file for the {name} inclusion"
        if components:
            msg += ", given " + config.englishFromList(components, "and")
        else:
            msg += "."
        m.die(msg)
    return ""

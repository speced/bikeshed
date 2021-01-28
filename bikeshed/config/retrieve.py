import io
import os

from ..InputSource import InputSource
from ..messages import *
from .main import scriptPath
from .status import splitStatus


class DataFileRequester:
    def __init__(self, type=None, fallback=None):
        self.type = type
        if self.type not in ("readonly", "latest"):
            raise Exception(f"Bad value for DataFileRequester.type, got '{type}'.")
        # fallback is another requester, used if the main one fails.
        self.fallback = fallback

    def fetch(self, *segs, **kwargs):
        str = kwargs.get("str", False)
        okayToFail = kwargs.get("okayToFail", False)
        fileType = kwargs.get("type", self.type)
        location = self._buildPath(segs=segs, fileType=fileType)
        try:
            if str:
                with open(location, encoding="utf-8") as fh:
                    return fh.read()
            else:
                return open(location, encoding="utf-8")
        except OSError:
            if self.fallback:
                try:
                    return self.fallback.fetch(*segs, str=str, okayToFail=okayToFail)
                except OSError:
                    return self._fail(location, str, okayToFail)
            return self._fail(location, str, okayToFail)

    def walkFiles(self, *segs, **kwargs):
        fileType = kwargs.get("type", self.type)
        for _, _, files in os.walk(self._buildPath(segs, fileType=fileType)):
            yield from files

    def _buildPath(self, segs, fileType=None):
        if fileType is None:
            fileType = self.type
        if fileType == "readonly":
            return scriptPath("spec-data", "readonly", *segs)
        else:
            return scriptPath("spec-data", *segs)

    def _fail(self, location, str, okayToFail):
        if okayToFail:
            if str:
                return ""
            else:
                return io.StringIO("")
        raise OSError(f"Couldn't find file '{location}'")


defaultRequester = DataFileRequester(
    type="latest", fallback=DataFileRequester(type="readonly")
)


def retrieveBoilerplateFile(doc, name, group=None, status=None, error=True):
    # Looks in three or four locations, in order:
    # the folder the spec source is in, the group's boilerplate folder, the megagroup's boilerplate folder, and the generic boilerplate folder.
    # In each location, it first looks for the file specialized on status, and then for the generic file.
    # Filenames must be of the format NAME.include or NAME-STATUS.include
    if group is None and doc.md.group is not None:
        group = doc.md.group.lower()
    if status is None:
        if doc.md.status is not None:
            status = doc.md.status
        elif doc.md.rawStatus is not None:
            status = doc.md.rawStatus
    megaGroup, status = splitStatus(status)

    searchLocally = doc.md.localBoilerplate[name]

    def boilerplatePath(*segs):
        return scriptPath("boilerplate", *segs)

    statusFile = f"{name}-{status}.include"
    genericFile = f"{name}.include"
    sources = []
    if searchLocally:
        sources.append(doc.inputSource.relative(statusFile))  # Can be None.
        sources.append(doc.inputSource.relative(genericFile))
    else:
        for f in (statusFile, genericFile):
            if doc.inputSource.cheaplyExists(f):
                warn(
                    (
                        "Found {0} next to the specification without a matching\n"
                        + "Local Boilerplate: {1} yes\n"
                        + "in the metadata. This include won't be found when building via a URL."
                    ).format(f, name)
                )
                # We should remove this after giving specs time to react to the warning:
                sources.append(doc.inputSource.relative(f))
    if group:
        sources.append(InputSource(boilerplatePath(group, statusFile)))
        sources.append(InputSource(boilerplatePath(group, genericFile)))
    if megaGroup:
        sources.append(InputSource(boilerplatePath(megaGroup, statusFile)))
        sources.append(InputSource(boilerplatePath(megaGroup, genericFile)))
    sources.append(InputSource(boilerplatePath(statusFile)))
    sources.append(InputSource(boilerplatePath(genericFile)))

    # Watch all the possible sources, not just the one that got used, because if
    # an earlier one appears, we want to rebuild.
    doc.recordDependencies(*sources)

    for source in sources:
        if source is not None:
            try:
                return source.read().content
            except OSError:
                # That input doesn't exist.
                pass
    else:
        if error:
            die(
                "Couldn't find an appropriate include file for the {0} inclusion, given group='{1}' and status='{2}'.",
                name,
                group,
                status,
            )
        return ""

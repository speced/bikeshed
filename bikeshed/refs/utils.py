from __future__ import annotations

from collections import defaultdict

from .. import config, t


def filterObsoletes(
    refs: list[t.RefWrapper],
    replacedSpecs: set[tuple[str, str]],
    ignoredSpecs: set[str],
    localShortname: str | None = None,
    localSpec: str | None = None,
) -> list[t.RefWrapper]:
    # Remove any ignored or obsoleted specs
    possibleSpecs = {ref.spec for ref in refs}
    if localSpec:
        possibleSpecs.add(localSpec)
    moreIgnores = set()
    for oldSpec, newSpec in replacedSpecs:
        if newSpec in possibleSpecs:
            moreIgnores.add(oldSpec)
    ret = []
    for ref in refs:
        if ref.spec in ignoredSpecs:
            continue
        if ref.spec in moreIgnores:
            continue
        if ref.status != "local" and ref.shortname == localShortname:
            continue
        ret.append(ref)
    return ret


def filterOldVersions(refs: list[t.RefWrapper], status: str | None = None) -> list[t.RefWrapper]:
    # If multiple levels of the same shortname exist,
    # only use the latest level.
    # If generating for a snapshot, prefer the latest snapshot level,
    # unless that doesn't exist, in which case just prefer the latest level.
    shortnameLevels: defaultdict[str, defaultdict[str, list[t.RefWrapper]]] = defaultdict(lambda: defaultdict(list))
    snapshotShortnameLevels: defaultdict[str, defaultdict[str, list[t.RefWrapper]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for ref in refs:
        shortnameLevels[ref.shortname][ref.level].append(ref)
        if status == ref.status == "snapshot":
            snapshotShortnameLevels[ref.shortname][ref.level].append(ref)
    refs = []
    for shortname, levelSet in shortnameLevels.items():
        if status == "snapshot" and snapshotShortnameLevels[shortname]:
            # Get the latest snapshot refs if they exist and you're generating a snapshot...
            maxLevel = max(snapshotShortnameLevels[shortname].keys())
            refs.extend(snapshotShortnameLevels[shortname][maxLevel])
        else:
            # Otherwise just grab the latest refs regardless.
            maxLevel = max(levelSet.keys())
            refs.extend(levelSet[maxLevel])
    return refs


def linkTextVariations(str: str, linkType: str | None) -> t.Generator[str, None, None]:
    # Generate intelligent variations of the provided link text,
    # so explicitly adding an lt attr isn't usually necessary.
    str = str.strip()
    yield str

    if len(str) == 0:
        # empty string got thru somehow, no use conjugating
        return

    if linkType is None:
        return
    elif linkType == "dfn":
        last1 = str[-1]
        last2 = str[-2:]
        last3 = str[-3:]

        # Berries <-> Berry
        if last3 == "ies":
            yield str[:-3] + "y"
        if last1 == "y":
            yield str[:-1] + "ies"

        # Blockified <-> Blockify
        if last3 == "ied":
            yield str[:-3] + "y"
        if last1 == "y":
            yield str[:-1] + "ied"

        # Zeroes <-> Zero
        if last2 == "es":
            yield str[:-2]
        else:
            yield str + "es"

        # Bikeshed's <-> Bikeshed
        if last2 in ("'s", "’s"):
            yield str[:-2]
        else:
            yield str + "'s"

        # Bikesheds <-> Bikeshed
        if last1 == "s":
            yield str[:-1]
        else:
            yield str + "s"

        # Bikesheds <-> Bikesheds'
        if last1 in ("'", "’"):
            yield str[:-1]
        else:
            yield str + "'"

        # Snapped <-> Snap
        if last2 == "ed" and len(str) >= 4 and str[-3] == str[-4]:
            yield str[:-3]
        elif last1 in "bdfgklmnprstvz":
            yield str + last1 + "ed"

        # Zeroed <-> Zero
        if last2 == "ed":
            yield str[:-2]
        else:
            yield str + "ed"

        # Generated <-> Generate
        if last1 == "d":
            yield str[:-1]
        else:
            yield str + "d"

        # Navigating <-> Navigate
        if last3 == "ing":
            yield str[:-3]
            yield str[:-3] + "e"
        elif last1 == "e":
            yield str[:-1] + "ing"
        else:
            yield str + "ing"

        # Snapping <-> Snap
        if last3 == "ing" and len(str) >= 5 and str[-4] == str[-5]:
            yield str[:-4]
        elif last1 in "bdfgklmnprstvz":
            yield str + last1 + "ing"

        # Insensitive <-> Insensitively
        if last2 == "ly":
            yield str[:-2]
        else:
            yield str + "ly"

        # Special irregular case: throw <-> thrown
        if str == "throw":
            yield "thrown"
        if str == "thrown":
            yield "throw"

    if " " in str and (config.linkTypeIn(linkType, "dfn") or config.linkTypeIn(linkType, "abstract-op")):
        # Multi-word phrase, which often contains the conjugated word as the *first*,
        # rather than at the end.
        first, _, rest = str.partition(" ")
        for variation in linkTextVariations(first, linkType):
            yield variation + " " + rest

    if config.linkTypeIn(linkType, "idl"):
        # _or <-> or
        if str[0] == "_":
            yield str[1:]
        else:
            yield "_" + str

        # Let people refer to methods without the parens.
        # Since attrs and methods live in the same namespace, this is safe.
        if "(" not in str:
            yield str + "()"

        # Allow linking to an enum-value with or without quotes
        if str[0] == '"':
            yield str[1:-1]
        if str[0] != '"':
            yield '"' + str + '"'


if t.TYPE_CHECKING:
    U = t.TypeVar("U", bound="t.MutableMapping|t.MutableSequence")


def stripLineBreaks(obj: U) -> U:
    it = obj.items() if isinstance(obj, dict) else enumerate(obj)
    for key, val in it:
        if isinstance(val, str):
            obj[key] = val.rstrip("\n")
        elif isinstance(val, (dict, list)):
            stripLineBreaks(val)
    return obj

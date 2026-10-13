# pylint: disable=unused-argument

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from isodate import parse_duration

from .. import config, constants, h, repository, t
from .. import messages as m

if t.TYPE_CHECKING:

    class ParseFunc(t.Protocol):
        def __call__(self, key: str, val: str, lineNum: str | int | None) -> t.Any: ...

    from ..stringEnum import StringEnum


def parseLiteral(key: str, val: str, lineNum: str | int | None) -> str:
    return val


def parseLiteralOrNone(key: str, val: str, lineNum: str | int | None) -> str | None:
    if val.lower() == "none":
        return None
    return val


def parseLiteralCaseless(key: str, val: str, lineNum: str | int | None) -> str:
    return val.lower()


def parseLiteralList(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [val]


def parseFixedList(key: str, val: str, validValues: list[str], lineNum: str | int | None) -> str | None:
    val = val.lower()
    if val in validValues:
        return val
    printableValues = config.englishFromList(f"'{x}'" for x in validValues)
    m.die(
        f"{key} metadata only accepts the values {printableValues}. Got '{val}'.",
        lineNum=lineNum,
    )
    return None


def parseStringEnum(key: str, val: str, enum: StringEnum, lineNum: str | int | None) -> str | None:
    val = val.strip().lower()
    if val in enum:
        return val
    printableValues = config.englishFromList(f"'{x}'" for x in list(enum))
    m.die(f"'{key}' must be {printableValues}. Got '{val}'", lineNum=lineNum)
    return None


def parseDate(key: str, val: str, lineNum: str | int | None) -> date | None:
    if val == "now":
        return datetime.utcnow().date()
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        m.die(f'The {key} field must be in the format YYYY-MM-DD - got "{val}" instead.', lineNum=lineNum)
        return None


def parseDateOrDuration(key: str, val: str, lineNum: str | int | None) -> date | timedelta | None:
    if val == "now":
        return datetime.utcnow().date()
    if val == "never" or boolish(val) is False:
        return None
    try:
        if val.startswith("P"):
            return t.cast(timedelta, parse_duration(val))
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        m.die(
            f"The {key} field must be an ISO 8601 duration, a date in the format YYYY-MM-DD, now, never, false, no, n, or off. Got '{val}' instead.",
            lineNum=lineNum,
        )
        return None


def parseLevel(key: str, val: str, lineNum: str | int | None) -> str:
    val = val.lower().strip()
    if val == "none":
        return ""
    return val.strip()


def parseInteger(key: str, val: str, lineNum: str | int | None) -> int:
    return int(val)


def parseBoolean(key: str, val: str, lineNum: str | int | None) -> bool | None:
    b = boolish(val)
    if b is None:
        m.die(f"The {key} field must be true/false, yes/no, y/n, or on/off. Got '{val}' instead.", lineNum=lineNum)
    return b


def parseSoftBoolean(key: str, val: str, lineNum: str | int | None) -> bool | t.Literal["maybe"] | None:
    b = boolish(val)
    if b is not None:
        return b
    if val.lower() in ["maybe", "if possible", "if needed"]:
        return "maybe"
    m.die(f"The {key} field must be boolish, or 'maybe'. Got '{val}' instead.", lineNum=lineNum)
    return None


def parseBoolishList(
    key: str,
    val: str,
    default: bool,
    validLabels: t.AbstractSet[str] | None = None,
    extraValues: dict[str, bool] | None = None,
    lineNum: str | int | None = None,
) -> config.BoolSet:
    # Parses anything defined as "label <boolish>, label <boolish>" into a BoolSet
    # Supply a list of valid labels if you want to have them checked,
    # and a dict of {value=>bool} pairs you want in addition to the standard boolish values
    boolset = config.BoolSet(default=default)

    if extraValues is None:
        extraValues = {}
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        name, _, boolstring = v.strip().rpartition(" ")
        if not name or not boolstring:
            m.die(f"{key} metadata pieces are a label and a boolean. Got:\n{v}", lineNum=lineNum)
            continue
        if validLabels and name not in validLabels:
            m.die(
                f"Unknown {key} label '{name}'. Valid values are:\n{config.englishFromList(validLabels, "or")}",
                lineNum=lineNum,
            )
            continue
        if boolstring in extraValues:
            boolset[name] = extraValues[boolstring]
        else:
            onoff = boolish(boolstring)
            if isinstance(onoff, bool):
                boolset[name] = onoff
            else:
                m.die(f"{key} metadata pieces are a shorthand category and a boolean. Got:\n{v}", lineNum=lineNum)
                continue
    return boolset


def boolish(val: str) -> bool | None:
    if val.lower() in ("true", "yes", "y", "on"):
        return True
    if val.lower() in ("false", "no", "n", "off"):
        return False
    return None


def parseWarning(key: str, val: str, lineNum: str | int | None) -> tuple[str, ...] | None:
    if val.lower() == "obsolete":
        return ("warning-obsolete",)
    if val.lower() == "not ready":
        return ("warning-not-ready",)
    if val.lower() == "custom":
        return ("warning-custom",)
    match = re.match(r"Commit +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-commit", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Branch +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-branch", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Replaced By +(.+)", val, re.I)
    if match:
        return "warning-replaced-by", match.group(1)
    match = re.match(r"New Version +(.+)", val, re.I)
    if match:
        return "warning-new-version", match.group(1)
    m.die(
        f"""Unknown value "{val}" for "{key}" metadata. Expected one of:
  obsolete
  not ready
  replaced by [new url]
  new version [new url]
  commit [snapshot id] [snapshot url] replaced by [master url]
  branch [branch name] [branch url] replaced by [master url]
  custom""",
        lineNum=lineNum,
    )
    return None


def parseEditor(key: str, val: str, lineNum: None | str | int) -> list[dict[str, str | None]]:
    pieces = [h.unescape(piece.strip()) for piece in val.split(",")]

    def looksLinkish(string: str) -> bool:
        return bool(re.match(r"\w+:", string)) or looksEmailish(string)

    def looksEmailish(string: str) -> bool:
        return bool(re.match(r".+@.+\..+", string))

    data = {
        "name": pieces[0],
        "w3cid": None,
        "org": None,
        "orglink": None,
        "link": None,
        "email": None,
    }
    # Handle well-known pieces, split off the ambiguous ones
    ambiguousPieces = []
    for piece in pieces[1:]:
        if re.match(r"w3cid \d+$", piece) and data["w3cid"] is None:
            data["w3cid"] = piece[6:]
        else:
            ambiguousPieces.append(piece)
    if len(ambiguousPieces) == 3 and looksLinkish(ambiguousPieces[1]) and looksLinkish(ambiguousPieces[2]):
        # [org, email, url] or [org, url, email]
        data["org"] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data["email"] = ambiguousPieces[1]
            data["link"] = ambiguousPieces[2]
        else:
            data["link"] = ambiguousPieces[1]
            data["email"] = ambiguousPieces[2]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[0]) and looksLinkish(ambiguousPieces[1]):
        # [email, url] or [url, email]
        if looksEmailish(ambiguousPieces[0]):
            data["email"] = ambiguousPieces[0]
            data["link"] = ambiguousPieces[1]
        else:
            data["link"] = ambiguousPieces[0]
            data["email"] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[1]):
        # [org, email] or [org, url]
        data["org"] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data["email"] = ambiguousPieces[1]
        else:
            data["link"] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 1:
        # [org], [email], or [url]
        if looksLinkish(ambiguousPieces[0]):
            if looksEmailish(ambiguousPieces[0]):
                data["email"] = ambiguousPieces[0]
            else:
                data["link"] = ambiguousPieces[0]
        else:
            data["org"] = ambiguousPieces[0]
    elif len(ambiguousPieces) == 0:
        pass
    else:
        m.die(
            f"'{key}' format is '<name>, <company>?, <email-or-contact-page>?'. Got:\n{val}",
            lineNum=lineNum,
        )
        return []
    # Check if the org ends with a link
    if data["org"] is not None and " " in str(data["org"]) and looksLinkish(data["org"].split()[-1]):
        pieces = data["org"].split()
        data["orglink"] = pieces[-1]
        data["org"] = " ".join(pieces[:-1])
    # Check if the name ends with an ID.
    # TODO: remove this, it's redundant with the "w3cid ####" piece
    if data["name"] and re.search(r"\s\d+$", data["name"]):
        pieces = data["name"].split()
        data["w3cid"] = pieces[-1]
        data["name"] = " ".join(pieces[:-1])
    return [data]


def parseCommaSeparated(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [term.strip().lower() for term in val.split(",")]


def parseIdList(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [term.strip() for term in val.split(",")]


def parseLinkDefaults(key: str, val: str, lineNum: str | int | None) -> t.LinkDefaultsT:
    defaultSpecs: t.LinkDefaultsT = defaultdict(list)
    for default in val.split(","):
        match = re.match(
            r"^([\w\d-]+)  (?:\s+\( ({}) (?:\s+(snapshot|current))? \) )  \s+(.*)$".format(
                "|".join(config.dfnTypes.union(["dfn"])),
            ),
            default.strip(),
            re.X,
        )
        if match:
            spec = match.group(1)
            type = match.group(2)
            status = match.group(3)
            terms = match.group(4).split("/")
            dfnFor = None
            for term in terms:
                defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
        else:
            m.die(
                f"'{key}' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{default}",
                lineNum=lineNum,
            )
            continue
    return defaultSpecs


def parseBoilerplate(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    boilerplate = config.BoolSet(default=True)
    for command in val.split(","):
        pieces = command.lower().strip().split()
        if len(pieces) != 2:
            m.die(
                f"Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{command}",
                lineNum=lineNum,
            )
            continue
        if pieces[0] == "omit":
            # legacy syntax; allows "omit foo" in addition to the normal "foo off"/etc
            boilerplate[pieces[1]] = False
        else:
            onoff = boolish(pieces[1])
            if onoff is None:
                m.die(
                    f"Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{command}",
                    lineNum=lineNum,
                )
                continue
            boilerplate[pieces[0]] = onoff
    return boilerplate


def parseBiblioDisplay(key: str, val: str, lineNum: str | int | None) -> str:
    return parseStringEnum(key, val, constants.biblioDisplay, lineNum) or constants.biblioDisplay.index


def parseRefStatus(key: str, val: str, lineNum: str | int | None) -> str:
    # Legacy term that used to be allowed
    if val.strip().lower() == "dated":
        return "snapshot"
    return parseStringEnum(key, val, constants.refStatus, lineNum) or constants.refStatus.current


def parseComplainAbout(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    validLabels = frozenset(
        ["missing-example-ids", "broken-links", "accidental-2119", "missing-exposed", "mixed-indents"],
    )
    ret = parseBoolishList(key, val.lower(), default=False, validLabels=validLabels, lineNum=lineNum)
    return ret


def parseExternalInfotrees(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    return parseBoolishList(
        key,
        val.lower(),
        default=False,
        validLabels=frozenset(["anchors.bsdata", "link-defaults.infotree"]),
        lineNum=lineNum,
    )


def parseLinkedText(key: str, val: str, lineNum: str | int | None) -> list[tuple[str, str]]:
    # Parses anything defined as "text url, text url, text url" into a list of 2-tuples.
    entries = []
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        pieces = v.rsplit(" ", 1)
        entries.append((pieces[0], pieces[1]))
    return entries


def parseMarkupShorthands(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    # Format is comma-separated list of shorthand category followed by boolean.
    # Output is a boolset of the shorthand categories.
    validCategories = frozenset(
        [
            "algorithm",
            "biblio",
            "cddl",
            "css",
            "dfn",
            "http",
            "idl",
            "macros-in-autolinks",
            "markdown",
            "markdown-block",
            "markdown-blockquotes",
            "markdown-inline",
            "markdown-escapes",
            "markup",
            "repository-links",
        ],
    )
    ret = parseBoolishList(key, val.lower(), lineNum=lineNum, default=False, validLabels=validCategories)
    # markdown is an alias for markdown-inline.
    # TODO: convert all specs to use markdown-inline, and then turn markdown
    # into a shorthand for markdown-*.
    if ret.explicitTrue("markdown"):
        ret["markdown-inline"] = True
        del ret["markdown"]
    return ret


def parseInlineGithubIssues(key: str, val: str, lineNum: str | int | None) -> t.Literal[False] | str:
    val = val.lower()
    if val in ["title", "full"]:
        return val
    b = boolish(val)
    if b is None:
        m.die(f"Inline Github Issues must be 'title', 'full' or a boolish value. Got: '{val}'", lineNum=lineNum)
        return False
    if b is True:
        return "full"
    return False


def parseTextMacro(key: str, val: str, lineNum: str | int | None) -> list[tuple[str, str]]:
    # Each Text Macro line is just a macro name (must be uppercase)
    # followed by the text it expands to.
    try:
        name, text = val.lstrip().split(None, 1)
    except ValueError:
        m.die(f"Text Macro lines must contain a macro name followed by the macro text. Got:\n{val}", lineNum=lineNum)
        return []
    if not re.match(r"[A-Z0-9-]+$", name):
        m.die(f"Text Macro names must be all-caps and alphanumeric. Got '{name}'", lineNum=lineNum)
        return []
    return [(name, text)]


def parseWorkStatus(key: str, val: str, lineNum: str | int | None) -> str | None:
    return parseFixedList(
        key,
        val,
        ["completed", "stable", "testing", "refining", "revising", "exploring", "rewriting", "abandoned"],
        lineNum,
    )


def parseRepository(key: str, val: str, lineNum: str | int | None) -> repository.Repository | None:
    # Shortname followed by url, or just url.
    # If just url, I'll try to recognize the shortname from it; otherwise it's the url again.
    val = val.strip()
    pieces = val.split(None, 1)
    if len(pieces) == 2:
        return repository.Repository(url=pieces[0], name=pieces[1])
    if len(pieces) == 1:
        # Try to recognize a GitHub url
        match = re.match(r"https://github\.([\w.-]+)/([\w-]+)/([\w-]+)/?$", val)
        if match:
            return repository.GithubRepository(*match.groups())
        # If you just provide a user/repo pair, assume it's a github.com repo.
        # Will provide ways to opt into other repos when people care.
        match = re.match(r"([\w-]+)/([\w-]+)$", val)
        if match:
            return repository.GithubRepository("com", *match.groups())
        # Otherwise just use the url as the shortname
        return repository.Repository(url=val)
    m.die(f"Repository must be a url, optionally followed by a shortname. Got '{val}'", lineNum=lineNum)
    return None


def parseTranslateIDs(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    translations = {}
    for v in val.split(","):
        pieces = v.strip().split()
        if len(pieces) != 2:
            m.die(f"‘Translate IDs’ values must be an old ID followed by a new ID. Got '{v}'", lineNum=lineNum)
            continue
        old, new = pieces
        translations[old] = new
    return translations


def parseTranslation(key: str, val: str, lineNum: str | int | None) -> list[dict[str, str | None]]:
    # Format is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?
    pieces = val.split(",")
    if not (1 <= len(pieces) <= 3):
        m.die(
            f"Format of a Translation line is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?. Got:\n{val}",
            lineNum=lineNum,
        )
        return []
    firstParts = pieces[0].split()
    if len(firstParts) != 2:
        m.die(
            f"First part of a Translation line must be a lang-code followed by a url. Got:\n{pieces[0]}",
            lineNum=lineNum,
        )
        return []
    langCode, url = firstParts
    name = None
    nativeName = None
    for piece in pieces[1:]:
        k, v = piece.split(None, 1)
        if k.lower() == "name":
            name = v
        elif k.lower() == "native-name":
            nativeName = v
        else:
            m.die(
                f"Later parts of a Translation line must start with 'name' or 'native-name'. Got:\n{piece}",
                lineNum=lineNum,
            )
    return [{"lang-code": langCode, "url": url, "name": name, "native-name": nativeName}]


def parseAudience(key: str, val: str, lineNum: str | int | None) -> list[str]:
    # WG21 value
    values = [x.strip().upper() for x in val.strip().split(",")]
    if len(values) == 1 and values[0] == "ALL":
        return ["all"]
    elif len(values) >= 1:
        ret = []
        namedAudiences = {"CWG", "LWG", "EWG", "LEWG", "DIRECTION"}
        pseudonymAudiences = {
            "Concurrency": "SG1",
            "Modules": "SG2",
            "Networking": "SG4",
            "TM": "SG5",
            "Numerics": "SG6",
            "Reflection": "SG7",
            "FeatureTesting": "SG10",
            "UB": "SG12",
            "HMI": "SG13",
            "LowLatency": "SG14",
            "Tooling": "SG15",
            "Unicode": "SG16",
            "EWGI": "SG17",
            "LEWGI": "SG18",
            "MachineLearning": "SG19",
            "Education": "SG20",
            "Contracts": "SG21",
        }
        for v in values:
            if v in namedAudiences:
                ret.append(v)
            elif v in pseudonymAudiences:
                ret.append(pseudonymAudiences[v])
            elif re.match(r"WG\d+|SG\d+", v):
                ret.append(v)
            else:
                m.die(f"Unknown 'Audience' value '{v}'.", lineNum=lineNum)
                continue
        return ret
    else:
        m.die("Audience metadata must have at least one value if specified.")
        return []


def parseEditorTerm(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    values = [x.strip() for x in val.strip().split(",")]
    if len(values) == 2:
        return {"singular": values[0], "plural": values[1]}
    m.die(
        f"Editor Term metadata must be two comma-separated terms, giving the singular and plural term for editors. Got '{val}'.",
        lineNum=lineNum,
    )
    return {"singular": "Editor", "plural": "Editors"}


def parseMaxToCDepth(key: str, val: str, lineNum: str | int | None) -> int | float:
    if val.lower() == "none":
        return float("inf")
    try:
        v = int(val)
    except ValueError:
        m.die(
            f"Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{val}'.",
            lineNum=lineNum,
        )
        return float("inf")
    if not (1 <= v <= 5):
        m.die(
            f"Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{val}'.",
            lineNum=lineNum,
        )
        return float("inf")
    return v


def parseMetadataOrder(key: str, val: str, lineNum: str | int | None) -> list[str]:
    pieces = [x.strip() for x in val.split(",")]
    return pieces


def parseWptDisplay(key: str, val: str, lineNum: str | int | None) -> str:
    return parseFixedList(key, val, ["none", "inline", "open", "closed"], lineNum) or "none"


def parseWptErrors(key: str, val: str, lineNum: str | int | None) -> str:
    return parseFixedList(key, val, ["minimal", "verbose"], lineNum) or "minimal"


def parsePreviousVersion(key: str, val: str, lineNum: str | int | None) -> list[dict[str, str]]:
    biblioMatch = re.match(r"from biblio(\s+\S+)?", val.lower())
    if biblioMatch:
        if biblioMatch.group(1):
            return [{"type": "from-biblio", "value": biblioMatch.group(1).strip()}]
        return [{"type": "from-biblio-implicit"}]
    return [{"type": "url", "value": val}]


def parseInlineTagCommand(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    tag, _, command = val.strip().partition(" ")
    command = command.strip()
    return {tag: command}


def parseDieOn(key: str, val: str, lineNum: str | int | None) -> str:
    return parseFixedList(key, val, list(m.MESSAGE_LEVELS.keys()), lineNum) or "everything"


def parseDieWhen(key: str, val: str, lineNum: str | int | None) -> str:
    return parseFixedList(key, val, m.DEATH_TIMING, lineNum) or "late"


def parseIgnoreMdnFailure(key: str, val: str, lineNum: str | int | None) -> list[str]:
    vals = [x.strip() for x in val.split(",")]
    vals = [x[1:] if x.startswith("#") else x for x in vals]
    return vals


@dataclasses.dataclass
class LinkCheckerTimeout:
    each: int | float = 5
    total: int | float = 10


def parseLinkCheckerTimeout(key: str, val: str, lineNum: str | int | None) -> LinkCheckerTimeout:
    vals = val.strip().split()
    if len(vals) != 2:
        m.die(f"Link Checker Timeout metadata needs exactly two numbers. Got: '{val}'.", lineNum=lineNum)
        return LinkCheckerTimeout()
    try:
        each = float(vals[0])
        total = float(vals[1])
    except ValueError:
        m.die(f"Link Checker Timeout metadata needs exactly two numbers. Got: '{val}'.", lineNum=lineNum)
        return LinkCheckerTimeout()
    return LinkCheckerTimeout(each, total)


def parseCgMaturity(key: str, val: str, lineNum: str | int | None) -> str | None:
    return parseFixedList(key, val, ["draft", "transferred", "unmaintained"], lineNum)

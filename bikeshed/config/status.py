from __future__ import annotations

from .. import messages as m
from .. import t
from . import main


@t.overload
def canonicalizeStatus(rawStatus: None, group: str | None) -> None: ...


@t.overload
def canonicalizeStatus(rawStatus: str, group: str | None) -> str: ...


def canonicalizeStatus(rawStatus: str | None, group: str | None) -> str | None:
    if rawStatus is None:
        return None

    def validateW3Cstatus(group: str, status: str, rawStatus: str) -> None:
        if status == "DREAM":
            m.warn("You used Status: DREAM for a W3C document. Consider UD instead.")
            return

        if "w3c/" + status in shortToLongStatus:
            status = "w3c/" + status

        def formatStatusSet(statuses: frozenset[str]) -> str:
            return ", ".join(sorted({status.split("/")[-1] for status in statuses}))

        if group in w3cIgs and status not in w3cIGStatuses:
            m.warn(
                f"You used Status: {rawStatus}, but W3C Interest Groups are limited to these statuses: {formatStatusSet(w3cIGStatuses)}.",
            )

        if group == "tag" and status not in w3cTAGStatuses:
            m.warn(
                f"You used Status: {rawStatus}, but the TAG is are limited to these statuses: {formatStatusSet(w3cTAGStatuses)}",
            )

        if group in w3cCgs and status not in w3cCommunityStatuses:
            m.warn(
                f"You used Status: {rawStatus}, but W3C Community and Business Groups are limited to these statuses: {formatStatusSet(w3cCommunityStatuses)}.",
            )

    def megaGroupsForStatus(status: str) -> list[str]:
        # Returns a list of megagroups that recognize the given status
        mgs = []
        for key in shortToLongStatus:
            mg, _, s = key.partition("/")
            if s == status:
                mgs.append(mg)
        return mgs

    # Canonicalize the rawStatus that was passed in, into a known form.
    # Might be foo/BAR, or just BAR.
    megaGroup, _, status = rawStatus.partition("/")
    if status == "":
        status = megaGroup
        megaGroup = ""
    megaGroup = megaGroup.lower()
    status = status.upper()
    if megaGroup:
        canonStatus = megaGroup + "/" + status
    else:
        canonStatus = status

    if group is not None:
        group = group.lower()

    if group in megaGroups["w3c"]:
        validateW3Cstatus(group, canonStatus, rawStatus)

    # Using a directly-recognized status is A-OK.
    # (Either one of the unrestricted statuses,
    # or one of the restricted statuses with the correct standards-org prefix.)
    if canonStatus in shortToLongStatus:
        return canonStatus

    possibleMgs = megaGroupsForStatus(status)

    # If they specified a standards-org prefix and it wasn't found,
    # that's an error.
    if megaGroup:
        # Was the error because the megagroup doesn't exist?
        if possibleMgs:
            if megaGroup not in megaGroups:
                msg = f"Status metadata specified an unrecognized '{megaGroup}' organization."
            else:
                msg = f"Status '{status}' can't be used with the org '{megaGroup}'."
            if "" in possibleMgs:
                if len(possibleMgs) == 1:
                    msg += f" That status must be used without an org at all, like `Status: {status}`"
                else:
                    msg += " That status can only be used with the org{} {}, or without an org at all.".format(
                        "s" if len(possibleMgs) > 1 else "",
                        main.englishFromList(f"'{x}'" for x in possibleMgs if x != ""),
                    )
            else:
                if len(possibleMgs) == 1:
                    msg += f" That status can only be used with the org '{possibleMgs[0]}', like `Status: {possibleMgs[0]}/{status}`"
                else:
                    msg += " That status can only be used with the orgs {}.".format(
                        main.englishFromList(f"'{x}'" for x in possibleMgs),
                    )

        else:
            if megaGroup not in megaGroups:
                msg = f"Unknown Status metadata '{canonStatus}'. Check the docs for valid Status values."
            else:
                msg = f"Status '{status}' can't be used with the org '{megaGroup}'. Check the docs for valid Status values."
        m.die(msg)
        return canonStatus

    # Otherwise, they provided a bare status.
    # See if their group is compatible with any of the prefixed statuses matching the bare status.
    assert "" not in possibleMgs  # if it was here, the literal "in" test would have caught this bare status
    for mg in possibleMgs:
        if group in megaGroups[mg]:
            canonStatus = mg + "/" + status

            if mg == "w3c":
                validateW3Cstatus(group, canonStatus, rawStatus)

            return canonStatus

    # Group isn't in any compatible org, so suggest prefixing.
    if possibleMgs:
        msg = "You used Status: {}, but that's limited to the {} org{}".format(
            rawStatus,
            main.englishFromList(f"'{mg}'" for mg in possibleMgs),
            "s" if len(possibleMgs) > 1 else "",
        )
        if group:
            msg += ", and your group '{}' isn't recognized as being in {}.".format(
                group,
                "any of those orgs" if len(possibleMgs) > 1 else "that org",
            )
            msg += " If this is wrong, please file a Bikeshed issue to categorize your group properly, and/or try:\n"
            msg += "\n".join(f"Status: {mg}/{status}" for mg in possibleMgs)
        else:
            msg += ", and you don't have a Group metadata. Please declare your Group, or check the docs for statuses that can be used by anyone."
    else:
        msg = f"Unknown Status metadata '{canonStatus}'. Check the docs for valid Status values."
    m.die(msg)
    return canonStatus


@t.overload
def splitStatus(st: None) -> tuple[None, None]: ...


@t.overload
def splitStatus(st: str) -> tuple[str | None, str]: ...


def splitStatus(st: str | None) -> tuple[str | None, str | None]:
    if st is None:
        return None, None

    parts = st.partition("/")
    if parts[2] == "":
        return None, parts[0]

    return parts[0], parts[2]


def looselyMatch(s1: str | None, s2: str | None) -> bool:
    # Loosely matches two statuses:
    # they must have the same status name,
    # and either the same or missing group name
    group1, status1 = splitStatus(s1)
    group2, status2 = splitStatus(s2)
    if status1 != status2:
        return False
    if group1 == group2 or group1 is None or group2 is None:
        return True
    return False

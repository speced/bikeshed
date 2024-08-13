from __future__ import annotations

from .. import t, messages as m

if t.TYPE_CHECKING:
    from . import GroupStatusManager, StandardsBody, Group, Status



@t.overload
def canonicalizeStatus(manager: GroupStatusManager, rawStatus: None, group: str | None) -> None: ...


@t.overload
def canonicalizeStatus(manager: GroupStatusManager, rawStatus: str, group: str | None) -> str: ...


def canonicalizeStatusShortname(manager: GroupStatusManager, rawStatus: str | None, groupName: str | None) -> Status | None:
    # Takes a "rawStatus" (something written in the Status metadata) and optionally a Group metadata value,
    # and, if possible, converts that into a Status value.
    if rawStatus is None:
        return None

    sbName: str|None
    statusName: str
    if "/" in rawStatus:
        sbName, _, statusName = rawStatus.partition("/")
        sbName = sbName.lower()
    else:
        sbName = None
        statusName = rawStatus
    statusName = statusName.upper()

    status = manager.getStatus(sbName, statusName)

    if groupName is not None:
        group = manager.getGroup(groupName.lower())
    else:
        group = None

    if group and status:
        # If using a standards-body status, group must match.
        # (Any group can use a generic status.)
        if status.sb is not None and status.sb != group.sb:
            possibleStatusNames = config.englishFromList(group.sb.statuses.keys())
            m.die(f"Your Group metadata is in the standards-body '{group.sb.name}', but your Status metadata is in the standards-body '{status.sb.name}'. Allowed Status values for '{group.sb.name}' are: {possibleStatusNames}")
        if group.sb.name == "w3c":
            # Apply the special w3c rules
            validateW3CStatus(group, status)

    if status:
        return status

    # Try and figure out why we failed to find the status

    # Does that status just not exist at all?
    possibleStatuses = manager.getStatuses(statusName)
    if not possibleStatuses:
        m.die(f"Unknown Status metadata '{rawStatus}'. Check the docs for valid Status values.")
        return None

    possibleSbNames = config.englishFromList(x.sb.name if x.sb else "(None)" for x in possibleStatuses)
    
    # Okay, it exists, but didn't come up. So you gave the wrong standards-body. Does that standards-body exist?
    if sbName is not None and manager.getStandardsBody(sbName) is None:
        m.die(f"Unknown standards-body prefix '{sbName}' on your Status metadata '{rawStatus}'. Recognized standards-body prefixes for that Status are: {possibleSbNames}")
        return None

    # Standards-body exists, but your status isn't in it.


    # If they specified a standards-org prefix and it wasn't found,
    # that's an error.
    if megaGroup:
        # Was the error because the megagroup doesn't exist?
        if possibleMgs:
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
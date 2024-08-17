from __future__ import annotations

from .. import config, t
from .. import messages as m

if t.TYPE_CHECKING:
    from . import DoctypeManager, Group, GroupW3C, Org, Status, StatusW3C


def canonicalizeOrgStatusGroup(
    manager: DoctypeManager,
    rawOrg: str | None,
    rawStatus: str | None,
    rawGroup: str | None,
) -> tuple[Org | None, Status | None, Group | None]:
    # Takes raw Org/Status/Group names (something written in the Org/Status/Group metadata),
    # and, if possible, converts them into Org/Status/Group objects.

    # First, canonicalize the status and group casings, and separate them from
    # any inline org specifiers.
    # Then, figure out what the actual org name is.
    orgFromStatus, statusName = splitOrg(rawStatus)
    statusName = statusName.upper() if statusName is not None else None

    orgFromGroup, groupName = splitOrg(rawGroup)
    groupName = groupName.lower() if groupName is not None else None

    orgName = reconcileOrgs(rawOrg, orgFromStatus, orgFromGroup)

    if orgName is not None and rawOrg is None:
        orgInferredFrom = "Org (inferred from "
        if orgFromStatus is not None:
            orgInferredFrom += f"Status '{rawStatus}')"
        else:
            orgInferredFrom += f"Group '{rawGroup}')"
    else:
        orgInferredFrom = "Org"

    # Actually fetch the Org/Status/Group objects
    if orgName is not None:
        org = manager.getOrg(orgName)
        if org is None:
            m.die(f"Unknown {orgInferredFrom} '{orgName}'. See docs for recognized Org values.")
    else:
        org = None

    if groupName is not None:
        group = manager.getGroup(orgName, groupName)
        if group is None:
            if orgName is None:
                groups = manager.getGroups(orgName, groupName)
                if len(groups) > 1:
                    orgNamesForGroup = config.englishFromList((x.org.name for x in groups), "and")
                    m.die(
                        f"Your Group '{groupName}' exists under several Orgs ({orgNamesForGroup}). Specify which org you want in an Org metadata.",
                    )
                else:
                    m.die(f"Unknown Group '{groupName}'. See docs for recognized Group values.")
            else:
                groups = manager.getGroups(None, groupName)
                if len(groups) > 0:
                    orgNamesForGroup = config.englishFromList((x.org.name for x in groups), "and")
                    m.die(
                        f"Your Group '{groupName}' doesn't exist under the {orgInferredFrom} '{orgName}', but does exist under {orgNamesForGroup}. Specify the correct Org (or the correct Group).",
                    )
                else:
                    m.die(f"Unknown Group '{rawGroup}'. See docs for recognized Group values.")
    else:
        group = None

    # If Org wasn't specified anywhere, default it from Group if possible
    if org is None and group is not None:
        org = group.org

    if statusName is not None:
        if orgFromStatus is not None:
            # If status explicitly specified an org, use that
            status = manager.getStatus(orgFromStatus, statusName)
        elif org:
            # Otherwise, if we found an org, look for it there,
            # but fall back to looking for it in the generic statuses
            status = manager.getStatus(org.name, statusName, allowGeneric=True)
        else:
            # Otherwise, just look in the generic statuses;
            # the error stuff later will catch it if that doesn't work.
            status = manager.getStatus(None, statusName)
    else:
        # Just quick exit on this case, nothing we can do.
        return org, None, group

    # See if your org-specific Status matches your Org
    if org and status and status.org is not None and status.org != org:
        m.die(f"Your {orgInferredFrom} is '{org.name}', but your Status is only usable in the '{status.org.name}' Org.")

    if group and status and status.org is not None and status.org != group.org:
        # If using an org-specific Status, Group must match.
        # (Any group can use a generic status.)
        possibleStatusNames = config.englishFromList(f"'{x}'" for x in group.org.statuses)
        m.die(
            f"Your Group is in the '{group.org.name}' Org, but your Status is only usable in the '{status.org.name}' Org. Allowed Status values for '{group.org.name}' are: {possibleStatusNames}",
        )

    if group and status and group.org.name == "w3c":
        # Apply the special w3c rules
        validateW3CStatus(group, status)

    # Reconciliation done, return everything if Status exists.
    if status:
        return org, status, group

    # Otherwise, try and figure out why we failed to find the status

    possibleStatuses = manager.getStatuses(statusName)
    if len(possibleStatuses) == 0:
        m.die(f"Unknown Status metadata '{rawStatus}'. Check the docs for valid Status values.")
        return org, status, group
    elif len(possibleStatuses) == 1:
        possibleStatus = possibleStatuses[0]
        if possibleStatus.org is None:
            m.die(
                f"Your Status '{statusName}' is a generic status, but you explicitly specified '{rawStatus}'. Remove the org prefix from your Status.",
            )
        else:
            m.die(
                f"Your Status '{statusName}' only exists in the '{possibleStatus.org.name}' Org, but you specified the {orgInferredFrom} '{orgName}'.",
            )
    else:
        statusNames = config.englishFromList((x.org.name for x in possibleStatuses if x.org), "and")
        includesDefaultStatus = any(x.org is None for x in possibleStatuses)
        if includesDefaultStatus:
            msg = f"Your Status '{statusName}' only exists in Org(s) {statusNames}, or is a generic status."
        else:
            msg = f"Your Status '{statusName}' only exists in the Orgs {statusNames}."
        if orgName:
            if org:
                msg += f" Your specified {orgInferredFrom} is '{orgName}'."
            else:
                msg += f" Your specified {orgInferredFrom} is an unknown value '{orgName}'."
        else:
            msg += " Declare one of those Orgs in your Org metadata."
        m.die(msg)

    return (org, status, group)


def splitOrg(st: str | None) -> tuple[str | None, str | None]:
    if st is None:
        return None, None

    if "/" in st:
        parts = st.partition("/")
        return parts[0].strip().lower(), parts[2].strip()
    else:
        return None, st.strip()


def reconcileOrgs(fromRaw: str | None, fromStatus: str | None, fromGroup: str | None) -> str | None:
    # Since there are three potential sources of "org" name,
    # figure out what the name actually is,
    # and complain if they disagree.
    fromRaw = fromRaw.lower() if fromRaw else None
    fromStatus = fromStatus.lower() if fromStatus else None
    fromGroup = fromGroup.lower() if fromGroup else None

    orgName: str | None = fromRaw

    if fromStatus is not None:
        if orgName is None:
            orgName = fromStatus
        elif orgName == fromStatus:
            pass
        else:
            m.die(
                f"Your Org metadata specifies '{fromRaw}', but your Status metadata states an org of '{fromStatus}'. These must agree - either fix them or remove one of them.",
            )

    if fromGroup is not None:
        if orgName is None:
            orgName = fromGroup
        elif orgName == fromGroup:
            pass
        else:
            m.die(
                f"Your Org metadata specifies '{fromRaw}', but your Group metadata states an org of '{fromGroup}'. These must agree - either fix them or remove one of them.",
            )

    return orgName


def validateW3CStatus(group: Group, status: Status) -> None:
    if t.TYPE_CHECKING:
        assert isinstance(group, GroupW3C)
        assert isinstance(status, StatusW3C)
    if status.org is None and status.name == "DREAM":
        m.warn("You used Status:DREAM for a W3C document. Consider Status:UD instead.")

    if status.name in ("IG-NOTE", "WG-NOTE"):
        m.die(
            f"Under Process2021, {status.name} is no longer a valid status. Use NOTE (or one of its variants NOTE-ED, NOTE-FPWD, NOTE-WD) instead.",
        )

    if group.type is not None and group.type not in status.groupTypes:
        if group.type == "ig":
            longTypeName = "W3C Interest Groups"
        elif group.type == "tag":
            longTypeName = "the W3C TAG"
        elif group.type == "cg":
            longTypeName = "W3C Community/Business Groups"
        else:
            longTypeName = "W3C Working Groups"
        allowedStatuses = [x for x in t.cast("list[StatusW3C]", group.org.statuses.values()) if group.type in x.groupTypes]
        if allowedStatuses:
            m.warn(
                f"You used Status:{status.name}, but {longTypeName} are limited to these statuses: {allowedStatuses}.",
            )
        else:
            m.die(f"PROGRAMMING ERROR: Group '{group.fullName()}' has type '{group.type}', but that isn't present in any of org's Statuses.")
        return

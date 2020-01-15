# -*- coding: utf-8 -*-


from .main import englishFromList
from ..messages import *

shortToLongStatus = {
    "DREAM": "A Collection of Interesting Ideas",
    "LS": "Living Standard",
    "LS-COMMIT": "Commit Snapshot",
    "LS-BRANCH": "Branch Snapshot",
    "LD": "Living Document",
    "DRAFT-FINDING": "Draft Finding",
    "FINDING": "Finding",
    "whatwg/RD": "Review Draft",
    "w3c/ED": "Editor's Draft",
    "w3c/WD": "W3C Working Draft",
    "w3c/FPWD": "W3C First Public Working Draft",
    "w3c/LCWD": "W3C Last Call Working Draft",
    "w3c/CR": "W3C Candidate Recommendation",
    "w3c/PR": "W3C Proposed Recommendation",
    "w3c/REC": "W3C Recommendation",
    "w3c/PER": "W3C Proposed Edited Recommendation",
    "w3c/WG-NOTE": "W3C Working Group Note",
    "w3c/IG-NOTE": "W3C Interest Group Note",
    "w3c/NOTE": "W3C Note",
    "w3c/MO": "W3C Member-only Draft",
    "w3c/UD": "Unofficial Proposal Draft",
    "w3c/CG-DRAFT": "Draft Community Group Report",
    "w3c/CG-FINAL": "Final Community Group Report",
    "tc39/STAGE0": "Stage 0: Strawman",
    "tc39/STAGE1": "Stage 1: Proposal",
    "tc39/STAGE2": "Stage 2: Draft",
    "tc39/STAGE3": "Stage 3: Candidate",
    "tc39/STAGE4": "Stage 4: Finished",
    "iso/I": "Issue",
    "iso/DR": "Defect Report",
    "iso/D": "Draft Proposal",
    "iso/P": "Published Proposal",
    "iso/MEET": "Meeting Announcements",
    "iso/RESP": "Records of Response",
    "iso/MIN": "Minutes",
    "iso/ER": "Editor's Report",
    "iso/SD": "Standing Document",
    "iso/PWI": "Preliminary Work Item",
    "iso/NP": "New Proposal",
    "iso/NWIP": "New Work Item Proposal",
    "iso/WD": "Working Draft",
    "iso/CD": "Committee Draft",
    "iso/FCD": "Final Committee Draft",
    "iso/DIS": "Draft International Standard",
    "iso/FDIS": "Final Draft International Standard",
    "iso/PRF": "Proof of a new International Standard",
    "iso/IS": "International Standard",
    "iso/TR": "Technical Report",
    "iso/DTR": "Draft Technical Report",
    "iso/TS": "Technical Specification",
    "iso/DTS": "Draft Technical Specification",
    "iso/PAS": "Publicly Available Specification",
    "iso/TTA": "Technology Trends Assessment",
    "iso/IWA": "International Workshop Agreement",
    "iso/COR": "Technical Corrigendum",
    "iso/GUIDE": "Guidance to Technical Committees",
    "iso/NP-AMD": "New Proposal Amendment",
    "iso/AWI-AMD": "Approved new Work Item Amendment",
    "iso/WD-AMD": "Working Draft Amendment",
    "iso/CD-AMD": "Committee Draft Amendment",
    "iso/PD-AMD": "Proposed Draft Amendment",
    "iso/FPD-AMD": "Final Proposed Draft Amendment",
    "iso/D-AMD": "Draft Amendment",
    "iso/FD-AMD": "Final Draft Amendment",
    "iso/PRF-AMD": "Proof Amendment",
    "iso/AMD": "Amendment",
    "fido/ED": "Editor's Draft",
    "fido/WD": "Working Draft",
    "fido/RD": "Review Draft",
    "fido/ID": "Implementation Draft",
    "fido/PS": "Proposed Standard",
    "fido/FD": "Final Document",
    "khronos/ED": "Editor's Draft"
}
snapshotStatuses = ["w3c/WD", "w3c/FPWD", "w3c/LCWD", "w3c/CR", "w3c/PR", "w3c/REC", "w3c/PER", "w3c/WG-NOTE", "w3c/IG-NOTE", "w3c/NOTE", "w3c/MO"]
datedStatuses = ["w3c/WD", "w3c/FPWD", "w3c/LCWD", "w3c/CR", "w3c/PR", "w3c/REC", "w3c/PER", "w3c/WG-NOTE", "w3c/IG-NOTE", "w3c/NOTE", "w3c/MO", "whatwg/RD"]
unlevelledStatuses = ["LS", "LD", "DREAM", "w3c/UD", "LS-COMMIT", "LS-BRANCH", "FINDING", "DRAFT-FINDING", "whatwg/RD"]
deadlineStatuses = ["w3c/LCWD", "w3c/PR"]
noEDStatuses = ["LS", "LS-COMMIT", "LS-BRANCH", "LD", "FINDING", "DRAFT-FINDING", "DREAM", "iso/NP", "whatwg/RD"]
# WG statuses can only be used if the group is a W3C working group or interest
# group, as opposed to a community or business group.
w3cWgStatuses = ["w3c/ED", "w3c/WD", "w3c/FPWD", "w3c/LCWD", "w3c/CR", "w3c/PR", "w3c/REC", "w3c/PER"]

megaGroups = {
    "w3c": frozenset(["act-framework", "audiowg", "csswg", "dap", "fxtf", "fxtf-csswg", "geolocation", "houdini", "html", "i18n", "immersivewebcg", "immersivewebwg", "mediacapture", "mediawg", "ping", "privacycg", "processcg", "ricg", "sacg", "secondscreenwg", "serviceworkers", "svg", "texttracks", "uievents", "wasm", "web-bluetooth-cg", "webapps", "webappsec", "webauthn", "webml", "web-payments", "webperf", "webplatform", "webrtc", "webspecs", "webvr", "wicg"]),
    "whatwg": frozenset(["whatwg"]),
    "tc39": frozenset(["tc39"]),
    "iso": frozenset(["wg14", "wg21"]),
    "fido": frozenset(["fido"]),
    "priv-sec": frozenset(["audiowg", "csswg", "dap", "fxtf", "fxtf-csswg", "geolocation", "houdini", "html", "mediacapture", "mediawg", "ricg", "svg", "texttracks", "uievents", "web-bluetooth-cg", "webappsec", "webplatform", "webspecs", "whatwg"]),
    "khronos": frozenset(["webgl"])
}
# Community and business groups within the W3C:
w3cCgs = frozenset(["immersivewebcg", "privacycg", "processcg", "ricg", "sacg", "web-bluetooth-cg", "wicg"])
assert w3cCgs.issubset(megaGroups["w3c"])


def canonicalizeStatus(rawStatus, group):
    if rawStatus is None:
        return None

    def megaGroupsForStatus(status):
        # Returns a list of megagroups that recognize the given status
        megaGroups = []
        for key in shortToLongStatus.keys():
            mg,_,s = key.partition("/")
            if s == status:
                megaGroups.append(mg)
        return megaGroups

    # Canonicalize the rawStatus that was passed in, into a known form.
    # Might be foo/BAR, or just BAR.
    megaGroup,_,status = rawStatus.partition("/")
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
                msg = "Status metadata specified an unrecognized '{0}' organization.".format(megaGroup)
            else:
                msg = "Status '{0}' can't be used with the org '{1}'.".format(status, megaGroup)
            if "" in possibleMgs:
                if len(possibleMgs) == 1:
                    msg += " That status must be used without an org at all, like `Status: {0}`".format(status)
                else:
                    msg += " That status can only be used with the org{0} {1}, or without an org at all.".format(
                        "s" if len(possibleMgs)>1 else "",
                        englishFromList("'{0}'".format(x) for x in possibleMgs if x != ""))
            else:
                if len(possibleMgs) == 1:
                    msg += " That status can only be used with the org '{0}', like `Status: {0}/{1}`".format(possibleMgs[0], status)
                else:
                    msg += " That status can only be used with the orgs {0}.".format(englishFromList("'{0}'".format(x) for x in possibleMgs))

        else:
            if megaGroup not in megaGroups:
                msg = "Unknown Status metadata '{0}'. Check the docs for valid Status values.".format(canonStatus)
            else:
                msg = "Status '{0}' can't be used with the org '{1}'. Check the docs for valid Status values.".format(status, megaGroup)
        die("{0}", msg)
        return canonStatus

    # Otherwise, they provided a bare status.
    # See if their group is compatible with any of the prefixed statuses matching the bare status.
    assert "" not in possibleMgs # if it was here, the literal "in" test would have caught this bare status
    for mg in possibleMgs:
        if group in megaGroups[mg]:
            canonStatus = mg + "/" + status

            if canonStatus in w3cWgStatuses and group in w3cCgs:
                msg = "You used Status: {0}, but that's limited to W3C working and interest groups.".format(rawStatus)
                msg += " Your group '{0}' is a community or business group. Consider CG-DRAFT or CG-FINAL instead.".format(group)
                warn("{0}", msg)

            return canonStatus

    # Group isn't in any compatible org, so suggest prefixing.
    if possibleMgs:
        msg = "You used Status: {0}, but that's limited to the {1} org{2}".format(
            rawStatus,
            englishFromList("'{0}'".format(mg) for mg in possibleMgs),
            "s" if len(possibleMgs)>1 else "")
        if group:
            msg += ", and your group '{0}' isn't recognized as being in {1}.".format(group, "any of those orgs" if len(possibleMgs)>1 else "that org")
            msg += " If this is wrong, please file a Bikeshed issue to categorize your group properly, and/or try:\n"
            msg += "\n".join("Status: {0}/{1}".format(mg, status) for mg in possibleMgs)
        else:
            msg += ", and you don't have a Group metadata. Please declare your Group, or check the docs for statuses that can be used by anyone."
    else:
        msg = "Unknown Status metadata '{0}'. Check the docs for valid Status values.".format(canonStatus)
    die("{0}", msg)
    return canonStatus

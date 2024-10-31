from __future__ import annotations

import dataclasses

import kdl

from .. import t
from . import utils


@dataclasses.dataclass
class Doctype:
    org: Org
    group: Group
    status: Status

    def __str__(self) -> str:
        return f"Doctype<org={self.org.name}, group={self.group.fullName()}, status={self.status.fullName()}>"


@dataclasses.dataclass
class DoctypeManager:
    genericStatuses: dict[str, Status] = dataclasses.field(default_factory=dict)
    orgs: dict[str, Org] = dataclasses.field(default_factory=dict)

    @staticmethod
    def fromKdlStr(data: str) -> DoctypeManager:
        self = DoctypeManager()
        kdlDoc = kdl.parse(data)

        for node in kdlDoc.getAll("status"):
            status = Status.fromKdlNode(node)
            self.genericStatuses[status.name] = status

        for node in kdlDoc.getAll("org"):
            org = Org.fromKdlNode(node)
            self.orgs[org.name] = org

        return self

    def getStatuses(self, name: str) -> list[Status]:
        statuses = []
        if name in self.genericStatuses:
            statuses.append(self.genericStatuses[name])
        for org in self.orgs.values():
            if name in org.statuses:
                statuses.append(org.statuses[name])
        return statuses

    def getStatus(self, orgName: str | None, statusName: str, allowGeneric: bool = False) -> Status | None:
        # Note that a None orgName does *not* indicate we don't care,
        # it's specifically statuses *not* restricted to an org.
        if orgName is None:
            return self.genericStatuses.get(statusName)
        elif orgName in self.orgs:
            statusInOrg = self.orgs[orgName].statuses.get(statusName)
            if statusInOrg:
                return statusInOrg
            elif allowGeneric:
                return self.genericStatuses.get(statusName)
            else:
                return None
        else:
            return None

    def getGroups(self, orgName: str | None, groupName: str) -> list[Group]:
        # Unlike Status, if org is None we'll just grab whatever group matches.
        groups = []
        for org in self.orgs.values():
            if orgName is not None and org.name != orgName:
                continue
            if groupName in org.groups:
                groups.append(org.groups[groupName])
        return groups

    def getGroup(self, orgName: str | None, groupName: str) -> Group | None:
        # If Org is None, and there are multiple groups with that name, fail to find.
        groups = self.getGroups(orgName, groupName)
        if len(groups) == 1:
            return groups[0]
        else:
            return None

    def getOrg(self, orgName: str) -> Org | None:
        return self.orgs.get(orgName)

    def getDoctype(self, orgName: str | None, groupName: str | None, statusName: str | None) -> Doctype:
        org, group, status = utils.canonicalize(self, orgName, groupName, statusName)
        return Doctype(org if org else NIL_ORG, group if group else NIL_GROUP, status if status else NIL_STATUS)


@dataclasses.dataclass
class Org:
    name: str
    groups: dict[str, Group] = dataclasses.field(default_factory=dict)
    statuses: dict[str, Status] = dataclasses.field(default_factory=dict)

    @staticmethod
    def fromKdlNode(node: kdl.Node) -> Org:
        name = t.cast(str, node.args[0]).upper()
        self = Org(name)
        for child in node.getAll("group"):
            g = Group.fromKdlNode(child, org=self)
            self.groups[g.name] = g
        for child in node.getAll("status"):
            s = Status.fromKdlNode(child, org=self)
            self.statuses[s.name] = s
        return self

    def __bool__(self) -> bool:
        return self != NIL_ORG


NIL_ORG = Org("(not provided)")


@dataclasses.dataclass
class Group:
    name: str
    privSec: bool
    org: Org
    requires: list[str] = dataclasses.field(default_factory=list)
    type: str | None = None

    def fullName(self) -> str:
        if self.org:
            return self.org.name + "/" + self.name
        else:
            return self.name

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org) -> Group:
        name = t.cast(str, node.args[0]).upper()
        privSec = t.cast(bool, node.props.get("priv-sec", False))
        if "type" in node.props:
            groupType = str(node.props.get("type")).lower()
        else:
            groupType = None
        self = Group(name, privSec, org, type=groupType)
        for n in node.getAll("requires"):
            self.requires.extend(t.cast("list[str]", n.getArgs((..., str))))
        return self

    def __bool__(self) -> bool:
        return self != NIL_GROUP


NIL_GROUP = Group("(not provided)", privSec=False, org=NIL_ORG)


@dataclasses.dataclass
class Status:
    name: str
    longName: str
    org: Org
    requires: list[str] = dataclasses.field(default_factory=list)
    groupTypes: list[str] = dataclasses.field(default_factory=list)

    def fullName(self) -> str:
        if self.org:
            return self.org.name + "/" + self.name
        else:
            return self.name

    def looselyMatch(self, rawStatus: str) -> bool:
        orgName, statusName = utils.splitOrg(rawStatus)
        if statusName and self.name.upper() != statusName.upper():
            return False
        if orgName and self.org.name != orgName.upper():  # noqa: SIM103
            return False
        return True

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org | None = None) -> Status:
        if org is None:
            org = NIL_ORG
        name = t.cast(str, node.args[0]).upper()
        longName = t.cast(str, node.args[1])
        self = Status(name, longName, org)
        for n in node.getAll("requires"):
            self.requires.extend(t.cast("list[str]", n.getArgs((..., str))))
        for n in node.getAll("group-types"):
            self.groupTypes.extend(str(x).lower() for x in n.getArgs((..., str)))
        return self

    def __bool__(self) -> bool:
        return self != NIL_STATUS


NIL_STATUS = Status("(not provided)", "", org=NIL_ORG)

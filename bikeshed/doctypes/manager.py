from __future__ import annotations

import dataclasses

import kdl

from .. import t
from . import utils


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


@dataclasses.dataclass
class Org:
    name: str
    groups: dict[str, Group] = dataclasses.field(default_factory=dict)
    statuses: dict[str, Status] = dataclasses.field(default_factory=dict)

    @staticmethod
    def fromKdlNode(node: kdl.Node) -> Org:
        name = t.cast(str, node.args[0])
        self = Org(name)
        for child in node.getAll("group"):
            g = Group.fromKdlNode(child, org=self)
            self.groups[g.name] = g
        for child in node.getAll("status"):
            s = Status.fromKdlNode(child, org=self)
            self.statuses[s.name] = s
        return self


@dataclasses.dataclass
class Group:
    name: str
    privSec: bool
    org: Org
    requires: list[str] = dataclasses.field(default_factory=list)

    def fullName(self) -> str:
        return self.org.name + "/" + self.name

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org) -> Group:
        if org.name == "w3c":
            return GroupW3C.fromKdlNode(node, org)
        name = t.cast(str, node.args[0])
        privSec = t.cast(bool, node.props.get("priv-sec", False))
        requiresNode = node.get("requires")
        self = Group(name, privSec, org)
        if requiresNode:
            self.requires = t.cast("list[str]", list(requiresNode.getArgs((..., str))))
        return self


@dataclasses.dataclass
class GroupW3C(Group):
    type: str | None = None

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org) -> GroupW3C:
        name = t.cast(str, node.args[0])
        privSec = t.cast(bool, node.props.get("priv-sec", False))
        groupType = t.cast("str|None", node.props.get("type"))
        return GroupW3C(name, privSec, org, [], groupType)


@dataclasses.dataclass
class Status:
    name: str
    longName: str
    org: Org | None = None
    requires: list[str] = dataclasses.field(default_factory=list)

    def fullName(self) -> str:
        if self.org is None:
            return self.name
        else:
            return self.org.name + "/" + self.name

    def orgName(self) -> str | None:
        if self.org:
            return self.org.name
        else:
            return None

    def looselyMatch(self, rawStatus: str) -> bool:
        orgName, statusName = utils.splitOrg(rawStatus)
        if statusName and self.name.upper() != statusName.upper():
            return False
        if orgName and self.org and self.orgName() != orgName.lower():
            return False
        return True

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org | None = None) -> Status:
        if org and org.name == "w3c":
            return StatusW3C.fromKdlNode(node, org)
        name = t.cast(str, node.args[0])
        longName = t.cast(str, node.args[1])
        self = Status(name, longName, org)
        requiresNode = node.get("requires")
        if requiresNode:
            self.requires = t.cast("list[str]", list(requiresNode.getArgs((..., str))))
        return self


@dataclasses.dataclass
class StatusW3C(Status):
    groupTypes: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def fromKdlNode(node: kdl.Node, org: Org | None = None) -> StatusW3C:
        name = t.cast(str, node.args[0])
        longName = t.cast(str, node.args[1])
        self = StatusW3C(name, longName, org)
        requiresNode = node.get("requires")
        if requiresNode:
            self.requires = t.cast("list[str]", list(requiresNode.getArgs((..., str))))
        groupTypesNode = node.get("requires")
        if groupTypesNode:
            self.requires = t.cast("list[str]", list(groupTypesNode.getArgs((..., str))))
        if name == "ED":
            print(self)
        return self

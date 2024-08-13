from __future__ import annotations

import dataclasses

import kdl

from .. import messages as m
from .. import t
from . import utils


@dataclasses.dataclass
class GroupStatusManager:
    genericStatuses: dict[str, Status] = dataclasses.field(default_factory=dict)
    standardsBodies: dict[str, StandardsBody] = dataclasses.field(default_factory=dict)

    @staticmethod
    def fromKdlStr(data: str) -> GroupStatusManager:
        self = GroupStatusManager()
        kdlDoc = kdl.parse(data)

        for node in kdlDoc.getAll("status"):
            status = Status.fromKdlNode(node)
            self.genericStatuses[status.shortName] = status

        for node in kdlDoc.getAll("standards-body"):
            sb = StandardsBody.fromKdlNode(node)
            self.standardsBodies[sb.name] = sb

        return self

    def getStatuses(name: str) -> list[Status]:
        statuses = []
        if name in self.genericStatuses:
            statuses.append(self.genericStatuses[name])
        for sb in self.standardsBodies:
            if name in sb.statuses:
                statuses.append(sb.statuses[name])
        return statuses

    def getStatus(sbName: str|None, statusName: str) -> Status|None:
        # Note that a None sbName does *not* indicate we don't care,
        # it's specifically statuses *not* restricted to a standards body.
        if sbName is None:
            return self.genericStatuses.get(statusName)
        elif sbName in self.standardsBodies:
            return self.standardsBodies[sbName].statuses.get(statusName)
        else:
            return None

    def getGroup(groupName: str) -> Group|None:
        for sb in self.standardsBodies:
            if groupName in sb.groups:
                return sb.groups[groupName]
        return None

    def getStandardsBody(sbName: str) -> StandardsBody|None:
        return self.standardsBodies.get(sbName)




@dataclasses.dataclass
class StandardsBody:
    name: str
    groups: dict[str, Group] = dataclasses.field(default_factory=dict)
    statuses: dict[str, Status] = dataclasses.field(default_factory=dict)

    @staticmethod
    def fromKdlNode(node: kdl.Node) -> StandardsBody:
        name = t.cast(str, node.args[0])
        self = StandardsBody(name)
        for child in node.getAll("group"):
            g = Group.fromKdlNode(child, sb=self)
            self.groups[g.name] = g
        for child in node.getAll("status"):
            s = Status.fromKdlNode(child, sb=self)
            self.statuses[s.shortName] = s
        return self


@dataclasses.dataclass
class Group:
    name: str
    privSec: bool
    sb: StandardsBody | None = None

    @staticmethod
    def fromKdlNode(node: kdl.Node, sb: StandardsBody | None = None) -> Group:
        if sb.name == "w3c":
            return GroupW3C.fromKdlNode(node, sb)
        name = t.cast(str, node.args[0])
        privSec = node.get("priv-sec") is not None
        return Group(name, privSec, sb)


@dataclasses.dataclass
class GroupW3C(Group):
    type: str | None = None

    @staticmethod
    def fromKdlNode(node: kdl.Node, sb: StandardsBody | None = None) -> GroupW3C:
        name = t.cast(str, node.args[0])
        privSec = node.get("priv-sec") is not None
        groupType = t.cast("str|None", node.props["type"])
        return GroupW3C(name, privSec, sb, groupType)


@dataclasses.dataclass
class Status:
    shortName: str
    longName: str
    sb: StandardsBody | None = None
    requires: list[str] = dataclasses.field(default_factory=list)

    def fullShortname(self) -> str:
        if self.sb.name is None:
            return self.shortName
        else:
            return self.sb.name + "/" + self.shortName

    @staticmethod
    def fromKdlNode(node: kdl.Node, sb: StandardsBody | None = None) -> Status:
        if sb.name == "w3c":
            return StatusW3C.fromKdlNode(node, sb)
        shortName = t.cast(str, node.args[0])
        longName = t.cast(str, node.args[1])
        self = Status(shortName, longName, sb)
        requiresNode = node.get("requires")
        if requiresNode:
            self.requires = t.cast("list[str]", list(node.getArgs((..., str))))
        return self


@dataclasses.dataclass
class StatusW3C(Status):
    groupTypes: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def fromKdlNode(node: kdl.Node, sbName: str | None = None) -> StatusW3C:
        shortName = t.cast(str, node.args[0])
        longName = t.cast(str, node.args[1])
        self = StatusW3C(shortName, longName, sbName)
        requiresNode = node.get("requires")
        if requiresNode:
            self.requires = t.cast("list[str]", list(node.getArgs((..., str))))
        groupTypesNode = node.get("requires")
        if groupTypesNode:
            self.requires = t.cast("list[str]", list(node.getArgs((..., str))))
        return self

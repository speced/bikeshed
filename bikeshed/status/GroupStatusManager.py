from __future__ import annotations

import dataclasses

import kdl

from .. import messages as m
from .. import t


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
            g = Group.fromKdlNode(child, sbName=self.name)
            self.groups[g.name] = g
        for child in node.getAll("status"):
            s = Status.fromKdlNode(child, sbName=self.name)
            self.statuses[s.shortName] = s
        return self


@dataclasses.dataclass
class Group:
    name: str
    privSec: bool
    sbName: str | None = None

    @staticmethod
    def fromKdlNode(node: kdl.Node, sbName: str | None = None) -> Group:
        if sbName == "w3c":
            return GroupW3C.fromKdlNode(node, sbName)
        name = t.cast(str, node.args[0])
        privSec = node.get("priv-sec") is not None
        return Group(name, privSec, sbName)


@dataclasses.dataclass
class GroupW3C(Group):
    type: str | None = None

    @staticmethod
    def fromKdlNode(node: kdl.Node, sbName: str | None = None) -> GroupW3C:
        name = t.cast(str, node.args[0])
        privSec = node.get("priv-sec") is not None
        groupType = t.cast("str|None", node.props["type"])
        return GroupW3C(name, privSec, sbName, groupType)


@dataclasses.dataclass
class Status:
    shortName: str
    longName: str
    sbName: str | None = None
    requires: list[str] = dataclasses.field(default_factory=list)

    def fullShortname(self) -> str:
        if self.sbName is None:
            return self.shortName
        else:
            return self.sbName + "/" + self.shortName

    @staticmethod
    def fromKdlNode(node: kdl.Node, sbName: str | None = None) -> Status:
        if sbName == "w3c":
            return StatusW3C.fromKdlNode(node, sbName)
        shortName = t.cast(str, node.args[0])
        longName = t.cast(str, node.args[1])
        self = Status(shortName, longName, sbName)
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

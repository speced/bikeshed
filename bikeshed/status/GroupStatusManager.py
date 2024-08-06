from __future__ import annotations

import dataclasses
import kdl

from .. import t, messages as m

@dataclasses.dataclass
class GroupStatusManager:
	genericStatuses: dict[str, Status] = dataclasses.field(default_factory=dict)
	megaGroups: dict[str, MegaGroup] = dataclasses.field(default_factory=dict)

	@classmethod
	def fromKDLStr(cls, data: str) -> t.Self:
		self = cls()
		kdlDoc = kdl.parse(data)

		for node in kdlDoc.nodes:
			if node.name.lower() == "status":
				status = Status.fromKdlNode(node)
				genericStatuses[status.name] = status
			elif node.name.lower() == "megagroup":
				mg = MegaGroup.fromKDLNode(node)
				megaGroups[mg.name] = mg
			else:
				m.die(f"Unknown node type '{node.name}' in the group/status KDL file.")
				return self
		return self



@dataclasses.dataclass
class MegaGroup:
	name: str
	groups: dict[str, Group] = dataclasses.field(default_factory=dict)
	statuses: dict[str, Status] = dataclasses.field(default_factory=dict)

	@classmethod
	def fromKDLNode(cls, node: kdl.Node) -> t.Self:
		self = cls(node.args[0])
		for child in node.nodes:
			if child.name.lower() == "group":
				g = Group.fromKDLNode(child)
				self.groups[g.name] = g
			elif child.name.lower() == "status":
				s = Status.fromKDLNode(child)
				self.statuses[s.name] = s
			else:
				m.die(f"Unknown node type '{child.name}' in megagroup '{self.name}'.")
				continue
		return self


@dataclasses.dataclass
class Group:
	name: str
	privSec: bool

@dataclasses.dataclass
class GroupW3C:
	type: str

@dataclasses.dataclass
class Status:
	name: str
	longName: str
	requires: list[str] = dataclasses.field(default_factory=list)

@dataclasses.dataclass
class StatusW3C:
	groupTypes: list[str] = dataclasses.field(default_factory=list)
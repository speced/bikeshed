import enum


class UpdateMode(enum.Flag):
    NONE = 0
    MANIFEST = enum.auto()
    MANUAL = enum.auto()
    FORCE = enum.auto()
    BOTH = MANIFEST | MANUAL

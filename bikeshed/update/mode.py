import enum


class UpdateMode(enum.Flag):
    """
    Enum dictating how the update process should run.
    """

    NONE = 0

    # Try to update via manifest
    MANIFEST = enum.auto()

    # Try to update manually
    MANUAL = enum.auto()

    # Update via the specified methods even if you'd normally skip
    # (such as if they would pass a freshness check).
    FORCE = enum.auto()

    BOTH = MANIFEST | MANUAL

# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import re
from functools import total_ordering

@total_ordering
class HierarchicalNumber(object):
    def __init__(self, valString):
        if valString.strip().lower() == "none":
            self.nums = None
        else:
            self.nums = [int(x) for x in re.split(r"\D+", valString) if x != ""]
        self.originalVal = valString

    def __nonzero__(self):
        return bool(self.nums)

    def __lt__(self, other):
        # Unlevelled numbers are falsey, and greater than all numbers.
        if not self and other:
            return False
        elif self and not other:
            return True
        elif not self and not other:
            return False

        try:
            return self.nums < other.nums
        except AttributeError:
            return self.nums[0] < other

    def __eq__(self, other):
        if (not self and other) or (self and not other):
            return False
        if not self and not other:
            return True
        try:
            return self.nums == other.nums
        except AttributeError:
            return self.nums[0] == other

    def __str__(self):
        return self.originalVal

    def __json__(self):
        return self.originalVal

    def __repr__(self):
        return "HierarchicalNumber(" + repr(self.originalVal) + ")"

    def __hash__(self):
        return hash(self.originalVal)
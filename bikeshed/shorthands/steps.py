class NextLiteral:
    def __init__(self, regex):
        self.regex = regex


class NextBody:
    def __init__(self, regex):
        self.regex = regex


class Success:
    def __init__(self, nodes, skips=None):
        self.skips = skips or []
        self.nodes = nodes


class Failure:
    pass

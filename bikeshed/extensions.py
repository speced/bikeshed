from . import config
from . import constants
from .h import *  # noqa: F401
from .messages import *  # noqa: F401


def load(doc):
    code = config.retrieveBoilerplateFile(doc, "bs-extensions", allowLocal=constants.executeCode)
    exec(code, globals())

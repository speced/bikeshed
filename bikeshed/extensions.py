from . import config
from .h import *  # noqa: F401
from .messages import *  # noqa: F401


def load(doc):
    code = config.retrieveBoilerplateFile(doc, "bs-extensions")
    exec(code, globals())

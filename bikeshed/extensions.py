# -*- coding: utf-8 -*-


from . import config
from .htmlhelpers import *
from .messages import *


def load(doc):
    code = config.retrieveBoilerplateFile(doc, "bs-extensions")
    exec(code, globals())

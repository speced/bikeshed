# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
from . import config
from .htmlhelpers import *
from .messages import *


def load(doc):
    exec config.retrieveBoilerplateFile(doc, "bs-extensions")
    globals()['BSPrepTR'] = BSPrepTR
    globals()['BSPublishAdditionalFiles'] = BSPublishAdditionalFiles

# -*- coding: utf-8 -*-

import sys
import platform

if sys.version_info < (3,):
	print('''Bikeshed has updated to Python 3, but you are trying to run it with
Python {}. For instructions on upgrading, please check:
https://tabatkins.github.io/bikeshed/#installing'''.format(platform.python_version()))
	sys.exit(1)

if sys.version_info < (3,7):
	print('''Bikeshed now requires Python 3.7; you are on {}.
For instructions on how to set up a pyenv with 3.7, see:
https://tabatkins.github.io/bikeshed/#installing'''.format(platform.python_version()))
	sys.exit(1)

from .cli import main
from .Spec import Spec
from . import update
from . import config

# pylint: disable=wrong-import-position

from __future__ import annotations

import os
import platform
import subprocess
import sys


def verify_python_version() -> None:
    if sys.version_info < (3,):
        print(
            """Bikeshed has updated to Python 3, but you are trying to run it with
    Python {}. For instructions on upgrading, please check:
    https://speced.github.io/bikeshed/#installing""".format(
                platform.python_version(),
            ),
        )
        sys.exit(1)

    if sys.version_info < (3, 9):
        print(
            """Bikeshed now requires Python 3.9 or higher; you are on {}.
    For instructions on how to set up a pyenv with 3.9, see:
    https://speced.github.io/bikeshed/#installing""".format(
                platform.python_version(),
            ),
        )
        sys.exit(1)


verify_python_version()


def verify_requirements() -> None:
    try:
        subprocess.check_output([sys.executable, "-m", "pip", "check", "bikeshed"])  # noqa: S603
    except subprocess.CalledProcessError as e:
        print("ERROR: Broken or incomplete manual installation.")
        print(str(e.output, encoding="utf-8"))
        requirements_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
            "requirements.txt",
        )
        print(f'Run "pip3 install -r {requirements_file_path}" to complete installation')
        print("Meanwhile, attempting to run Bikeshed anyway...")


verify_requirements()

from . import (
    config,
    update,
)
from .cli import main
from .Spec import Spec

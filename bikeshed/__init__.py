def verify_python_version():
    import platform
    import sys

    if sys.version_info < (3,):
        print(
            """Bikeshed has updated to Python 3, but you are trying to run it with
    Python {}. For instructions on upgrading, please check:
    https://tabatkins.github.io/bikeshed/#installing""".format(
                platform.python_version()
            )
        )
        sys.exit(1)

    if sys.version_info < (3, 7):
        print(
            """Bikeshed now requires Python 3.7; you are on {}.
    For instructions on how to set up a pyenv with 3.7, see:
    https://tabatkins.github.io/bikeshed/#installing""".format(
                platform.python_version()
            )
        )
        sys.exit(1)


verify_python_version()


def verify_requirements():
    import os
    import sys

    import pkg_resources

    requirements_file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "requirements.txt"
    )
    if os.path.exists(requirements_file_path):
        requirements_met = True
        with open(requirements_file_path) as requirements_file:
            requirements = [
                line
                for line in requirements_file.read().split("\n")
                if (not line.strip().startswith("-"))
            ]
            for requirement in pkg_resources.parse_requirements(requirements):
                try:
                    distribution = pkg_resources.get_distribution(
                        requirement.project_name
                    )
                    if distribution not in requirement:
                        print(
                            "Package {} version {} is not supported.".format(
                                requirement.project_name, distribution.version
                            )
                        )
                        requirements_met = False
                except Exception:
                    print(f"Package {requirement.project_name} is not installed.")
                    requirements_met = False
        if not requirements_met:
            print(
                'Run "pip3 install -r {}" to complete installation'.format(
                    requirements_file_path
                )
            )
            sys.exit(1)


verify_requirements()

from . import config  # noqa: E402
from . import update  # noqa: E402
from .cli import main  # noqa: E402
from .Spec import Spec  # noqa: E402

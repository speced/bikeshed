#!/usr/bin/env python

def verify_requirements():
    import os
    import pkg_resources
    requirements_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'requirements.txt')
    if (os.path.exists(requirements_file_path)):
        requirements_met = True
        with open(requirements_file_path, 'r') as requirements_file:
            requirements = [line for line in requirements_file.read().split('\n') if (not line.strip().startswith('-'))]
            for requirement in pkg_resources.parse_requirements(requirements):
                try:
                    distribution = pkg_resources.get_distribution(requirement.project_name)
                    if (distribution not in requirement):
                        print('Package', requirement.project_name, 'version', distribution.version, 'is not supported')
                        requirements_met = False
                except Exception:
                    print('Package', requirement.project_name, 'is not installed')
                    requirements_met = False
        if (not requirements_met):
            print('Run "pip3 install -r {path}" to complete installation'.format(path=requirements_file_path))
            exit()


verify_requirements()

import bikeshed

if __name__ == "__main__":
    bikeshed.main()

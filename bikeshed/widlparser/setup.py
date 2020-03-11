"""Define PyPI package."""

import setuptools

with open("README.md", "r") as readme_file:
    long_description = readme_file.read()

setuptools.setup(
    name='widlparser',
    version='0.0.0',  # version will get replaced by git version tag - do not edit
    author='Peter Linss',
    author_email='pypi@linss.com',
    description='WebIDL Parser',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/plinss/widlparser/',

    packages=['widlparser'],
    package_data={'widlparser': ['py.typed']},

    install_requires=[
    ],
    extras_require={
        'dev': ['mypy',
                'flake8', 'flake8-import-order', 'flake8-annotations', 'flake8-type-annotations', 'flake8-docstrings',
                'pep8-naming'],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7'
)

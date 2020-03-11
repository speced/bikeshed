"""Define PyPI package."""

import setuptools

with open("README.md", "r") as readme_file:
    long_description = readme_file.read()

setuptools.setup(
    name='json_home_client',
    version='0.0.0',  # version will get replaced by git version tag - do not edit
    author='Peter Linss',
    author_email='pypi@linss.com',
    description='Client for REST APIs using JSON Home pages per https://tools.ietf.org/html/draft-nottingham-json-home-06',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/plinss/json_home_client/',

    packages=['json_home_client'],
    package_data={'json_home_client': ['py.typed']},

    install_requires=[
        'uri_template',
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
    python_requires='>=3.6'
)

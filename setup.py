from setuptools import find_packages, setup

with open("README.md") as fh:
    long_description = fh.read()
with open("semver.txt") as fh:
    semver = fh.read().strip()
with open("requirements.txt") as fh:
    install_requires = [x.strip() for x in fh.read().strip().split("\n")]

setup(
    name="bikeshed",
    version=semver,
    author="Tab Atkins-Bittner",
    description="A document-authoring tool mainly intended for web specifications.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tabatkins/bikeshed/",
    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: Public Domain",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Documentation",
    ],
    entry_points={"console_scripts": ["bikeshed = bikeshed:main"]},
)

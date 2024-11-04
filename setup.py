from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()
with open("bikeshed/semver.txt", encoding="utf-8") as fh:
    semver = fh.read().strip()
with open("requirements.txt", encoding="utf-8") as fh:
    install_requires = [x.strip() for x in fh.read().strip().split("\n") if len(x) and x[0].isalpha()]

setup(
    name="bikeshed",
    version=semver,
    author="Tab Atkins-Bittner",
    description="A document-authoring tool mainly intended for web specifications.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/speced/bikeshed/",
    packages=find_packages(),
    package_data={"bikeshed": ["py.typed"]},
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: Public Domain",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.9",
        "Topic :: Software Development :: Documentation",
    ],
    entry_points={"console_scripts": ["bikeshed = bikeshed:main"]},
)

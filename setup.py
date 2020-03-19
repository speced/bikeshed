from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='bikeshed',
    version='1.0.0',
    author='Tab Atkins-Bittner',
    description="A document-authoring tool mainly intended for web specifications.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tabatkins/bikeshed/",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'pygments>=2.6.1,<2.7',
        'lxml>=4.5,<4.6',
        'html5lib>=1.0.1,<1.1',
        'cssselect>=1.1.0,<1.2',
        'typing-extensions>=3.7.4.1,<3.8',
        'widlparser>=1,<2',
        'json_home_client>=1,<2',
    ],
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: Public Domain",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Documentation",
    ],
    entry_points={'console_scripts': ['bikeshed = bikeshed:main']},
)

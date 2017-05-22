from setuptools import setup, find_packages

setup(
    name='Bikeshed',
    author='Tab Atkins Jr.',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['pygments','lxml', 'html5lib', 'cssselect'],
    entry_points={'console_scripts': ['bikeshed = bikeshed:main']},
)

from setuptools import setup

setup(
    name='css-bikeshed',
    author='Tab Atkins Jr.',
    py_modules=['preprocess'],
    install_requires=['lxml', 'html5lib', 'cssselect'],
    entry_points={'console_scripts': ['css-bikeshed = bikeshed:main']},
)

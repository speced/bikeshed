from setuptools import setup


setup(
    name='css-preprocessor',
    author='Tab Atkins Jr.',
    py_modules=['preprocess'],
    install_requires=['lxml', 'html5lib', 'cssselect'],
    entry_points={'console_scripts': ['css-preprocess = preprocess:main']},
)

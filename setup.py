from setuptools import setup, find_packages

setup(
    name='Bikeshed',
    author='Tab Atkins Jr.',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'pygments>=2.3.0,<2.4',
        'lxml>=4.2.5,<4.3',
        'html5lib>=1.0.1,<1.1',
        'cssselect>=1.0.3,<1.1',
    ],
    entry_points={'console_scripts': ['bikeshed = bikeshed:main']},
)

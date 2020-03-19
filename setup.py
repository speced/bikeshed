from setuptools import setup, find_packages

setup(
    name='Bikeshed',
    author='Tab Atkins Jr.',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'pygments>=2.6.1,<2.7',
        'lxml>=4.5,<4.6',
        'html5lib>=1.0.1,<1.1',
        'cssselect>=1.1.0,<1.2',
        'widlparser>=1.0.2,<2',
        'json_home_client>=1,<2',
    ],
    entry_points={'console_scripts': ['bikeshed = bikeshed:main']},
)

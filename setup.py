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
        'typing-extensions>=3.7.4.1,<3.8',
        'widlparser>=1,<2',
        'json_home_client>=1,<2',
    ],
    entry_points={'console_scripts': ['bikeshed = bikeshed:main']},
)

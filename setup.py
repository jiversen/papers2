from setuptools import setup, find_packages, findall
import os

def find_scripts(script_dir):
    return [s for s in findall(script_dir) if os.path.splitext(s)[1] != '.pyc']

setup(
    name='papers2',

    version='0.2.0',

    description='API to access Papers2 database, and scripts to convert to Zotero. Built upon work of John Didion.',

    # The project's main homepage.
    url='https://github.com/jiversen/papers2',

    # Author details
    author='John Iversen',
    author_email='john@johniversen.org',

    # Choose your license
    license='GPL',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: GPLv3',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3.10',
    ],

    packages=find_packages(exclude=['scripts']),
    
    scripts=find_scripts('bin/'),
    
    install_requires=[
        'pyzotero',
        'sqlalchemy'
    ]
)
### -*- coding: utf-8 -*-
###
###  Copyright 2011-2016 Peter Williams <pwil3058@gmail.com>
###
### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.
###
### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.
###
### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
import glob
import os

from darning import version

here = os.path.abspath(os.path.dirname(__file__))

NAME = "darning"

VERSION = version.VERSION

DESCRIPTION = "a tool for managing a series of source patches."

# Get the long description from the README file
with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

pixmaps = glob.glob("pixmaps/*.png")

PIXMAPS = [("share/pixmaps", ["darning.png", "darning.ico"]), ("share/pixmaps/darning", pixmaps)]

COPYRIGHT = [("share/doc/darning", ["COPYING", "copyright"])]

LICENSE = "GNU General Public License (GPL) Version 2.0"

CLASSIFIERS = [
    "Development Status :: Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: {}".format(LICENSE),
    "Programming Language :: Python",
    "Topic :: Software Development :: Patch Management",
    #"Operating System :: MacOS :: MacOS X",
    #"Operating System :: Microsoft :: Windows",
    "Operating System :: POSIX",
]

KEYWORDS = []

AUTHOR = "Peter Williams"

AUTHOR_EMAIL = "pwil3058@gmail.com"

URL = "https://github.com/pwil3058/darning"

SCRIPTS = ["darn", "gdarn"]

PACKAGES = find_packages(exclude=["pixmaps", "test_cli"])

INSTALL_REQUIRES = []

EXTRAS_REQUIRE = {}

PACKAGE_DATA = {}

ENTRY_POINTS = {}

setup(
    name = NAME,
    version = VERSION,
    description = DESCRIPTION,
    long_description = LONG_DESCRIPTION,
    url = URL,
    classifiers = CLASSIFIERS,
    license = LICENSE,
    author = AUTHOR,
    author_email = AUTHOR_EMAIL,
    keywords = KEYWORDS,
    packages = PACKAGES,
    install_requires = INSTALL_REQUIRES,
    extras_require = EXTRAS_REQUIRE,
    package_data = PACKAGE_DATA,
    data_files = PIXMAPS + COPYRIGHT,
    scripts = SCRIPTS,
    entry_points = ENTRY_POINTS,
)

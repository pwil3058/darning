### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

from distutils.core import setup
import glob

from darning import version

NAME = 'darning'

VERSION = version.VERSION

DESCRIPTION = 'a tool for managing a series of source patches.'

LONG_DESCRIPTION =\
'''
Darning is a tool for managing as series of patches to source files.
'''

pixmaps = glob.glob('pixmaps/*.png')

PIXMAPS = [('share/pixmaps', ['darning.png', 'darning.ico']), ('share/pixmaps/darning', pixmaps)]

COPYRIGHT = [('share/doc/darning', ['COPYING', 'copyright'])]

LICENSE = 'GNU General Public License (GPL) Version 2.0'

CLASSIFIERS = [
    'Development Status :: Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: %s' % LICENSE,
    'Programming Language :: Python',
    'Topic :: Software Development :: Patch Management',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: Microsoft :: Windows',
    'Operating System :: POSIX',
]

AUTHOR = 'Peter Williams'

AUTHOR_EMAIL = 'peter_ono@users.sourceforge.net'

URL = 'http://darning.sourceforge.net/'

SCRIPTS = ['darn', 'gdarn']

PACKAGES = ['darning', 'darning/cli', 'darning/gui']

setup(
    name = NAME,
    version = VERSION,
    description = DESCRIPTION,
    long_description = LONG_DESCRIPTION,
    classifiers = CLASSIFIERS,
    license = LICENSE,
    author = AUTHOR,
    author_email = AUTHOR_EMAIL,
    url = URL,
    scripts = SCRIPTS,
    packages = PACKAGES,
    data_files = PIXMAPS + COPYRIGHT
)

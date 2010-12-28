### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>
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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''
Provide command line parsing mechanism including provision of a
mechanism for sub commands to add their components.
'''

import argparse
import collections

import darning.version

PARSER = argparse.ArgumentParser(description='Manage stacked patches')

PARSER.add_argument(
    '--version',
    action='version',
    version=darning.version.VERSION
)

SUB_CMD_PARSER = PARSER.add_subparsers(title='commands')

# There doesn't seem to be a way to easily change the help messages
# in argparse arguments incorporated using the "parents" mechanism so
# we'll adopt a slghtly different approach

_COMOPT = collections.namedtuple('_COMOPT', ['name', 'action', 'nargs',
    'const', 'default', 'type', 'choices', 'required', 'help',
    'metavar', 'dest'])

_DEFAULT_COMOPT = _COMOPT(None, None, None, None, None, None, None, None, None, None, None)

OPT_DESCR = _DEFAULT_COMOPT._replace(name='--descr', dest='opt_description', metavar='text')
OPT_PATCH = _DEFAULT_COMOPT._replace(name='-P', dest='opt_patch', metavar='patch')

ARG_FILES = _DEFAULT_COMOPT._replace(name='filenames', metavar='file', nargs='+')

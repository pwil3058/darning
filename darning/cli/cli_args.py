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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

'''
Provide command line parsing mechanism including provision of a
mechanism for sub commands to add their components.
'''

import argparse
import collections

from darning import i18n

import darning.version

PARSER = argparse.ArgumentParser(description=_('Manage stacked patches'))

PARSER.add_argument(
    '--version',
    action='version',
    version=darning.version.VERSION
)

SUB_CMD_PARSER = PARSER.add_subparsers(title=_('commands'))

# There doesn't seem to be a way to easily change the help messages
# in argparse arguments incorporated using the "parents" mechanism so
# we'll adopt a slghtly different approach

def add_descr_option(parser, helptext):
    parser.add_argument(
        '--descr',
        help=helptext,
        dest='opt_description',
        metavar=_('text'),
    )

def add_patch_option(parser, helptext):
    parser.add_argument(
        '-P', '--patch',
        help=helptext,
        dest='opt_patch',
        metavar=_('patch'),
    )

def add_force_option(parser, helptext):
    parser.add_argument(
        '-f', '--force',
        help=helptext,
        dest='opt_force',
        action='store_true',
    )

def add_verbose_option(parser, helptext):
    parser.add_argument(
        '-v', '--verbose',
        help=helptext,
        dest='opt_verbose',
        action='store_true',
    )

def add_files_argument(parser, helptext):
    parser.add_argument(
        'filenames',
        help=helptext,
        nargs='+',
        metavar=_('file'),
    )

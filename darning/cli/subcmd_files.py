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

'''List a patch's files.'''

import sys

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning import cmd_result

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'files',
    description=_('List the files in the named (or top) patch.'),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    '--combined',
    dest='opt_combined',
    help=_('show files for all applied patches combined.'),
    action='store_true'
)

GROUP.add_argument(
    'patchname',
    metavar=_('patchname'),
    nargs='?',
    help=_('the name of the patch whose files are to be listed.'),
)

def format_file_data(file_data):
    if file_data.related_file:
        return '{0}: {1} {2} {3}\n'.format(file_data.status.presence, patch_db.rel_subdir(file_data.name), file_data.related_file.relation, patch_db.rel_subdir(file_data.related_file.path))
    else:
        return '{0}: {1}\n'.format(file_data.status.presence, patch_db.rel_subdir(file_data.name))

def run_files(args):
    '''Execute the "files" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    patchname = patch_db.get_patch_name(args.patchname)
    if patchname is None:
        return cmd_result.ERROR
    if args.opt_combined:
        for file_data in sorted(patch_db.get_combined_patch_file_table()):
            sys.stdout.write(format_file_data(file_data))
    else:
        for file_data in sorted(patch_db.get_patch_file_table(patchname)):
            sys.stdout.write(format_file_data(file_data))
    return cmd_result.OK

PARSER.set_defaults(run_cmd=run_files)

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

'''Print the diff for the named (or all) files in the named (or top) patch.'''

import sys

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning import cmd_result

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'diff',
    description=_('Print the "diff" for the named (or all files) in the named (or top) patch.'),
    epilog=_('''For applied patches, the printed "diff" will be reflect the actual
        changes rather than the "refreshed" changes.  For unapplied patches, the change will
        (obviously) reflect that last "refeshed" change.'''),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    '--combined',
    dest='opt_combined',
    help=_('show "diff" for all applied patches combined.'),
    action='store_true'
)

cli_args.add_patch_option(GROUP, 'the name of the patch for which the "diff" should be printed.')

PARSER.add_argument(
    '--notimestamps',
    dest='opt_notimestamps',
    help=_('omit timestamp data from the generated "diff".'),
    action='store_true'
)

PARSER.add_argument(
    'filepaths',
    metavar=_('file'),
    nargs='*',
    help=_('the name(s) of the file(s) to be included in the "diff".'),
)

def run_diff(args):
    '''Execute the "diff" sub command using the supplied args'''
    db_utils.open_db(modifiable=False)
    db_utils.set_report_context(verbose=True)
    if args.opt_combined:
        diff = patch_db.get_combined_diff_for_files(args.filepaths, not args.opt_notimestamps)
    else:
        diff = patch_db.get_diff_for_files(args.filepaths, args.opt_patch, not args.opt_notimestamps)
    if diff is False:
        return cmd_result.ERROR
    sys.stdout.write(diff)
    return cmd_result.OK

PARSER.set_defaults(run_cmd=run_diff)

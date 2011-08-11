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

'''List a patch's series.'''

import sys

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning import cmd_result

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'series',
    description=_('List the patches in the series.'),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    '--applied',
    dest='opt_applied',
    help=_('show only applied patches.'),
    action='store_true'
)

GROUP.add_argument(
    '--unapplied',
    dest='opt_unapplied',
    help=_('show only unapplied patches.'),
    action='store_true'
)

GROUP.add_argument(
    '--blocked',
    dest='opt_blocked',
    help=_('show patches blocked by guards.'),
    action='store_true'
)

def format_patch_data(patch_data):
    return '{0}: {1}\n'.format(patch_data.state, patch_data.name)

def run_series(args):
    '''Execute the "series" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    table = patch_db.get_patch_table_data()
    if args.opt_applied:
        for patch_data in [pdat for pdat in table if pdat.state != patch_db.PatchState.UNAPPLIED]:
            sys.stdout.write('{0}\n'.format(patch_data.name))
    elif args.opt_unapplied:
        for patch_data in [pdat for pdat in table if pdat.state == patch_db.PatchState.UNAPPLIED]:
            sys.stdout.write('{0}\n'.format(patch_data.name))
    elif args.opt_blocked:
        for patch_data in [pdat for pdat in table if pdat.state == patch_db.PatchState.UNAPPLIED]:
            if not patch_db.is_patch_pushable(patch_data.name):
                sys.stdout.write('{0}\n'.format(patch_data.name))
    else:
        for patch_data in table:
            sys.stdout.write(format_patch_data(patch_data))
    #if args.opt_applied:
        #for patch_data in sorted(patch_db.get_combined_patch_file_table()):
            #sys.stdout.write(format_patch_data(patch_data))
    #else:
        #patchname = patch_db.get_patch_name(args.patchname)
        #if patchname is None:
            #return cmd_result.ERROR
        #for patch_data in sorted(patch_db.get_patch_file_table(patchname)):
            #sys.stdout.write(format_patch_data(patch_data))
    return cmd_result.OK

PARSER.set_defaults(run_cmd=run_series)

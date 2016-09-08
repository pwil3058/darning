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

from aipoed import CmdResult

from . import cli_args
from . import db_utils

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
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    table = PM.get_patch_table_data()
    if args.opt_applied:
        for patch_data in [pdat for pdat in table if pdat.state != PM.PatchState.NOT_APPLIED]:
            sys.stdout.write('{0}\n'.format(patch_data.name))
    elif args.opt_unapplied:
        for patch_data in [pdat for pdat in table if pdat.state == PM.PatchState.NOT_APPLIED]:
            sys.stdout.write('{0}\n'.format(patch_data.name))
    elif args.opt_blocked:
        for patch_data in [pdat for pdat in table if pdat.state == PM.PatchState.NOT_APPLIED]:
            if not PM.is_patch_pushable(patch_data.name):
                sys.stdout.write('{0}\n'.format(patch_data.name))
    else:
        for patch_data in table:
            sys.stdout.write(format_patch_data(patch_data))
    return CmdResult.OK

PARSER.set_defaults(run_cmd=run_series)

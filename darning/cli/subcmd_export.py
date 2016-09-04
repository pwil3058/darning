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

'''Print a text version of a patch to standard output.'''

import sys

from .. import CmdResult

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'export',
    description=_('Output a text version of the named (or top) patch to standard output.'),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    '--combined',
    dest='opt_combined',
    help=_('text version all applied patches combined.'),
    action='store_true'
)

GROUP.add_argument(
    'patchname',
    metavar=_('patchname'),
    nargs='?',
    help=_('the name of the patch to be exported.'),
)

def run_export(args):
    '''Execute the "export" sub command using the supplied args'''
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    patchname = PM.get_named_or_top_patch_name(args.patchname)
    if patchname is None:
        return CmdResult.ERROR
    if args.opt_combined:
        tpatch = PM.get_combined_textpatch()
    else:
        tpatch = PM.get_textpatch(patchname)
    sys.stdout.write(str(tpatch))
    return CmdResult.OK

PARSER.set_defaults(run_cmd=run_export)

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

'''Set/display a patch's guards.'''

import sys

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "guard",
    description=_("Display/select which patch guards are in force."),
    epilog=_("""When invoked with no arguments the patch's current guards are listed."""),
)

PARSER.add_argument(
    "patch_name",
    help=_("the patch to which the guards are to be attached."),
    default=None,
    nargs="?",
    metavar=_("patch"),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    "-n", "--none",
    help=_("Disable all guards."),
    dest="opt_none",
    action="store_true",
)

GROUP.add_argument(
    "-g", "--guard",
    help=_("list of guards to be attached to the patch."),
    dest="guards",
    metavar="(+|-)guard",
    action="append",
)

def run_guard(args):
    '''Execute the "guard" sub command using the supplied args'''
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    if args.opt_none:
        return PM.do_set_patch_guards_fm_list(args.patch_name, None)
    elif args.guards:
        return PM.do_set_patch_guards_fm_list(args.patch_name, args.guards)
    else:
        pos_guards, neg_guards = PM.get_patch_guards(args.patch_name)
        for guard in sorted(pos_guards):
            sys.stdout.write("+{0}\n".format(guard))
        for guard in sorted(neg_guards):
            sys.stdout.write("-{0}\n".format(guard))
    return 0

PARSER.set_defaults(run_cmd=run_guard)

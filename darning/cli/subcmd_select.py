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

"""Select/display which patch guards are in force."""

import sys

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "select",
    description=_("Display/select which patch guards are in force."),
    epilog=_("""When invoked with no arguments the currently selected guards are listed."""),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    "-n", "--none",
    help=_("Disable all guards."),
    dest="opt_none",
    action="store_true",
)

GROUP.add_argument(
    "-s", "--set",
    help=_("the list of guards to be enabled/selected."),
    dest="guards",
    metavar="guard",
    action="append",
)

def run_select(args):
    """Execute the "select" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    if args.opt_none:
        return PM.do_select_guards(None)
    elif args.guards:
        return PM.do_select_guards(args.guards)
    else:
        selected_guards = PM.get_selected_guards()
        for guard in sorted(selected_guards):
            sys.stdout.write(guard + "\n")
    return 0

PARSER.set_defaults(run_cmd=run_select)

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

"""Unapply the current top patch."""

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "add",
    description=_("Add nominated file(s) to the top patch."),
    epilog=_("""If any of the nominated files have uncommitted changes from
    the point of view of the SCM controlling the sources or unrefreshed changes
    in an applied patch below the top patch the addition will be aborted unless
    either the force or the absorb option is specified."""),
)

GROUP = PARSER.add_mutually_exclusive_group()

cli_args.add_force_option(GROUP, helptext=_("force the operation and leave uncommitted/unrefreshed changes to named files out of the top patch."))

cli_args.add_absorb_option(GROUP, helptext=_("absorb/incorporate uncommitted/unrefreshed changes to named files into the top patch."))

cli_args.add_files_argument(PARSER, helptext=_("the file(s) to be added."))

def run_add(args):
    """Execute the "add" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    return PM.do_add_files_to_top_patch(args.filepaths, absorb=args.opt_absorb, force=args.opt_force)

PARSER.set_defaults(run_cmd=run_add)

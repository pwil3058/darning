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

"""Duplicat a named patch in the series behind the current top patch."""

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "duplicate",
    description=_("Duplicate a patch in the series after the current top patch."),
)

cli_args.add_descr_option(PARSER, helptext=_("a description of the patch's purpose."))

PARSER.add_argument(
    "patch_name",
    metavar=_("patch_name"),
    help=_("the name of the patch to be duplicated."),
)

PARSER.add_argument(
    "as_patch_name",
    metavar=_("as_patch_name"),
    help=_("the name for the duplicated patch."),
)

def run_duplicate(args):
    """Execute the "duplicate" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    return PM.do_duplicate_patch(args.patch_name, args.as_patch_name, args.opt_description)

PARSER.set_defaults(run_cmd=run_duplicate)

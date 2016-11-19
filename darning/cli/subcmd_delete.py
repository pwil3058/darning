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

"""Delete files within the current top patch."""

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "delete",
    description=_("Delete nominated file(s) within the top patch."),
    epilog=_("""Any of the nominated files not already in the top patch
    will added to the top patch before being deleted."""),
)

GROUP = PARSER.add_mutually_exclusive_group()

cli_args.add_files_argument(PARSER, helptext=_("the file(s) to be deleted."))

def run_delete(args):
    """Execute the "delete" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    return PM.do_delete_files_in_top_patch(args.filepaths)

PARSER.set_defaults(run_cmd=run_delete)

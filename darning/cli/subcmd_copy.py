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

"""Copy a file within the current top patch."""

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "copy",
    description=_("copy the nominated file to the nominated path within the top patch."),
    epilog=_("""If a file with the nominated target path is already in the top patch
        this command will abort unless the --overwrite option is used.  In this case,
        any changes that have been made to that file in the patch will be irretrievably lost."""),
)

cli_args.add_overwrite_option(PARSER, helptext=_("overwrite an existing file even if it is already in the patch and may contain changes."))

PARSER.add_argument(
    "from_path",
    help="the path of the file to be copied.",
    metavar=_("source"),
)

PARSER.add_argument(
    "to_path",
    help="the path of the file \"source\" is to be copied to.",
    metavar=_("target"),
)

def run_copy(args):
    """Execute the "copy" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    return PM.do_copy_file_to_top_patch(args.from_path, args.to_path, overwrite=args.opt_overwrite)

PARSER.set_defaults(run_cmd=run_copy)

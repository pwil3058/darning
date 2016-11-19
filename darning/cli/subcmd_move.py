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

"""Move/rename a file within the current top patch."""

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "move",
    description=_("move the nominated file(s) to the nominated path within the top patch."),
    epilog=_("""If a file with the nominated target paths exists (even if it is already in the top patch)
        this command will abort unless the --overwrite option is used.  In this case,
        any changes that have been made to that file within will be irretrievably lost.\n\n
        If the file to be moved has unrefreshed changes (or uncommitted changes from the underlying
        SCM's point of view) this command will abort unless the --force option is used."""),
)

cli_args.add_overwrite_option(PARSER, helptext=_("overwrite an existing file even if it is already in the patch and may contain changes."))

cli_args.add_force_option(PARSER, helptext=_("move the file even if it has unrefreshed or uncommitted changes."))

PARSER.add_argument(
    "--mkdir",
    help="create the target directory if necessary",
    dest="opt_mkdir",
    action="store_true",
)

PARSER.add_argument(
    "from_paths",
    help="the path of the file to be moved.",
    metavar=_("source"),
    nargs="+"
)

PARSER.add_argument(
    "to_path",
    help="the path that the \"source\" file(s) is/are to be moved to. Must be a directory if more than source file specified.",
    metavar=_("target"),
)

def run_move(args):
    """Execute the "move" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    return PM.do_move_files_in_top_patch(args.from_paths, args.to_path, force=args.opt_force, overwrite=args.opt_overwrite, make_dir=args.opt_mkdir)

PARSER.set_defaults(run_cmd=run_move)

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

"""Manage removed patches available for restoration."""

import sys

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "kept",
    description=_("Manage removed patches that are available for restoration."),
    epilog=_("If no arguments are given to this command the available \"kept\" patches will be listed."),
)

EGROUP = PARSER.add_mutually_exclusive_group()

EGROUP.add_argument(
    "--delete",
    help=_("Delete the listed patches."),
    nargs="+",
    dest="delete_patches_named",
    metavar="patchname",
)

RGROUP = EGROUP.add_argument_group()

RGROUP.add_argument(
    "--restore",
    help=_("Restore the named patch."),
    dest="restore_patch_named",
    metavar="patchname",
)

RGROUP.add_argument(
    "--as",
    help=_("The name to give the restored patch."),
    dest="as_patch_name",
    metavar="patchname",
    required=False
)

def run_kept(args):
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    if args.delete_patches_named:
        return PM.do_delete_kept_patches(args.delete_patches_named)
    elif args.restore_patch_named:
        return PM.do_restore_patch(args.restore_patch_named, args.as_patch_name if args.as_patch_name else args.restore_patch_named)
    else:
        for patch_name in PM.get_kept_patch_names():
            sys.stdout.write(patch_name + "\n")
        return 0

PARSER.set_defaults(run_cmd=run_kept)

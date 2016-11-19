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

"""List a patch's files."""

import sys

from ..bab import CmdResult

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    "files",
    description=_("List the files in the named (or top) patch."),
)

GROUP = PARSER.add_mutually_exclusive_group()

GROUP.add_argument(
    "--combined",
    dest="opt_combined",
    help=_("show files for all applied patches combined."),
    action="store_true"
)

GROUP.add_argument(
    "patchname",
    metavar=_("patchname"),
    nargs="?",
    help=_("the name of the patch whose files are to be listed."),
)

def format_file_data(PM, file_data):
    VAL_MAP = {
        None: " ",
        PM.Validity.REFRESHED: "+",
        PM.Validity.NEEDS_REFRESH: "?",
        PM.Validity.UNREFRESHABLE: "!",
    }
    def status_to_str(status):
        return "{0}:{1}".format(status.presence, VAL_MAP[status.validity])
    if file_data.related_file_data:
        return "{0}: {1} {2} {3}\n".format(status_to_str(file_data.status), PM.rel_subdir(file_data.path), file_data.related_file_data.relation, PM.rel_subdir(file_data.related_file_data.path))
    else:
        return "{0}: {1}\n".format(status_to_str(file_data.status), PM.rel_subdir(file_data.path))

def run_files(args):
    """Execute the "files" sub command using the supplied args"""
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    patchname = PM.get_named_or_top_patch_name(args.patchname)
    if patchname is None:
        return CmdResult.ERROR
    if args.opt_combined:
        for file_data in sorted(PM.get_combined_patch_file_table()):
            sys.stdout.write(format_file_data(PM, file_data))
    else:
        for file_data in sorted(PM.get_patch_file_table(patchname)):
            sys.stdout.write(format_file_data(PM, file_data))
    return CmdResult.OK

PARSER.set_defaults(run_cmd=run_files)

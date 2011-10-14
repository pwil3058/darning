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

'''Move/rename a file within the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'move',
    description=_('move the nominated file to the nominated path within the top patch.'),
    epilog=_('''If a file with the nominated target path is already in the top patch
        this command will abort unless the --overwrite option is used.  In this case,
        any changes that have been made to that file in the patch will be irretrievably lost.\n\n
        If the file to be moved has unrefreshed changes (or uncommitted changes from the underlying
        SCM's point of view) this command will abort unless the --force option is used.'''),
)

cli_args.add_overwrite_option(PARSER, helptext=_('overwrite an existing file even if it is already in the patch and may contain changes.'))

cli_args.add_force_option(PARSER, helptext=_('move the file even if it has unrefreshed or uncommitted changes.'))

PARSER.add_argument(
    'from_path',
    help='the path of the file to be moved.',
    metavar=_('source'),
)

PARSER.add_argument(
    'to_path',
    help='the path of the file "source" is to be moved to.',
    metavar=_('target'),
)

def run_move(args):
    '''Execute the "move" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    return patch_db.do_rename_file_in_top_patch(args.from_path, args.to_path, force=args.opt_force, overwrite=args.opt_overwrite)

PARSER.set_defaults(run_cmd=run_move)

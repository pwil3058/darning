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

'''Unapply the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'add',
    description=_('Add nominated file(s) to the top (or nominated) patch.'),
)

cli_args.add_patch_option(PARSER, helptext=_('the name of the patch to add the file(s) to.'))

cli_args.add_force_option(PARSER, helptext=_('incorporate uncommitted/unrefreshed changes to named files into the top (or nominated) patch.'))

cli_args.add_files_argument(PARSER, helptext=_('the file(s) to be added.'))

def run_add(args):
    '''Execute the "add" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    return patch_db.do_add_files_to_patch(db_utils.get_report_context(verbose=True), args.opt_patch, args.filepaths, force=args.opt_force)

PARSER.set_defaults(run_cmd=run_add)

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

'''Create a new patch in the series behind the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'new',
    description=_('Create a new patch in the series after the current top patch.'),
)

cli_args.add_descr_option(PARSER, helptext=_('a description of the patch\'s purpose.'))

PARSER.add_argument(
    'patchname',
    metavar=_('patchname'),
    help=_('the name of the patch.'),
)

def run_new(args):
    '''Execute the "new" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    return patch_db.do_create_new_patch(args.patchname, args.opt_description)

PARSER.set_defaults(run_cmd=run_new)

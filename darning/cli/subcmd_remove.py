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

'''Remove a named patch from the series.'''

from .. import patch_db

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'remove',
    description=_('Remove the named patch from the series.'),
)

PARSER.add_argument(
    'patchname',
    metavar=_('patchname'),
    help=_('the name of the patch to be removed.'),
)

def run_remove(args):
    '''Execute the "new" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    return patch_db.do_remove_patch(args.patchname)

PARSER.set_defaults(run_cmd=run_remove)

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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''Create a new patch in the series behind the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'new',
    description='Create a new patch in the series after the current top patch.',
)

cli_args.add_descr_option(PARSER, helptext='a description of the patch\'s purpose.')

PARSER.add_argument(
    'patchname',
    help='the name of the patch.',
)

def run_new(args):
    '''Execute the "new" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if patch_db.patch_is_in_series(args.patchname):
        return msg.Error('patch "{0}" already exists', args.patchname)
    patch_db.create_new_patch(args.patchname, args.opt_description)
    warn = patch_db.top_patch_needs_refresh()
    if warn:
        old_top = patch_db.get_top_patch_name()
    patch_db.apply_patch()
    msg.Info('Patch "{0}" is now on top.', patch_db.get_top_patch_name())
    if warn:
        msg.Warn('Previous top patch ("{0}") needs refreshing.', old_top)
    return msg.OK

PARSER.set_defaults(run_cmd=run_new)

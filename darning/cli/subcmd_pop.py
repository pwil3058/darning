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

'''Unapply the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'pop',
    description='Unapply the top patch.',
)

def run_pop(args):
    '''Execute the "pop" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    top_patch = patch_db.get_top_patch_name()
    if not top_patch:
        return msg.Error('No patches applied')
    if patch_db.top_patch_needs_refresh():
        return msg.Error('Top patch ("{0}") needs to be refreshed', top_patch)
    result = patch_db.unapply_top_patch()
    if result is not True:
        return msg.Error('{0}: top patch is now "{1}"', result, patch_db.get_top_patch_name())
    else:
        top_patch = patch_db.get_top_patch_name()
        if top_patch is None:
            return msg.Info('There are now no patches applied')
        else:
            return msg.Info('Patch "{1}" is now on top', result, top_patch)
    return msg.OK

PARSER.set_defaults(run_cmd=run_pop)

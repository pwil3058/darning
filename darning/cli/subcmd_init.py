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

'''Create a darning patch management system (persistent) database'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'init',
    description=_('Create a new patch database.'),
)

cli_args.add_descr_option(PARSER, helptext=_('a message to describe the purpose of the patches to be managed.'))

def run_init(args):
    '''Execute the "init" sub command using the supplied args'''
    result = patch_db.create_db(description=args.opt_description)
    if not result:
        return msg.Error(result)
    return msg.OK

PARSER.set_defaults(run_cmd=run_init)

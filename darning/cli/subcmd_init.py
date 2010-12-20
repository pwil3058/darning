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

from darning import patch_db
from darning.cli import cli_args

OK = 0

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'init',
    description='Create a new patch patch database.',
)

PARSER.add_argument(
    '--msg',
    help='a message to describe the purpose of the patches to be managed.',
    dest='description',
    metavar='text',
)

def run_init(args):
    result = patch_db.create_db(description=args.description)
    if not result:
        return 'Error: %s' % result
    return OK

PARSER.set_defaults(run_cmd=run_init)

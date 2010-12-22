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

import sys

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils

OK = 0

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'new',
    description='Create a new patch in the series after the current top patch.',
)

PARSER.add_argument(
    '--descr',
    help='a description of the patch\'s purpose.',
    dest='description',
    metavar='text',
)

PARSER.add_argument(
    'patchname',
    help='the name of the patch.',
)

def run_new(args):
    '''Execute the "new" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    try:
        if patch_db.patch_is_in_series(args.patchname):
            return 'Error: patch "%s" already exists' % args.patchname
        patch_db.create_new_patch(args.patchname, args.description)
        warn = patch_db.top_patch_needs_refresh()
        if warn:
            old_top = patch_db.get_top_patch_name()
        patch_db.apply_patch()
        sys.stdout.write('Patch "%s" is now on top.\n' % patch_db.get_top_patch_name())
        if warn:
            sys.stderr.write('Previous top patch ("%s") needs refreshing\n' % old_top)
    finally:
        close_ok = db_utils.close_db()
    return OK if close_ok else close_ok

PARSER.set_defaults(run_cmd=run_new)

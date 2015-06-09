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

'''
Utility database functions that are ony of interest CLI programs
'''

import os
import sys
import atexit

from .. import rctx
from .. import patch_db
from .. import scm_ifce

def open_db(modifiable):
    '''Change directory to the base direcory and open the database'''
    BASE_DIR = patch_db.find_base_dir(remember_sub_dir=True)
    if BASE_DIR:
        os.chdir(BASE_DIR)
    else:
        sys.exit(_('Valid database NOT found.'))
    result = patch_db.load_db(modifiable)
    if not result:
        sys.exit(str(result))
    atexit.register(patch_db.release_db)
    return True

def set_report_context(verbose=True):
    if not verbose:
        rctx.reset(open('/dev/null', 'w'), sys.stderr)

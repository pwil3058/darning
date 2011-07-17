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

from darning import patch_db
from darning import scm_ifce
from darning.cli import msg

BASE_DIR = SUB_DIR = SUB_DIR_DOWN = None

def open_db(modifiable):
    '''Change directory to the base direcory and open the database'''
    global BASE_DIR, SUB_DIR, SUB_DIR_DOWN
    BASE_DIR, SUB_DIR = patch_db.find_base_dir()
    if BASE_DIR is None:
        sys.exit(msg.Error(_('could not find a "darning" database')))
    if SUB_DIR is not None:
        SUB_DIR_DOWN = os.path.join(*['..'] * len(SUBDIR.split(os.sep)))
    os.chdir(BASE_DIR)
    scm_ifce.reset_back_end()
    result = patch_db.load_db(modifiable)
    if not result:
        sys.exit(msg.Error(result))
    atexit.register(patch_db.release_db)
    return True

def prepend_subdir(filepaths):
    if SUB_DIR is not None:
        for findex in range(len(filepaths)):
            filepaths[findex] = os.path.join(SUB_DIR, filepaths[findex])

def rel_subdir(filepath):
    if SUB_DIR_DOWN is None:
        return filepath
    else:
        return os.path.join(SUB_DIR_DOWN, filepath)

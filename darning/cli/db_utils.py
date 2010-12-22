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

'''
Utility database functions that are ony of interest CLI programs
'''

import os
import sys

from darning import patch_db

BASE_DIR = SUB_DIR = None

def open_db(modifiable):
    '''Change directory to the base direcory and open the database'''
    global BASE_DIR, SUB_DIR
    BASE_DIR, SUB_DIR = patch_db.find_base_dir()
    if BASE_DIR is None:
        sys.exit('Error: could not find a "darning" database')
    os.chdir(BASE_DIR)
    result = patch_db.load_db(modifiable)
    if not result:
        sys.exit('Error: %s' % result)
    return True

def close_db():
    '''Close the database'''
    return patch_db.release_db()

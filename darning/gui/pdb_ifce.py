### Copyright (C) 2011 Peter Williams <peter@users.sourceforge.net>
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

'''GUI interface to patch_db'''

from darning import patch_db
from darning import cmd_result

# patch_db commands that don't need wrapping
from darning.patch_db import find_base_dir

from darning.gui import ws_event

def open_db():
    result = patch_db.load_db(lock=True)
    if result is True:
        return cmd_result.Result(cmd_result.OK, '', '')
    return cmd_result.Result(cmd_result.ERROR, '', str(result))

def close_db():
    '''Close the patch database if it is open'''
    if patch_db.is_readable():
        patch_db.release_db()

def initialize(description):
    '''Create a patch database in the current directory'''
    return patch_db.create_db(description)

def get_in_progress():
    return patch_db.is_readable() and patch_db.get_top_patch_name() is not None

def get_all_patches_data():
    if not patch_db.is_readable():
        return []
    return patch_db.get_patch_table_data()

def get_selected_guards():
    if not patch_db.is_readable():
        return set()
    return patch_db.get_selected_guards()

def get_patch_description(patch):
    if not patch_db.is_readable():
        raise cmd_result.Failure('Database is unreadable')
    return patch_db.get_patch_description(patch)

def do_create_new_patch(name, descr):
    if patch_db.patch_is_in_series(name):
        return cmd_result.Result(cmd_result.ERROR, '', '{0}: Already exists in database'.format(name))
    patch_db.create_new_patch(name, descr)
    ws_event.notify_events(ws_event.PATCH_CREATE)
    return cmd_result.Result(cmd_result.OK, '', '')

def do_set_patch_description(patch, text):
    if not patch_db.is_readable():
        return cmd_result.Result(cmd_result.ERROR, '', 'Database is unreadable')
    patch_db.do_set_patch_description(patch, text)
    return cmd_result.Result(cmd_result.OK, '', '')

def is_pushable():
    if not patch_db.is_readable():
        return False
    return patch_db.is_pushable()

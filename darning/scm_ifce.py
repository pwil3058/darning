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
Provide an interface to SCM controlling source on which patches sit
'''

_AVAILABLE_BACK_ENDS = {}

_CURRENT_BACK_END = None

def add_back_end(backend):
    '''Add a new back end interface to the pool'''
    _AVAILABLE_BACK_ENDS[backend.name] = backend

def reset_back_end():
    '''Reset the current back end to one that is valid for cwd'''
    global _CURRENT_BACK_END
    for name in _AVAILABLE_BACK_ENDS:
        if _AVAILABLE_BACK_ENDS[name].is_valid_repo():
            _CURRENT_BACK_END = _AVAILABLE_BACK_ENDS[name]
            return
    _CURRENT_BACK_END = None

def is_valid_repo():
    '''Is the currend working directory in a valid repository?'''
    return _CURRENT_BACK_END is not None

def get_revision(filepath=None):
    '''
    Return the SCM revision for the named file or the whole playground
    if the filepath is None
    '''
    if _CURRENT_BACK_END is None:
        return None
    return _CURRENT_BACK_END.get_revision(filepath)

def get_files_with_uncommitted_changes(files=None):
    '''
    Get the subset of files which have uncommitted SCM changes.  If files
    is None assume all files in current directory.
    '''
    if _CURRENT_BACK_END is None:
        return []
    return _CURRENT_BACK_END.get_files_with_uncommitted_changes(files)

def get_file_db():
    '''
    Get the SCM view of the current directory
    '''
    if _CURRENT_BACK_END is None:
        from darning import fsdb
        return fsdb.OsFileDb()
    return _CURRENT_BACK_END.get_file_db()

def get_status_deco(status):
    '''
    Get the SCM specific decoration for the given status
    '''
    if _CURRENT_BACK_END is None:
        from darning import fsdb
        import pango
        return fsdb.Deco(pango.STYLE_NORMAL, "black")
    return _CURRENT_BACK_END.get_status_deco(status)

def get_name():
    '''
    Get the SCM name to use in displays
    '''
    if _CURRENT_BACK_END is None:
        return ''
    return _CURRENT_BACK_END.name

def is_clean(status):
    '''
    Does this status indicate a clean object?
    '''
    if _CURRENT_BACK_END is None:
        return False
    return _CURRENT_BACK_END.is_clean(status)

def copy_clean_version_to(filepath, target_name):
    '''
    Copy a clean version of the named file to the specified target
    '''
    assert _CURRENT_BACK_END is not None
    return _CURRENT_BACK_END.copy_clean_version_to(filepath, target_name)

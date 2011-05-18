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
        if _AVAILABLE_BACK_ENDS[name].in_playground():
            _CURRENT_BACK_END = _AVAILABLE_BACK_ENDS[name]
            return
    _CURRENT_BACK_END = None

def is_valid_repo():
    '''Is the currend working directory in a valid repository?'''
    return _CURRENT_BACK_END is not None

def get_revision(filename=None):
    '''
    Return the SCM revision for the named file or the whole playground
    if the filename is None
    '''
    if _CURRENT_BACK_END is None:
        return None
    return _CURRENT_BACK_END.get_revision(filename)

def has_uncommitted_change(filename):
    '''
    Does the SCM have uncommitted changes for the named file?
    '''
    if _CURRENT_BACK_END is None:
        return False
    return _CURRENT_BACK_END.has_uncommitted_change(filename)

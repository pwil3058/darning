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
Implement a patch stack management database
'''

import collections
import cPickle
import os
import stat
import copy

from darning import scm_ifce

class Failure:
    def __init__(self, msg):
        self.msg = msg
    def __bool__(self):
        return False
    def __nonzero__(self):
        return False
    def __str__(self):
        return self.msg
    def __repr__(self):
        return 'Failure(%s)' % self.msg

class _FileData:
    def __init__(self, name):
        self.name = name
        self.diff = ''
        try:
            self.old_mode = os.stat(name).st_mode
        except OSError:
            self.old_mode = None
        self.new_mode = None
        self.timestamp = 0
        self.scm_revision = None
        self.deleted = False
    def set_diff_data(diff):
        '''Set diff data for this file'''
        self.diff = diff
        try:
            stat_data = os.stat(self.name)
            self.new_mode = stat_data.st_mode
            self.timestamp = stat_data.st_mtime
            self.deleted = False
        except OSError as edata:
            if edata.errno != errno.ENOENT:
                raise
            self.new_mode = None
            self.timestamp = os.path.getmtime(self.name)
            self.deleted = True
        self.scm_revision = scm_ifce.get_revision(self.name)
    def needs_refresh():
        '''Does this file need a refresh? (Given that it is not overshadowed.)'''
        if os.path.exists(self.name):
            return self.timestamp < os.path.getmtime(self.name) or self.deleted
        else:
            return not self.deleted

class _PatchData:
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.files = dict()
        self.pos_guards = set()
        self.neg_guards = set()
        self.scm_revision = None
    def get_file_names_set(self):
        return set([entry for entry in self.files])
    def is_applied():
        return os.path.isdir(os.path.join(_BACKUPS_DIR, self.name))

class _DataBase:
    def __init__(self, description, host_scm):
        self.description = description
        self.selected_guards = set()
        self.series = list()
        self.kept_patches = dict()
        self.host_scm = None

_DB_DIR = '.darning.dbd'
_BACKUPS_DIR = os.path.join(_DB_DIR, 'backups')
_DB_FILE = os.path.join(_DB_DIR, 'database')
_DB_LOCK_FILE = os.path.join(_DB_DIR, 'lock')
_DB = None

def find_base_dir(dirpath=None):
    '''Find the nearest directory above that contains a database'''
    if dirpath is None:
        dirpath = os.getcwd()
    subdir_parts = []
    while True:
        if os.path.isdir(os.path.join(dirpath, _DB_DIR)):
            subdir = None if not subdir_parts else os.path.join(*subdir_parts)
            return dirpath, subdir
        else:
            dirpath, basename = os.path.split(dirpath)
            if not basename:
                break
            subdir_parts.insert(0, basename)
    return None, None

def exists():
    return os.path.isfile(_DB_FILE)

def is_readable():
    return exists() and _DB is not None

def is_writable():
    if not is_readable():
        return False
    try:
        lock_pid = open(_DB_LOCK_FILE).read()
    except IOError:
        lock_pid = False
    return lock_pid and lock_pid == str(os.getpid())

def create_db(description, dirpath=None):
    def rollback():
        if os.path.exists(db_file):
            os.remove(db_file)
        for dirnm in [bu_dir, db_dir]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    db_dir = _DB_DIR if not dirpath else os.path.join(dirpath, _DB_DIR)
    bu_dir = _BACKUPS_DIR if not dirpath else os.path.join(dirpath, _BACKUPS_DIR)
    db_file = _DB_FILE if not dirpath else os.path.join(dirpath, _DB_FILE)
    if os.path.exists(db_dir):
        if os.path.exists(bu_dir) and os.path.exists(db_file):
            return Failure('Database already exists')
        return Failure('Database directory exists')
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(db_dir, dir_mode)
        os.mkdir(bu_dir, dir_mode)
        db_obj = _DataBase(description, None)
        fobj = open(db_file, 'wb', stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        try:
            cPickle.dump(db_obj, fobj)
        finally:
            fobj.close()
    except OSError as edata:
        rollback()
        return Failure(edata.strerror)
    except Exception:
        rollback()
        raise
    return True

def load_db(lock=True):
    '''Load the database for access (read only unless lock is True)'''
    global _DB
    assert exists()
    assert not is_readable()
    if lock:
        try:
            lf_fd = os.open(_DB_LOCK_FILE, os.O_WRONLY|os.O_EXCL|os.O_CREAT, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        except OSError as edata:
            return Failure('%s: %s' % (_DB_LOCK_FILE, edata.strerror))
        if lf_fd == -1:
            return Failure('%s: Unable to open' % _DB_LOCK_FILE)
        os.write(lf_fd, str(os.getpid()))
        os.close(lf_fd)
    fobj = open(_DB_FILE, 'rb')
    try:
        _DB = cPickle.load(fobj)
    except Exception:
        # Just in case higher level code catches and handles
        _DB = None
        raise
    finally:
        fobj.close()
    return True

def dump_db():
    '''Dump in memory database to file'''
    assert is_writable()
    fobj = open(_DB_FILE, 'wb')
    try:
        cPickle.dump(_DB, fobj)
    except Exception:
        return Failure('Failed to write to database')
    finally:
        fobj.close()
    return True

def release_db():
    '''Release access to the database'''
    assert is_readable()
    global _DB
    writeable = is_writable()
    was_ok = True
    if writeable:
        was_ok = dump_db()
    _DB = None
    if writeable:
        os.remove(_DB_LOCK_FILE)
    return was_ok

def get_patch_series_names():
    '''Get a list of patch names in series order (names only)'''
    assert is_readable()
    return [patch.name for patch in _DB.series]

def get_applied_patch_set():
    '''Get the set of applied patches' names'''
    def isdir(item):
        return os.path.isdir(os.path.join(_BACKUPS_DIR, item))
    return set([item for item in os.listdir(_BACKUPS_DIR) if isdir(item)])

def get_applied_patch_list():
    '''Get an ordered list of applied patch names'''
    assert is_readable()
    applied = list()
    applied_set = get_applied_patch_set()
    if len(applied_set) == 0:
        return []
    for patch in _DB.series:
        if patch.name in applied_set:
            applied.append(patch.name)
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                return applied
    assert False, 'Series/applied patches discrepency'

def _get_patch_index(name):
    '''Get the index in series for the patch with the given name'''
    assert is_readable()
    index = 0
    for patch in _DB.series:
        if patch.name == name:
            return index
        index += 1
    return None

def _get_top_patch_index():
    '''Get the index in series of the top applied patch'''
    assert is_readable()
    applied_set = get_applied_patch_set()
    if len(applied_set) == 0:
        return None
    index = 0
    for patch in _DB.series:
        if patch.name in applied_set:
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                return index
        index += 1
    return None

def patch_is_in_series(name):
    return _get_patch_index(name) is not None

def is_applied(name):
    return os.path.isdir(os.path.join(_BACKUPS_DIR, name))

def is_top_applied_patch(name):
    top_index = _get_top_patch_index()
    if top_index is None:
        return False
    return _DB.series[top_index].name == name

def _insert_patch(patch, after=None):
    '''Insert a patch into series after the top or nominated patch'''
    assert is_writable()
    assert _get_patch_index(patch.name) is None
    assert after is None or _get_patch_index(after) is not None
    if after is not None:
        assert not is_applied(after) or is_top_applied_patch(after)
        index = _get_patch_index(after) + 1
    else:
        top_index = _get_top_patch_index()
        index = top_index + 1 if top_index is not None else 0
    _DB.series.insert(index, patch)
    return dump_db()

def patch_needs_refresh(name):
    '''Does the named patch need to be refreshed?'''
    assert is_readable()
    assert _get_patch_index(name) is not None
    return False

def create_new_patch(name, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    assert is_writable()
    assert _get_patch_index(name) is None
    patch = _PatchData(name, description)
    return _insert_patch(patch)

def duplicate_patch(name, newname, newdescription):
    '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
    assert is_writable()
    assert _get_patch_index(newname) is None
    assert _get_patch_index(name) is not None and not patch_needs_refresh(name)
    patch = _DB.series[_get_patch_index(name)]
    newpatch = copy.deepcopy(patch)
    newpatch.name = newname
    newpatch.description = newdescription
    return _insert_patch(newpatch)

def remove_patch(name, keep=True):
    '''Remove the named patch from series and (optionally) keep it for later restoration'''
    assert is_writable()
    assert _get_patch_index(name) is not None
    assert not is_applied(name)
    patch = _DB.series[_get_patch_index(name)]
    if keep:
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    return dump_db()

def restore_patch(name, newname=None):
    '''Restore a previously removed patch to the series (after the top patch)'''
    assert is_writable()
    assert newname is None or _get_patch_index(newname) is None
    assert newname is not None or _get_patch_index(name) is None
    assert name in _DB.kept_patches
    patch = _DB.kept_patches[name]
    if newname is not None:
        patch.name = newname
    is_ok = _insert_patch(patch)
    if is_ok:
        del _DB.kept_patches[name]
        is_ok = dump_db()
    return is_ok

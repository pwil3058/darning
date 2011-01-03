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
import shutil
import atexit

from darning import scm_ifce
from darning import runext
from darning import utils

class Failure:
    '''Report failure'''
    def __init__(self, msg):
        self._bool = False
        self.msg = msg
    def __bool__(self):
        return self._bool
    def __nonzero__(self):
        return self._bool
    def __str__(self):
        return self.msg
    def __repr__(self):
        return 'Failure(%s)' % self.msg

class _FileData:
    '''Change data for a single file'''
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
    def needs_refresh(self):
        '''Does this file need a refresh? (Given that it is not overshadowed.)'''
        if os.path.exists(self.name):
            return self.timestamp < os.path.getmtime(self.name) or self.deleted
        else:
            return not self.deleted

OverlapData = collections.namedtuple('OverlapData', ['unrefreshed', 'uncommitted'])

class _PatchData:
    '''Store data for changes to a number of files as a single patch'''
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.files = dict()
        self.pos_guards = set()
        self.neg_guards = set()
        self.scm_revision = None
    def do_add_file(self, filename):
        '''Add the named file to this patch'''
        assert is_writable()
        assert filename not in self.files
        if not self.is_applied():
            # not much to do here
            self.files[filename] = _FileData(filename)
            return dump_db()
        overlaps = self.get_overlap_data([filename])
        assert len(overlaps.unrefreshed) + len(overlaps.uncommitted) == 0
        self.files[filename] = _FileData(filename)
        overlapped_by = self.get_overlapping_patch_for_file(filename)
        if overlapped_by is None:
            self.do_back_up_file(filename)
        else:
            overlapping_backup = overlapped_by.get_backup_file_name(filename)
            if os.path.exists(overlapping_backup):
                os.link(overlapping_backup, self.get_backup_file_name(filename))
                self.files[filename].old_mode = overlapped_by.files[filename].old_mode
            else:
                self.files[filename].old_mode = None
        return dump_db()
    def do_back_up_file(self, filename):
        '''Back up the named file for this patch'''
        assert is_writable()
        assert filename in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filename) is None
        if os.path.exists(filename):
            bu_f_name = self.get_backup_file_name(filename)
            # We need this so that we need to reset it on pop
            old_mode = os.stat(filename).st_mode
            # We'll try to preserve links when we pop patches
            # so we move the file to the backups directory and then make
            # a copy (without links) in the working directory
            shutil.move(filename, bu_f_name)
            shutil.copy2(bu_f_name, filename)
            # Make the backup read only to prevent accidental change
            os.chmod(bu_f_name, utils.turn_off_write(old_mode))
            self.files[filename].old_mode = old_mode
        else:
            self.files[filename].old_mode = None
    def do_refresh_file(self, filename):
        '''Refresh the named file in this patch'''
        assert is_writable()
        assert filename in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filename) is None
        bu_f_name = os.path.join(_BACKUPS_DIR, self.name, filename)
        file_data = self.files[filename]
        if os.path.exists(filename):
            # Do a check for unresolved merges here
            if False:
                file_data.deleted = False
                file_data.timestamp = 0
                result = runext.Result(3, '', 'File has unresolved merge(s).\n')
            if os.path.exists(bu_f_name):
                pass
            else:
                pass
            stat_data = os.stat(filename)
            curr_mode = stat_data.st_mode
            timestamp = stat_data.st_mtime
            deleted = False
            # TODO: finish this
        elif os.path.exists(bu_f_name):
            curr_mode = None
            timestamp = 0
            deleted = True
            # TODO: finish this
        else:
            file_data.diff = ''
            file_data.new_mode = None
            file_data.timestamp = 0
            file_data.scm_revision = scm_ifce.get_revision(filename=file_data.name)
            file_data.deleted = True
            result = runext.Result(0, '', 'File does not exist\n')
        dump_db()
        return result
    def do_unapply(self):
        '''Unapply this patch'''
        assert is_writable()
        assert self.is_applied()
        assert not self.needs_refresh()
        assert not self.is_overlapped()
        for file_data in self.files.values():
            if os.path.exists(file_data.name):
                os.remove(file_data.name)
            bu_f_name = self.get_backup_file_name(file_data.name)
            if os.path.exists(bu_f_name):
                os.chmod(bu_f_name, file_data.old_mode)
                shutil.move(bu_f_name, file_data.name)
        shutil.rmtree(self.get_backup_dir_name())
        return True
    def do_refresh(self):
        '''Refresh the patch'''
        assert is_writable()
        assert self.is_applied()
        results = {}
        for filename in self.files:
            results[filename] = self.do_refresh_file(filename)
        return results
    def get_backup_dir_name(self):
        '''Return the name of the backup directory for this patch'''
        return os.path.join(_BACKUPS_DIR, self.name)
    def get_backup_file_name(self, filename):
        '''Return the name of the backup directory for the named file in this patch'''
        return os.path.join(_BACKUPS_DIR, self.name, filename)
    def get_filenames(self, filenames=None):
        '''
        Return the names of the files in this patch.
        If filenames is not None restrict the returned list to names that
        are also in filenames.
        '''
        if filenames is None:
            return [filename for filename in self.files]
        else:
            return [filename for filename in self.files if filename in filenames]
    def get_file_names_set(self, filenames=None):
        '''Return the set of names for the files in this patch.
        If filenames is not None restrict the returned set to names that
        are also in filenames.
        '''
        return set(self.get_filenames(filenames=filenames))
    def get_overlapping_patch_for_file(self, filename):
        '''Return the patch (if any) which overlaps the named file in this patch'''
        assert is_readable()
        assert self.is_applied()
        after = False
        for apatch in get_applied_patch_list():
            if after:
                if filename in apatch.files:
                    return apatch
            else:
                after = apatch.name == self.name
        return None
    def get_overlap_data(self, filenames=None):
        '''
        Get the data detailing unrefreshed/uncommitted files that will be
        overlapped by this patch
        '''
        assert is_readable()
        data = OverlapData(unrefreshed = {}, uncommitted = [])
        applied_patches = get_applied_patch_list()
        try:
            patch_index = applied_patches.index(self)
            applied_patches = applied_patches[:patch_index]
        except ValueError:
            pass
        if filenames is None:
            filenames = [name for name in self.files]
        for filename in filenames:
            in_patch = False
            for applied_patch in reversed(applied_patches):
                apfile = applied_patch.files.get(filename, None)
                if apfile is not None:
                    in_patch = True
                    if apfile.needs_refresh():
                        data.unrefreshed[filename] = applied_patch.name
                    break
            if not in_patch and scm_ifce.has_uncommitted_change(filename):
                data.uncommited.append(filename)
        return data
    def is_applied(self):
        '''Is this patch applied?'''
        return os.path.isdir(self.get_backup_dir_name())
    def is_blocked_by_guard(self):
        '''Is the this patch blocked from being applied by any guards?'''
        if (self.pos_guards & _DB.selected_guards) != self.pos_guards:
            return True
        if len(self.neg_guards & _DB.selected_guards) != 0:
            return True
        return False
    def is_overlapped(self):
        '''Are any files in this patch overlapped by applied patches?'''
        for filename in self.files:
            if self.get_overlapping_patch_for_file(filename) is not None:
                return True
        return False
    def is_pushable(self):
        '''Is this patch pushable?'''
        return not self.is_applied() and not self.is_blocked_by_guard()
    def needs_refresh(self):
        '''Does this patch need a refresh?'''
        for file_data in self.files.values():
            if file_data.needs_refresh():
                return True
        return False

class _DataBase:
    '''Storage for an ordered sequence/series of patches'''
    def __init__(self, description, host_scm=None):
        self.description = description
        self.selected_guards = set()
        self.series = list()
        self.kept_patches = dict()
        self.host_scm = host_scm
    def get_series_index(self, name):
        '''Get the series index for the patch with the given name'''
        assert is_readable()
        index = 0
        for patch in self.series:
            if patch.name == name:
                return index
            index += 1
        return None
    def get_patch(self, name):
        '''Get the patch with the given name'''
        assert is_readable()
        patch_index = self.get_series_index(name)
        if patch_index is not None:
            return self.series[patch_index]
        else:
            return None

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
    '''Does the current directory contain a patch database?'''
    return os.path.isfile(_DB_FILE)

def is_readable():
    '''Is the database open for reading?'''
    return exists() and _DB is not None

def is_writable():
    '''Is the databas modifiable?'''
    if not is_readable():
        return False
    try:
        lock_pid = open(_DB_LOCK_FILE).read()
    except IOError:
        lock_pid = False
    return lock_pid and lock_pid == str(os.getpid())

def create_db(description, dirpath=None):
    '''Create a patch database in the current directory?'''
    def rollback():
        '''Undo steps that were completed before failure occured'''
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

def release_db():
    '''Release access to the database'''
    assert is_readable()
    global _DB
    writeable = is_writable()
    _DB = None
    if writeable:
        os.remove(_DB_LOCK_FILE)

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
    atexit.register(release_db)
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

def get_patch_series_names():
    '''Get a list of patch names in series order (names only)'''
    assert is_readable()
    return [patch.name for patch in _DB.series]

def _get_applied_patch_names_set():
    '''Get the set of applied patches' names'''
    def isdir(item):
        '''Is item a directory?'''
        return os.path.isdir(os.path.join(_BACKUPS_DIR, item))
    return set([item for item in os.listdir(_BACKUPS_DIR) if isdir(item)])

def get_applied_patch_name_list():
    '''Get an ordered list of applied patch names'''
    assert is_readable()
    applied = list()
    applied_set = _get_applied_patch_names_set()
    if len(applied_set) == 0:
        return []
    for patch in _DB.series:
        if patch.name in applied_set:
            applied.append(patch.name)
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                return applied
    assert False, 'Series/applied patches discrepency'

def get_applied_patch_list():
    '''Get an ordered list of applied patch names'''
    assert is_readable()
    applied = list()
    applied_set = _get_applied_patch_names_set()
    if len(applied_set) == 0:
        return []
    for patch in _DB.series:
        if patch.name in applied_set:
            applied.append(patch)
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                return applied
    assert False, 'Series/applied patches discrepency'

def get_patch_series_index(name):
    '''Get the index in series for the patch with the given name'''
    assert is_readable()
    return _DB.get_series_index(name)

def _get_top_patch_index():
    '''Get the index in series of the top applied patch'''
    assert is_readable()
    applied_set = _get_applied_patch_names_set()
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
    '''Is there a patch with the given name in the series?'''
    return get_patch_series_index(name) is not None

def is_applied(name):
    '''Is the named patch currently applied?'''
    return _DB.get_patch(name).is_applied()

def is_top_applied_patch(name):
    '''Is the named patch the top applied patch?'''
    top_index = _get_top_patch_index()
    if top_index is None:
        return False
    return _DB.series[top_index].name == name

def _insert_patch(patch, after=None):
    '''Insert a patch into series after the top or nominated patch'''
    assert is_writable()
    assert get_patch_series_index(patch.name) is None
    assert after is None or get_patch_series_index(after) is not None
    if after is not None:
        assert not is_applied(after) or is_top_applied_patch(after)
        index = get_patch_series_index(after) + 1
    else:
        top_index = _get_top_patch_index()
        index = top_index + 1 if top_index is not None else 0
    _DB.series.insert(index, patch)
    return dump_db()

def patch_needs_refresh(name):
    '''Does the named patch need to be refreshed?'''
    assert is_readable()
    assert get_patch_series_index(name) is not None
    return _DB.get_patch(name).needs_refresh()

def create_new_patch(name, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(name) is None
    patch = _PatchData(name, description)
    return _insert_patch(patch)

def duplicate_patch(name, newname, newdescription):
    '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(newname) is None
    assert get_patch_series_index(name) is not None and not patch_needs_refresh(name)
    patch = _DB.series[get_patch_series_index(name)]
    newpatch = copy.deepcopy(patch)
    newpatch.name = newname
    newpatch.description = newdescription
    return _insert_patch(newpatch)

def remove_patch(name, keep=True):
    '''Remove the named patch from series and (optionally) keep it for later restoration'''
    assert is_writable()
    assert get_patch_series_index(name) is not None
    assert not is_applied(name)
    patch = _DB.series[get_patch_series_index(name)]
    if keep:
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    return dump_db()

def restore_patch(name, newname=None):
    '''Restore a previously removed patch to the series (after the top patch)'''
    assert is_writable()
    assert newname is None or get_patch_series_index(newname) is None
    assert newname is not None or get_patch_series_index(name) is None
    assert name in _DB.kept_patches
    patch = _DB.kept_patches[name]
    if newname is not None:
        patch.name = newname
    is_ok = _insert_patch(patch)
    if is_ok:
        del _DB.kept_patches[name]
        is_ok = dump_db()
    return is_ok

def top_patch_needs_refresh():
    '''Does the top applied patch need a refresh?'''
    assert is_readable()
    top = _get_top_patch_index()
    if top is not None:
        for file_data in _DB.series[top].files.values():
            if file_data.needs_refresh():
                return True
    return False

def _get_next_patch_index():
    '''Get the next patch to be applied'''
    assert is_readable()
    top = _get_top_patch_index()
    index = 0 if top is None else top + 1
    while index < len(_DB.series):
        patch = _DB.series[index]
        if patch.is_blocked_by_guard():
            continue
        return index
    return None

def get_patch_overlap_data(name, filenames=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the named patch's current files if filenames is None
    or otherwise for the named files (regardless of whether they are in
    the patch).
    '''
    assert is_readable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    return _DB.series[patch_index].get_overlap_data(filenames)

def get_next_patch_overlap_data():
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the nextpatch
    '''
    assert is_readable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return OverlapData(unrefreshed = {}, uncommitted = [])
    return _DB.series[next_index].get_overlap_data()

def apply_patch():
    '''Apply the next patch in the series'''
    def total_len(overlap_data):
        '''Total number of overlaps'''
        count = 0
        for item in overlap_data:
            count += len(item)
        return count
    assert is_writable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return (False, 'There are no pushable patches available')
    next_patch = _DB.series[next_index]
    assert total_len(next_patch.get_overlap_data()) == 0
    os.mkdir(os.path.join(_BACKUPS_DIR, next_patch.name))
    results = {}
    if len(next_patch.files) == 0:
        return (True, results)
    patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch', '--silent']
    for file_data in next_patch.files.values():
        next_patch.do_back_up_file(file_data.name)
        if file_data.diff:
            results[file_data.name] = runext.run_cmd(patch_cmd, file_data.diff)
        if os.path.exists(file_data.name) and file_data.new_mode is not None:
            os.chmod(file_data.name, file_data.new_mode)
    return (dump_db(), results)

def get_top_patch_name():
    '''Return the name of the top applied patch'''
    assert is_readable()
    top = _get_top_patch_index()
    return None if top is None else _DB.series[top].name

def is_blocked_by_guard(name):
    '''Is the named patch blocked from being applied by any guards?'''
    assert is_readable()
    assert get_patch_series_index(name) is not None
    return _DB.get_patch(name).is_blocked_by_guard()

def is_pushable():
    '''Is there a pushable patch?'''
    assert is_readable()
    return _get_next_patch_index() is not None

def is_patch_pushable(name):
    '''Is the named patch pushable?'''
    assert is_readable()
    return _DB.get_patch(name).is_pushable()

def unapply_top_patch():
    '''Unapply the top applied patch'''
    assert is_writable()
    assert not top_patch_needs_refresh()
    top_patch_index = _get_top_patch_index()
    assert top_patch_index is not None
    return _DB.series[top_patch_index].do_unapply()

def get_filenames_in_patch(name, filenames=None):
    '''
    Return the names of the files in the named patch.
    If filenames is not None restrict the returned list to names that
    are also in filenames.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    return _DB.series[patch_index].get_filenames(filenames)

def add_file_to_patch(name, filename):
    '''Add the named file to the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filename not in patch.files
    return patch.do_add_file(filename)

def do_refresh_patch(name):
    '''Refresh the named patch'''
    assert is_writable()
    assert is_applied(name)
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    results = {}
    for filename in patch.files:
        results[filename] = patch.do_refresh_file(filename)
    return results

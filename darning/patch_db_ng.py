### Copyright (C) 2015 Peter Williams <peter_ono@users.sourceforge.net>
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
Implement a patch stack management database
'''

import os
import stat
import cPickle
import collections

from contextlib import contextmanager

from .cmd_result import CmdResult

from . import rctx as RCTX
from . import utils
from . import mixins

from .pm_ifce import PatchState
from .patch_db import _O_IP_PAIR, _O_IP_S_TRIPLET, Failure, _tidy_text

_DIR_PATH = ".darning.dbd"
_BLOBS_DIR_PATH = os.path.join(_DIR_PATH, "blobs")
_RETAINED_PATCHES_DIR_PATH = os.path.join(_DIR_PATH, "retained_patches")
_PATCHES_DATA_FILE_PATH = os.path.join(_DIR_PATH, "patches_data")
_BLOB_REF_COUNT_FILE_PATH = os.path.join(_DIR_PATH, "blob_ref_counts")
_DESCRIPTION_FILE_PATH = os.path.join(_DIR_PATH, "description")
_LOCK_FILE_PATH = os.path.join(_DIR_PATH, "lock_db_ng")

_SUB_DIR = None

def rel_subdir(file_path):
    return file_path if _SUB_DIR is None else os.path.relpath(file_path, _SUB_DIR)

def rel_basedir(file_path):
    if os.path.isabs(file_path):
        file_path = os.path.relpath(file_path)
    elif _SUB_DIR is not None:
        file_path = os.path.join(_SUB_DIR, file_path)
    return file_path

# Probably don't need this but hold on to it for the time being
#def prepend_subdir(file_paths):
    #for findex in range(len(file_paths)):
        #file_paths[findex] = rel_basedir(file_paths[findex])
    #return file_paths

def iter_prepending_subdir(file_paths):
    if _SUB_DIR is None:
        for file_path in file_paths:
            yield file_path
    else:
        for file_path in file_paths:
            yield rel_basedir(file_path)

def find_base_dir(dir_path=None, remember_sub_dir=False):
    '''Find the nearest directory above that contains a database'''
    global _SUB_DIR
    dir_path = os.getcwd() if dir_path is None else os.path.abspath(os.path.expanduser(dir_path))
    subdir_parts = []
    while True:
        # NB: we look for the lock file to distinguish from legacy playgrounds
        if os.path.isfile(os.path.join(dir_path, _LOCK_FILE_PATH)):
            _SUB_DIR = None if not subdir_parts else os.path.join(*subdir_parts)
            return dir_path
        else:
            dir_path, basename = os.path.split(dir_path)
            if not basename:
                break
            if remember_sub_dir:
                subdir_parts.insert(0, basename)
    return None

class PickleExtensibleObject(object):
    '''A base class for pickleable objects that can cope with modifications'''
    RENAMES = dict()
    NEW_FIELDS = dict()
    def __setstate__(self, state):
        self.__dict__ = state
        for old_field in self.RENAMES:
            if old_field in self.__dict__:
                self.__dict__[self.RENAMES[old_field]] = self.__dict__.pop(old_field)
    def __getstate__(self):
        return self.__dict__
    def __getattr__(self, attr):
        if attr in self.NEW_FIELDS:
            return self.NEW_FIELDS[attr]
        raise AttributeError(attr)

class _DataBaseData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("selected_guards", "patch_series_data", "applied_patches_data", "combined_patch_stack")
    def __init__(self, description):
        self.selected_guards = set()
        self.patch_series_data = list()
        self.applied_patches_data = list()
        self.combined_patch_stack = list()

class _PatchData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("name", "description", "files_data", "pos_guards", "neg_guards")
    def __init__(self, name, description=None):
        self.name = name
        self.description = _tidy_text(description) if description else ""
        self.files_data = dict()
        self.pos_guards = set()
        self.neg_guards = set()

class DarnIt(Exception): pass
class DarnItPatchError(Exception): pass
class DarnItPatchExists(DarnItPatchError): pass
class DarnItPatchIsApplied(DarnItPatchError): pass
class DarnItNoPatchesApplied(DarnItPatchError): pass
class DarnItPatchNeedsRefresh(DarnItPatchError): pass

def _find_named_patch_in_list(patch_list, patch_name):
    for index, patch in enumerate(patch_list):
        if patch.name == patch_name:
            return (index, patch)
    return (None, None)

def _named_patch_is_in_list(patch_list, patch_name):
    for patch in patch_list:
        if patch.name == patch_name:
            return True
    return False

def _guards_block_patch(guards, patch):
    if guards:
        if patch.pos_guards and not patch.pos_guards & guards:
            return True
        elif patch.neg_guards & guards:
            return True
    return False

_PTR = collections.namedtuple("_PTR", ["name", "state", "pos_guards", "neg_guards"])

class File(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = []
    WRAPPED_OBJECT_NAME = "_file_data"
    needs_refresh = True
    def __init__(self, file_data):
        self._file_data = file_data

class Patch(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _PatchData.__slots__
    WRAPPED_OBJECT_NAME = "_patch_data"
    def __init__(self, patch_data, data_base):
        self._patch_data = patch_data
        self._data_base = data_base
    @property
    def is_applied(self):
        return self._patch_data in self._data_base.applied_patches_data
    @property
    def is_top_patch(self):
        return self._patch_data is self._data_base.top_patch
    @property
    def needs_refresh(self):
        for pfile in self.iterate_files():
            if pfile.needs_refresh:
                return True
        return False
    @property
    def state(self):
        if not self.is_applied:
            return PatchState.NOT_APPLIED
        elif self.needs_refresh:
            return PatchState.APPLIED_NEEDS_REFRESH
            #PatchState.APPLIED_UNREFRESHABLE self.has_unresolved_merges else
        else:
            return PatchState.APPLIED_REFRESHED
    def iterate_files(self):
        return []
    def iterate_overlying_patches(self):
        applied_index = self._data_base.applied_patches_data.index(self._patch_data)
        return self._data_base.iterate_applied_patches(start=applied_index + 1)
    def get_table_row(self):
        return _PTR(self.name, self.state, self.pos_guards, self.neg_guards)
    def undo_apply(self):
        for file_path, file_data in self.files_data.iteritems():
            if file_data.orig is None:
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue
            dir_path = os.path.dirpath(file_path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            # TODO: add special handling for restoring deleted soft links on pop
            orig_content = self._data_base.get_content_for_hash(file_data.orig.git_hash)
            open(file_path, "w").write(orig_content)
            os.chmod(file_path, file_data.orig.mode)

class DataBase(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _DataBaseData.__slots__
    WRAPPED_OBJECT_NAME = "_PPD"
    def __init__(self, patches_persistent_data, blob_ref_counts, is_writable):
        self._PPD = patches_persistent_data
        self.blob_ref_counts = blob_ref_counts
        self.is_writable = is_writable
    @property
    def top_patch(self):
        return None if not self._PPD.applied_patches_data else Patch(self._PPD.applied_patches_data[-1], self)
    @property
    def top_patch_name(self):
        return None if not self._PPD.applied_patches_data else self._PPD.applied_patches_data[-1].name
    @property
    def base_patch(self):
        return None if not self._PPD.applied_patches_data else Patch(self._PPD.applied_patches_data[0], self)
    @property
    def base_patch_name(self):
        return None if not self._PPD.applied_patches_data else self._PPD.applied_patches_data[0].name
    @property
    def prev_patch(self):
        return None if len(self._PPD.applied_patches_data) < 2 else PathcMgr(self._PPD.applied_patches_data[-2], self)
    @property
    def prev_patch_name(self):
        return None if len(self._PPD.applied_patches_data) < 2 else self._PPD.applied_patches_data[-2].name
    def _next_patch_data(self):
        if self._PPD.applied_patches_data:
            top_patch_index = self._PPD.patch_series_data.index(self._PPD.applied_patches_data[-1])
            for patch in self._PPD.patch_series_data[top_patch_index + 1:]:
                if not _guards_block_patch(self._PPD.guards, patch):
                    return patch
        else:
            for patch in self._PPD.patch_series_data:
                if not _guards_block_patch(self._PPD.guards, patch):
                    return patch
        return None
    @property
    def next_patch(self):
        next_patch_data = self._next_patch_data()
        return Patch(next_patch_data, self) if next_patch_data else None
    @property
    def next_patch_name(self):
        next_patch_data = self._next_patch_data()
        return next_patch_data.name if next_patch_data else None
    def create_new_patch(self, patch_name, description):
        assert self.is_writable
        if _named_patch_is_in_list(self._PPD.patch_series_data, patch_name):
            raise DarnItPatchExists(patch_name)
        new_patch = _PatchData(patch_name, description)
        if self._PPD.applied_patches_data:
            top_patch_index = self._PPD.patch_series_data.index(self._PPD.applied_patches_data[-1])
            self._PPD.patch_series_data.insert(top_patch_index + 1, new_patch)
        else:
            self._PPD.patch_series_data.insert(0, new_patch)
        self._PPD.applied_patches_data.append(new_patch)
        return Patch(new_patch, self)
    def remove_patch(self, patch):
        assert self.is_writable
        if patch._patch_data in self._PPD.applied_patches_data:
            raise DarnItPatchIsApplied(patch._patch_data.name)
        self._PPD.patch_series_data.remove(patch._patch_data)
    def get_named_patch(self, patch_name):
        _index, patch = _find_named_patch_in_list(self._PPD.patch_series_data, patch_name)
        if not patch:
            raise DarnItUnknownPatch(patch_name)
        return Patch(patch, self)
    def iterate_applied_patches(self, start=0):
        return (Patch(patch_data, self) for patch_data in self.applied_patches_data[start:])
    def iterate_series(self, start=0):
        return (Patch(patch_data, self) for patch_data in self.patch_series_data[start:])
    def pop_top_patch(self, force=False):
        assert self.is_writable
        if not self.applied_patches_data:
            raise DarnItNoPatchesApplied()
        if not force and self.top_patch.needs_refresh:
            raise DarnItPatchNeedsRefresh(self.top_patch_name)
        self.top_patch.undo_apply()
        self.applied_patches_data.pop()
        return self.top_patch

def do_create_db(dir_path=None, description=None):
    '''Create a patch database in the current directory?'''
    def rollback():
        '''Undo steps that were completed before failure occured'''
        for filnm in [patches_data_file_path, database_lock_file_path, blob_ref_count_file_path, description_file_path]:
            if os.path.exists(filnm):
                os.remove(filnm)
        for dirnm in [database_blobs_dir_path, retained_patches_dir_path, database_dir_path]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    if not dir_path:
        dir_path = os.getcwd()
    root = find_base_dir(dir_path=dir_path, remember_sub_dir=False)
    if root is not None:
        RCTX.stderr.write(_("Inside existing playground: \"{0}\".\n").format(os.path.relpath(root)))
        return CmdResult.ERROR
    database_dir_path = os.path.join(dir_path, _DIR_PATH)
    database_blobs_dir_path = os.path.join(dir_path, _BLOBS_DIR_PATH)
    retained_patches_dir_path = os.path.join(dir_path, _RETAINED_PATCHES_DIR_PATH)
    patches_data_file_path = os.path.join(dir_path, _PATCHES_DATA_FILE_PATH)
    blob_ref_count_file_path = os.path.join(dir_path, _BLOB_REF_COUNT_FILE_PATH)
    description_file_path = os.path.join(dir_path, _DESCRIPTION_FILE_PATH)
    if os.path.exists(database_dir_path):
        if os.path.exists(database_blobs_dir_path) and os.path.exists(patches_data_file_path):
            RCTX.stderr.write(_("Database already exists.\n"))
        else:
            RCTX.stderr.write(_("Database directory exists.\n"))
        return CmdResult.ERROR
    database_lock_file_path = os.path.join(dir_path, _LOCK_FILE_PATH)
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(database_dir_path, dir_mode)
        os.mkdir(database_blobs_dir_path, dir_mode)
        os.mkdir(retained_patches_dir_path, dir_mode)
        open(database_lock_file_path, "wb").write("0")
        open(description_file_path, "w").write(_tidy_text(description) if description else "")
        db_obj = _DataBaseData(description)
        fobj = open(patches_data_file_path, "wb", stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        try:
            cPickle.dump(db_obj, fobj)
        finally:
            fobj.close()
        fobj = open(blob_ref_count_file_path, "wb", stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        try:
            cPickle.dump(dict(), fobj)
        finally:
            fobj.close()
    except OSError as edata:
        rollback()
        RCTX.stderr.write(edata.strerror)
        return CmdResult.ERROR
    except Exception:
        rollback()
        raise
    return CmdResult.OK

# Make a context manager for locking/opening/closing database
@contextmanager
def open_db(mutable=False):
    import fcntl
    fd = os.open(_LOCK_FILE_PATH, os.O_RDWR if mutable else os.O_RDONLY)
    fcntl.lockf(fd, fcntl.LOCK_EX if mutable else fcntl.LOCK_SH)
    patches_data = cPickle.load(open(_PATCHES_DATA_FILE_PATH, "rb"))
    blob_ref_counts = cPickle.load(open(_BLOB_REF_COUNT_FILE_PATH, "rb"))
    try:
        yield DataBase(patches_data, blob_ref_counts, mutable)
    finally:
        if mutable:
            scount = os.read(fd, 255)
            os.lseek(fd, 0, 0)
            os.write(fd, str(int(scount) + 1))
            cPickle.dump(patches_data, open(_PATCHES_DATA_FILE_PATH, "wb"))
            cPickle.dump(blob_ref_counts, open(_BLOB_REF_COUNT_FILE_PATH, "wb"))
        fcntl.lockf(fd, fcntl.LOCK_UN)
        os.close(fd)

### Helper commands

### Main interface commands start here

### DOs

def do_create_new_patch(patch_name, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    with open_db(mutable=True) as DB:
        old_top = DB.top_patch
        try:
            patch = DB.create_new_patch(patch_name, description)
        except DarnItPatchExists:
            RCTX.stderr.write(_("patch \"{0}\" already exists.\n").format(patch_name))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        if old_top and old_top.needs_refresh:
            RCTX.stderr.write(_("Previous top patch (\"{0}\") needs refreshing.\n").format(old_top.name))
            return CmdResult.WARNING
        return CmdResult.OK

def do_pop_top_patch(force=False):
    # TODO: implement non dummy version do_unapply_top_patch()
    with open_db(mutable=True) as DB:
        try:
            new_top_patch = DB.pop_top_patch(force=force)
        except DarnItNoPatchesApplied:
            RTX.stderr.write(_("There are no applied patches to pop."))
            return CmdResult.ERROR
        except DarnItPatchNeedsRefresh:
            RCTX.stderr.write(_('Top patch ("{0}") needs to be refreshed.\n').format(DB.top_patch_name))
            return CmdResult.ERROR_SUGGEST_FORCE_OR_REFRESH
        if new_top_patch is None:
            RCTX.stdout.write(_("There are now no patches applied.\n"))
        else:
             RCTX.stdout.write(_("Patch \"{0}\" is now on top.\n").format(new_top_patch.name))
        return CmdResult.OK

def do_unapply_top_patch(force=False):
    return do_pop_top_patch(force=force)

### GETs

def get_patch_table_data():
    with open_db(mutable=False) as DB:
        return [patch.get_table_row() for patch in DB.iterate_series()]

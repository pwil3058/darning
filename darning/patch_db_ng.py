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
import shutil
import copy
import difflib

from contextlib import contextmanager

from .cmd_result import CmdResult

from . import rctx as RCTX
from . import utils
from . import mixins
from . import scm_ifce
from . import fsdb
from . import patchlib

from .pm_ifce import PatchState, FileStatus, Presence, Validity, MERGE_CRE, PatchTableRow, patch_timestamp_str
from .patch_db import _O_IP_PAIR, _O_IP_S_TRIPLET, Failure, _tidy_text
from .patch_db import OverlapData

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

def iter_with_subdir(file_paths):
    if _SUB_DIR is None:
        for file_path in file_paths:
            yield (file_path, file_path)
    else:
        for file_path in file_paths:
            yield (rel_basedir(file_path), file_path)

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

class _DataBaseData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("selected_guards", "patch_series_data", "applied_patches_data", "combined_patch_data")
    def __init__(self, description):
        self.selected_guards = set()
        self.patch_series_data = list()
        self.applied_patches_data = list()
        self.combined_patch_data = None

class _PatchData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("name", "description", "files_data", "pos_guards", "neg_guards")
    def __init__(self, name, description=None):
        self.name = name
        self.description = _tidy_text(description) if description else ""
        self.files_data = dict()
        self.pos_guards = set()
        self.neg_guards = set()

class _CombinedPatchData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("files_data", "prev")
    def __init__(self, prev):
        self.files_data = dict() if not prev else {file_path : copy.copy(files_data) for file_path, files_data in prev.files_data.iteritems()}
        self.prev = prev

class _FileData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("orig", "darned", "came_from", "renamed_as", "diff")
    def __init__(self, orig, darned, came_from=None, renamed_as=None, diff=None):
        self.orig = orig
        self.darned = darned
        self.came_from = came_from
        self.renamed_as = renamed_as
        self.diff = diff

class _CombinedFileData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("top", "bottom")
    def __init__(self, top, bottom):
        self.top = top
        self.bottom = bottom

class _EssentialFileData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("git_hash", "lstats")
    def __init__(self, git_hash, lstats):
        self.git_hash = git_hash
        self.lstats = lstats
    @property
    def mode(self):
        return stat.S_IMODE(self.lstats.st_mode)
    @property
    def timestamp(self):
        return patch_timestamp_str(self.lstats.st_mtime)
    def clone(self):
        return self.__class__(self.git_hash, self.lstats)
    def __eq__(self, other):
        return False if other is None else self.lstats.st_mode == other.lstats.st_mode and self.git_hash == other.git_hash
    def __ne__(self, other):
        return not self.__eq__(other)

class _CameFromData(mixins.PedanticSlotPickleMixin):
    __slots__ = ("file_path", "as_rename")
    def __init__(self, file_path, as_rename):
        self.file_path = file_path
        self.as_rename = as_rename

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

def _content_has_unresolved_merges(content):
    for line in content.splitlines():
        if MERGE_CRE.match(line):
            return True
    return False

def _file_has_unresolved_merges(file_path):
    return _content_has_unresolved_merges(open(file_path, "r").read()) if os.path.exists(file_path) else False

def generate_diff_preamble_lines(file_path, before, after, came_from=None):
    if came_from:
        lines = ["diff --git {0} {1}\n".format(os.path.join("a", came_from.file_path), os.path.join("b", file_path)), ]
    else:
        lines = ["diff --git {0} {1}\n".format(os.path.join("a", file_path), os.path.join("b", file_path)), ]
    if before is None:
        if after is not None:
            lines.append("new file mode {0:07o}\n".format(after.mode))
    elif after is None:
        lines.append("deleted file mode {0:07o}\n".format(before.mode))
    else:
        if before.mode != after.mode:
            lines.append("old mode {0:07o}\n".format(before.mode))
            lines.append("new mode {0:07o}\n".format(after.mode))
    if came_from:
        if came_from.as_rename:
            lines.append("rename from {0}\n".format(came_from.file_path))
            lines.append("rename to {0}\n".format(file_path))
        else:
            lines.append("copy from {0}\n".format(came_from.file_path))
            lines.append("copy to {0}\n".format(file_path))
    hash_line = "index {0}".format(before.git_hash if before.git_hash else "0" *48)
    hash_line += "..{0}".format(after.git_hash if after.git_hash else "0" *48)
    hash_line += " {0:07o}\n".format(after.mode) if before.mode == after.mode else "\n"
    lines.append(hash_line)
    return lines

def generate_diff_preamble(file_path, before, after, came_from=None):
    return patchlib.Preamble.parse_lines(generate_diff_preamble_lines(file_path, before, after, came_from))

def generate_unified_diff_lines(before, after):
    before_lines = before.content.splitlines(True)
    after_lines = after.content.splitlines(True)
    diff_lines = list(difflib.unified_diff(before_lines, after_lines, fromfile=before.label, tofile=after.label, fromfiledate=before.timestamp, tofiledate=after.timestamp))
    if diff_lines and not diff_lines[-1].endswith((os.linesep, "\n")):
        diff_lines[-1] = diff_lines[-1] + "\n"
        diff_lines.append("\ No newline at end of file\n")
    return diff_lines

def generate_unified_diff(before, after):
    return patchlib.Diff.parse_lines(generate_unified_diff_lines(before, after))

_DiffData = collections.namedtuple("_DiffData", ["label", "efd", "content", "timestamp"])

class FileData(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _FileData.__slots__
    WRAPPED_OBJECT_NAME = "persistent_file_data"
    def __init__(self, file_path, persistent_file_data, patch):
        self.path = file_path
        self.persistent_file_data = persistent_file_data
        self.patch = patch
    def __eq__(self, other):
        self.persistent_file_data is other.persistent_file_data
    @classmethod
    def new(cls, file_path, patch, overlaps=OverlapData()):
        # NB: presence of overlaps implies absorb
        orig = patch.database.store_file_content(file_path, overlaps)
        darned = patch.database.clone_stored_content_data(orig)
        #print "NEW({}, {}, {}): -> {}, {}".format(file_path, patch, overlaps, orig, darned)
        return cls(file_path, _FileData(orig=orig, darned=darned), patch)
    @property
    def presence(self):
        if self.orig is None:
            return Presence.ADDED
        elif self.darned is None:
            return Presence.REMOVED
        return Presence.EXTANT
    @property
    def validity(self):
        if not self.patch.is_applied:
            return None
        overlapping_file = self.get_overlapping_file()
        if self._needs_refresh(overlapping_file):
            if self._has_unresolved_merges(overlapping_file):
                return Validity.UNREFRESHABLE
            else:
                return Validity.NEEDS_REFRESH
        else:
            return Validity.REFRESHED
    @property
    def needs_refresh(self):
        if not self.patch.is_applied:
            # None means "undeterminable"
            return None
        return self._needs_refresh(self.get_overlapping_file())
    def _needs_refresh(self, overlapping_file):
        if overlapping_file is None:
            try:
                lstats = os.lstat(self.path)
                if self.darned.lstats.st_mode != lstats.st_mode:
                    return True
                elif self.darned.lstats.st_mtime != lstats.st_mtime:
                    return True
                elif self.darned.lstats.st_size != lstats.st_size:
                    return True
                # NB: using modify time and size instead of comparing hash values
            except OSError:
                return self.darned is not None
        else:
            return self.darned != overlapping_file.orig
        return False
    @property
    def has_unresolved_merges(self):
        if not self.patch.is_applied:
            # None means "undeterminable"
            return None
        return self._has_unresolved_merges(self.get_overlapping_file())
    def _has_unresolved_merges(self, overlapping_file):
        if overlapping_file is None:
            return _file_has_unresolved_merges(self.path)
        else:
            content = self.patch.database.get_content_for(overlapping_file.orig)
            return _content_has_unresolved_merges(content)
    @property
    def related_file_data(self):
        return None # TODO:
    def get_overlapping_file(self):
        for patch in self.patch.iterate_overlying_patches():
            file_data = patch.files_data.get(self.path, None)
            if file_data:
                return FileData(self.path, file_data, patch)
        return None
    def get_table_row(self):
        return fsdb.Data(self.path, FileStatus(self.presence, self.validity), self.related_file_data)
    def get_diff_before_data(self, as_refreshed=False, with_timestamps=False):
        if self.came_from:
            efd = self.patch.get_file(self.came_from.path).orig
            label = os.path.join("a", self.came_from.path)
        else:
            efd = self.orig
            label = os.path.join("a", self.path) if efd else "/dev/null"
        timestamp = efd.timestamp if (with_timestamps and efd) else None
        content = None if as_refreshed else self.patch.database.get_content_for(efd)
        return _DiffData(label, efd, content, timestamp)
    def get_diff_after_data(self, as_refreshed=False, with_timestamps=False):
        if as_refreshed or not self.patch.is_applied:
            efd = self.darned
            label = os.path.join("b", self.path) if efd else "/dev/null"
            content = None
        else:
            overlapping_file = self.get_overlapping_file()
            if overlapping_file is not None:
                efd = overlapping_file.orig
                content = self.patch.database.get_content_for(efd)
            elif os.path.exists(self.path):
                content = open(self.path, "r").read()
                efd = _EssentialFileData(utils.get_git_hash_for_content(content), os.lstat(self.path))
            else:
                efd = None
                content = ""
            label = os.path.join("b", self.path) if efd else "/dev/null"
        timestamp = efd.timestamp if (with_timestamps and efd) else None
        return _DiffData(label, efd, content, timestamp)
    def get_diff_plus(self, as_refreshed=False, with_timestamps=False):
        before = self.get_diff_before_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        after = self.get_diff_after_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        preamble = generate_diff_preamble(self.path, before.efd, after.efd, self.came_from)
        if as_refreshed or (after.efd and self.darned and after.efd.git_hash == self.darned.git_hash):
            diff = copy.deepcopy(self.diff)
        elif before.content.find("\000") != -1 or before.content.find("\000") != -1:
            diff = BinaryDiff(before_content, after_content)
        else:
            diff = generate_unified_diff(before, after)
        diff_plus = patchlib.DiffPlus([preamble], diff)
        if self.renamed_as and self.after is None:
            diff_plus.trailing_junk.append(_("# Renamed to: {0}\n").format(self.renamed_as))
        return diff_plus
    def get_diff_text(self, as_refreshed=False, with_timestamps=False):
        before = self.get_diff_before_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        after = self.get_diff_after_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        preamble = "".join(generate_diff_preamble_lines(self.path, before.efd, after.efd, self.came_from))
        if as_refreshed or (after.efd and self.darned and after.efd.git_hash == self.darned.git_hash):
            diff = "" if self.diff is None else str(copy.deepcopy(self.diff))
        elif before.content.find("\000") != -1 or before.content.find("\000") != -1:
            diff = str(BinaryDiff(before.content, after.content))
        else:
            diff = "".join(generate_unified_diff_lines(before, after))
        trailing_junk = _("# Renamed to: {0}\n").format(self.renamed_as) if self.renamed_as and self.after is None else ""
        return preamble + (diff if diff else "") + trailing_junk

class Patch(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _PatchData.__slots__
    WRAPPED_OBJECT_NAME = "persistent_patch_data"
    def __init__(self, patch_data, database):
        self.persistent_patch_data = patch_data
        self.database = database
        assert patch_data in database.patch_series_data
    def __eq__(self, other):
        self.persistent_patch_data is other.persistent_patch_data
    @property
    def is_applied(self):
        return self.persistent_patch_data in self.database.applied_patches_data
    @property
    def is_top_patch(self):
        return self.persistent_patch_data is self.database.top_patch.persistent_patch_data
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
    def iterate_files(self, file_paths=None):
        if file_paths is None:
            return (FileData(file_path, pfd, self) for file_path, pfd in self.files_data.iteritems())
        else:
            return (FileData(file_path, self.files_data[file_path], self) for file_path in file_paths)
    def iterate_files_sorted(self, file_paths=None):
        if file_paths is None:
            return (FileData(file_path, pfd, self) for file_path, pfd in sorted(self.files_data.iteritems()))
        else:
            return (FileData(file_path, pfd, self) for file_path, pfd in sorted(self.files_data.iteritems()) if file_path in file_paths)
    def iterate_overlying_patches(self):
        applied_index = self.database.applied_patches_data.index(self.persistent_patch_data)
        return self.database.iterate_applied_patches(start=applied_index + 1)
    def get_file(self, file_path):
        return FileData(file_path, self.files_data[file_path], self)
    def get_file_paths_set(self, file_paths=None):
        if file_paths is None:
            return set(self.files_data.iterkeys())
        else:
            return {file_path for file_path in self.files_data.iterkeys() if file_path in file_paths}
    def get_files_table(self):
        return [patch_file.get_table_row() for patch_file in self.iterate_files()]
    def get_table_row(self):
        return PatchTableRow(self.name, self.state, self.pos_guards, self.neg_guards)
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
            orig_content = self.database.get_content_for_hash(file_data.orig.git_hash)
            open(file_path, "w").write(orig_content)
            os.chmod(file_path, file_data.orig.mode)
    def add_file(self, file_data):
        assert not self.is_applied or self.is_top_patch
        assert file_data.path not in self.files_data
        self.files_data[file_data.path] = file_data.persistent_file_data
        if self.is_applied:
            self.database.combined_patch.add_file(file_data)

class CombinedPatch(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _CombinedPatchData.__slots__
    WRAPPED_OBJECT_NAME = "persistent_data"
    def __init__(self, persistent_data):
        self.persistent_data = persistent_data
    def add_file(self, file_data):
        if self.prev:
            prev_file_data = self.prev.files_data.get(file_data.path, None)
            bottom = prev_file_data.bottom if prev_file_data else file_data.persistent_file_data
        else:
            bottom = file_data.persistent_file_data
        self.files_data[file_data.path] = _CombinedFileData(file_data.persistent_file_data, bottom)

class DataBase(mixins.WrapperMixin):
    WRAPPED_ATTRIBUTES = _DataBaseData.__slots__
    WRAPPED_OBJECT_NAME = "_PPD"
    def __init__(self, patches_persistent_data, blob_ref_counts, is_writable):
        self._PPD = patches_persistent_data
        self.blob_ref_counts = blob_ref_counts
        self.is_writable = is_writable
        for patch in patches_persistent_data.applied_patches_data:
            assert patch in patches_persistent_data.patch_series_data
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
    @property
    def combined_patch(self):
        return CombinedPatch(self.combined_patch_data)
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
        assert self._PPD.applied_patches_data[-1] is new_patch
        assert new_patch in self._PPD.patch_series_data
        self._PPD.combined_patch_data = _CombinedPatchData(self._PPD.combined_patch_data)
        return Patch(new_patch, self)
    def remove_patch(self, patch):
        assert self.is_writable
        if patch.persistent_patch_data in self._PPD.applied_patches_data:
            raise DarnItPatchIsApplied(patch.name)
        self._PPD.patch_series_data.remove(patch.persistent_patch_data)
    def get_named_patch(self, patch_name):
        _index, patch = _find_named_patch_in_list(self._PPD.patch_series_data, patch_name)
        if not patch:
            raise DarnItUnknownPatch(patch_name)
        return Patch(patch, self)
    def iterate_applied_patches(self, start=0, stop=None, backwards=False):
        if backwards:
            return (Patch(patch_data, self) for patch_data in reversed(self.applied_patches_data[slice(start, stop)]))
        else:
            return (Patch(patch_data, self) for patch_data in self.applied_patches_data[slice(start, stop)])
    def iterate_series(self, start=0, stop=None):
        return (Patch(patch_data, self) for patch_data in self.patch_series_data[slice(start, stop)])
    def pop_top_patch(self, force=False):
        assert self.is_writable
        if not self.applied_patches_data:
            raise DarnItNoPatchesApplied()
        if not force and self.top_patch.needs_refresh:
            raise DarnItPatchNeedsRefresh(self.top_patch_name)
        self.top_patch.undo_apply()
        self.applied_patches_data.pop()
        self._PPD.combined_patch_data = self._PPD.combined_patch_data.prev
        return self.top_patch
    def get_overlap_data(self, file_paths, patch=None):
        '''
        Get the data detailing unrefreshed/uncommitted files that will be
        overlapped by the files in filelist if they are added to the named
        (or next, if patch_name is None) patch.
        '''
        if not file_paths:
            return OverlapData()
        # NB: let this blow up if index fails
        patch_index = None if patch is None else self.applied_patches_data.index(patch.persistent_patch_data)
        remaining_files = set(file_paths)
        uncommitted = set(scm_ifce.get_ifce().get_files_with_uncommitted_changes(remaining_files))
        unrefreshed = {}
        for patch in self.iterate_applied_patches(stop=patch_index, backwards=True):
            if len(uncommitted) + len(remaining_files) == 0:
                break
            patch_file_paths_set = patch.get_file_paths_set(remaining_files)
            if patch_file_paths_set:
                remaining_files -= patch_file_paths_set
                uncommitted -= patch_file_paths_set
                for patched_file in patch.iterate_files(patch_file_paths_set):
                    if patched_file.needs_refresh:
                        unrefreshed[patched_file.path] = patch
        return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)
    def incr_ref_count_for_hash(self, git_hash):
        try:
            self.blob_ref_counts[git_hash[:2]][git_hash[2:]] += 1
        except KeyError:
            try:
                self.blob_ref_counts[git_hash[:2]][git_hash[2:]] = 1
            except KeyError:
                self.blob_ref_counts[git_hash[:2]] = {git_hash[2:] : 1}
        return self.blob_ref_counts[git_hash[:2]][git_hash[2:]]
    def store_file_content(self, file_path, overlaps=OverlapData()):
        overlapped_patch = overlaps.unrefreshed.get(file_path, None)
        if overlapped_patch:
            return self.clone_stored_content_data(overlapped_patch.get_file(file_path).darned)
        if file_path in overlaps.uncommitted:
            pass # TODO: handle uncommitted overlaps
        elif not os.path.exists(file_path):
            return None
        git_hash = utils.get_git_hash_for_file(file_path)
        if self.incr_ref_count_for_hash(git_hash) == 1:
            blob_dir_path = os.path.join(_BLOBS_DIR_PATH, git_hash[:2])
            if not os.path.exists(blob_dir_path):
                os.mkdir(blob_dir_path)
            shutil.copyfile(file_path, os.path.join(blob_dir_path, git_hash[2:]))
        return _EssentialFileData(git_hash, os.lstat(file_path))
    def clone_stored_content_data(self, content_data):
        if content_data is None:
            return None
        cloned_data = content_data.clone()
        assert self.incr_ref_count_for_hash(cloned_data.git_hash) > 1
        return cloned_data
    @staticmethod
    def get_content_for(obj):
        return "" if obj is None else open(os.path.join(_BLOBS_DIR_PATH, obj.git_hash[:2], obj.git_hash[2:]), "r").read()

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
# The helper commands are wrappers for common functionality in the
# modules exported functions.  They may emit output to stderr and
# should only be used where that is a requirement.  Use DataBase
# methods otherwise.
def _get_patch(patch_name, db):
    '''Return the named patch'''
    try:
        return db.get_named_patch(patch_name)
    except DarnItUnknownPatch:
        RCTX.stderr.write(_('{0}: patch is NOT known.\n').format(patch_name))
        return None

def _get_top_patch(db):
    if db.top_patch is None:
        RCTX.stderr.write(_('No patches applied.\n'))
    return db.top_patch

def _get_named_or_top_patch(patch_name, db):
    '''Return the named or top applied patch'''
    return _get_patch(patch_name, db) if patch_name is not None else _get_top_patch(db)

def _add_files_to_top_patch(DB, file_paths, absorb=False, force=False):
    '''Add the named files to the named patch'''
    assert not (absorb and force)
    top_patch = _get_top_patch(DB)
    if top_patch is None:
        return CmdResult.ERROR
    if not force:
        overlaps = DB.get_overlap_data(iter_prepending_subdir(file_paths), top_patch)
        if not absorb and len(overlaps) > 0:
            return overlaps.report_and_abort()
    else:
        overlaps = OverlapData()
    top_patch_file_paths_set = top_patch.get_file_paths_set()
    issued_warning = False
    for file_path, file_path_rel_subdir in iter_with_subdir(file_paths):
        if file_path in top_patch_file_paths_set:
            RCTX.stderr.write(_('{0}: file already in patch "{1}". Ignored.\n').format(file_path_rel_subdir, top_patch.name))
            issued_warning = True
            continue
        elif os.path.isdir(file_path):
            RCTX.stderr.write(_('{0}: is a directory. Ignored.\n').format(file_path_rel_subdir))
            issued_warning = True
            continue
        top_patch_file_paths_set.add(file_path)
        top_patch.add_file(FileData.new(file_path, top_patch, overlaps=overlaps))
        RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(file_path_rel_subdir, top_patch.name))
        if file_path in overlaps.uncommitted:
            RCTX.stderr.write(_('{0}: Uncommited SCM changes have been incorporated in patch "{1}".\n').format(file_path_rel_subdir, top_patch.name))
        elif file_path in overlaps.unrefreshed:
            RCTX.stderr.write(_('{0}: Unrefeshed changes in patch "{2}" incorporated in patch "{1}".\n').format(file_path_rel_subdir, top_patch.name, overlaps.unrefreshed[file_path].name))
    return CmdResult.WARNING if issued_warning else CmdResult.OK

### Main interface commands start here

### DOs

def do_add_files_to_top_patch(file_paths, absorb=False, force=False):
    with open_db(mutable=True) as DB:
        return _add_files_to_top_patch(DB, file_paths, absorb=absorb, force=force)

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

def get_diff_for_files(file_paths, patch_name, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        patch = _get_named_or_top_patch(patch_name, _DB)
        if patch is None:
            return False
        if file_paths:
            base_file_paths = list(iter_prepending_subdir(file_paths))
            file_paths_set = patch.get_file_paths_set(base_file_paths)
            if len(base_file_paths) != len(file_paths_set):
                for file_path, base_file_path in zip(file_paths, base_file_paths):
                    if base_file_path not in file_path_set:
                        RCTX.stderr.write("{0}: file is not in patch \"{1}\".\n".format(file_path, patch.name))
                return False
            file_iter = patch.iterate_files(file_paths_set)
        else:
            file_iter = patch.iterate_files_sorted()
        diffs = (file_data.get_diff_text(with_timestamps=with_timestamps) for file_data in file_iter)
        return "".join(diffs)

def get_named_or_top_patch_name(patch_name):
    '''Return the name of the named or top patch if patch_name is None or None if patch_name is not a valid patch_name'''
    with open_db(mutable=False) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        return None if patch is None else patch.name

def get_patch_file_table(patch_name=None):
    with open_db(mutable=False) as DB:
        patch = DB.top_patch if patch_name is None else DB.get_named_patch(patch_name)
        return patch.get_files_table()

def get_patch_table_data():
    with open_db(mutable=False) as DB:
        return [patch.get_table_row() for patch in DB.iterate_series()]

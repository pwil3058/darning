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

import os
import hashlib
import runext
import pango
import collections

from . import fsdb
from . import utils
from . import patchlib
from . import quilt_utils

FSTATUS_MODIFIED = ' '
FSTATUS_ADDED = '+'
FSTATUS_REMOVED = '-'
FSTATUS_IGNORED = 'I'

FSTATUS_MODIFIED_SET = set([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED])
FSTATUS_CLEAN_SET = set([FSTATUS_IGNORED, None])

STATUS_DECO_MAP = {
    None: fsdb.Deco(pango.STYLE_NORMAL, 'black'),
    FSTATUS_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, 'blue'),
    FSTATUS_ADDED: fsdb.Deco(pango.STYLE_NORMAL, 'darkgreen'),
    FSTATUS_REMOVED: fsdb.Deco(pango.STYLE_NORMAL, 'red'),
    FSTATUS_IGNORED: fsdb.Deco(pango.STYLE_ITALIC, 'grey'),
}

# Contained File Relative Data
CFRD = collections.namedtuple("CFRD", ["sub_dir_relpath", "name"])
def get_file_path_relative_data(file_path, base_dir_path=None):
    data = CFRD(*os.path.split(os.path.relpath(file_path, os.curdir if base_dir_path is None else base_dir_path)))
    return None if data.sub_dir_relpath.startswith(os.pardir) else data

class WsFileDb(fsdb.GenericSnapshotWsFileDb):
    class FileDir(fsdb.GenericSnapshotWsFileDb.FileDir):
        IGNORED_STATUS_SET = set([FSTATUS_IGNORED])
        CLEAN_STATUS_SET = FSTATUS_CLEAN_SET
        SIGNIFICANT_DATA_SET = FSTATUS_MODIFIED_SET
        def _get_initial_status(self):
            if not os.path.isdir(self._dir_path):
                return FSTATUS_REMOVED
            return FSTATUS_MODIFIED if self._file_status_snapshot.status_set else None
    def _get_file_data_text(self, h):
        result = runext.run_cmd(["quilt", "files", "-va"])
        h.update(result.stdout)
        return result.stdout
    @staticmethod
    def _extract_file_status_snapshot(file_data_text):
        return fsdb.Snapshot({line[2:] : (line[0], None) for line in file_data_text.splitlines() if line[0] in FSTATUS_MODIFIED_SET})

def iterate_quilt_file_data(patch_text):
    if not patch_text:
        return
    for line in patch_text.splitlines():
        yield (line[2:], line[0], None)

PATCHLIB_TO_STATUS_MAP = {
    patchlib.FilePathPlus.ADDED : FSTATUS_ADDED,
    patchlib.FilePathPlus.DELETED: FSTATUS_REMOVED,
    patchlib.FilePathPlus.EXTANT: FSTATUS_MODIFIED
}

def iterate_patchlib_file_data(patch_text):
    if not patch_text:
        return
    for fdata in patchlib.Patch.parse_text(patch_text).iterate_file_paths_plus(1):
        yield (fdata.path, PATCHLIB_TO_STATUS_MAP[fdata.status], fdata.expath)

class TopPatchFileDb(fsdb.GenericChangeFileDb):
    class FileDir(fsdb.GenericChangeFileDb.FileDir):
        CLEAN_STATUS_SET = frozenset([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED])
        def _calculate_status(self):
            if not self._status_set:
                return None
            elif len(self._status_set) > 1:
                return  FSTATUS_MODIFIED
            else:
                return list(self._status_set)[0]
    def __init__(self):
        self._top_patch = self._get_top_patch()
        fsdb.GenericChangeFileDb.__init__(self)
    @staticmethod
    def _get_top_patch():
        result = runext.run_cmd(["quilt", "top"])
        if result.ecode != 0: return None # we're not in a repo so no patches
        return result.stdout
    @property
    def is_current(self):
        if self._get_top_patch() != self._top_patch:
            # somebody's popped or pushed externally
            return False
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_patch_data_text(self, h):
        if self._top_patch is None:
            return ("", "")
        patch_status_text = runext.run_cmd(["quilt", "files", "-v"]).stdout
        h.update(patch_status_text)
        return (patch_status_text)
    @staticmethod
    def _iterate_file_data(pdt):
        return iterate_quilt_file_data(pdt)

class PatchFileDb(fsdb.GenericChangeFileDb):
    FileDir = TopPatchFileDb.FileDir
    def __init__(self, patch_name):
        self._patch_name = patch_name
        self._is_applied = quilt_utils.is_patch_applied(self._patch_name)
        self._patch_file_path = quilt_utils.get_patch_file_path(self._patch_name)
        fsdb.GenericChangeFileDb.__init__(self)
    @property
    def is_current(self):
        if quilt_utils.is_patch_applied(self._patch_name) != self._is_applied:
            # somebody's popped or pushed externally
            return False
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_patch_data_text(self, h):
        if self._is_applied:
            patch_status_text = runext.run_cmd(["quilt", "files", "-v", self._patch_name]).stdout
        else:
            patch_status_text = utils.get_file_contents(self._patch_file_path)
        h.update(patch_status_text)
        return patch_status_text
    def _iterate_file_data(self, pdt):
        if self._is_applied:
            return iterate_quilt_file_data(pdt)
        else:
            return iterate_patchlib_file_data(pdt)

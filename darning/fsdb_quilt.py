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
CFRD = collections.namedtuple("CFRD", ["subdir_relpath", "name"])
def get_file_path_relative_data(file_path, base_dir_path=None):
    data = CFRD(*os.path.split(os.path.relpath(file_path, os.curdir if base_dir_path is None else base_dir_path)))
    return None if data.subdir_relpath.startswith(os.pardir) else data

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

class TopPatchFileDb(fsdb.GenericTopPatchFileDb):
    class FileDir(fsdb.GenericTopPatchFileDb.FileDir):
        CLEAN_STATUS_SET = frozenset([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED])
        def _calculate_status(self):
            if not self._status_set:
                return None
            elif len(self._status_set) > 1:
                return  FSTATUS_MODIFIED
            else:
                return list(self._status_set)[0]
    @staticmethod
    def _get_applied_patch_count():
        return len(runext.run_get_cmd(["quilt", "applied"], default="").splitlines())
    def _get_patch_data_text(self, h):
        if self._applied_patch_count == 0:
            return ""
        patch_status_text = runext.run_get_cmd(["quilt", "files", "-v"], default="")
        h.update(patch_status_text)
        return (patch_status_text)
    @staticmethod
    def _iterate_file_data(pdt):
        return iterate_quilt_file_data(pdt)

class PatchFileDb(fsdb.GenericPatchFileDb):
    FileDir = TopPatchFileDb.FileDir
    def __init__(self, patch_name):
        self._patch_file_path = quilt_utils.get_patch_file_path(patch_name)
        fsdb.GenericPatchFileDb.__init__(self, patch_name=patch_name)
    @staticmethod
    def _get_is_applied(patch_name):
        return quilt_utils.is_patch_applied(patch_name)
    def _get_patch_data_text(self, h):
        if self._is_applied:
            patch_status_text = runext.run_get_cmd(["quilt", "files", "-v", self.patch_name], default="")
        else:
            patch_status_text = utils.get_file_contents(self._patch_file_path)
        h.update(patch_status_text)
        return patch_status_text
    def _iterate_file_data(self, pdt):
        if self._is_applied:
            return iterate_quilt_file_data(pdt)
        else:
            return iterate_patchlib_file_data(pdt)

class CombinedPatchFileDb(TopPatchFileDb):
    def _get_patch_data_text(self, h):
        stdout = runext.run_get_cmd(["quilt", "files", "-va"], default="")
        h.update(stdout)
        return stdout
    @staticmethod
    def _iterate_file_data(pdt):
        for line in pdt.splitlines():
            if line[0] in FSTATUS_MODIFIED_SET:
                yield (line[2:], line[0], None)

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

from . import fsdb
from . import utils
from . import patchlib

FSTATUS_MODIFIED = 'M'
FSTATUS_ADDED = 'A'
FSTATUS_REMOVED = 'R'
FSTATUS_CLEAN = 'C'
FSTATUS_MISSING = '!'
FSTATUS_NOT_TRACKED = '?'
FSTATUS_IGNORED = 'I'
FSTATUS_ORIGIN = ' '
FSTATUS_UNRESOLVED = 'U'

FSTATUS_MODIFIED_SET = frozenset([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED, FSTATUS_MISSING, FSTATUS_UNRESOLVED])
FSTATUS_CLEAN_SET = frozenset([FSTATUS_IGNORED, FSTATUS_CLEAN, None])
FSTATUS_MARDUC_SET = frozenset([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED, FSTATUS_MISSING, FSTATUS_NOT_TRACKED, FSTATUS_CLEAN])

STATUS_DECO_MAP = {
    None: fsdb.Deco(pango.STYLE_NORMAL, 'black'),
    FSTATUS_CLEAN: fsdb.Deco(pango.STYLE_NORMAL, 'black'),
    FSTATUS_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, 'blue'),
    FSTATUS_ADDED: fsdb.Deco(pango.STYLE_NORMAL, 'darkgreen'),
    FSTATUS_REMOVED: fsdb.Deco(pango.STYLE_NORMAL, 'red'),
    FSTATUS_UNRESOLVED: fsdb.Deco(pango.STYLE_NORMAL, 'magenta'),
    FSTATUS_MISSING: fsdb.Deco(pango.STYLE_ITALIC, 'pink'),
    FSTATUS_NOT_TRACKED: fsdb.Deco(pango.STYLE_ITALIC, 'cyan'),
    FSTATUS_IGNORED: fsdb.Deco(pango.STYLE_ITALIC, 'grey'),
}

def get_qparent():
    result = runext.run_cmd(["hg", "log", "--template", "{rev}", "-rqparent"])
    return result.stdout if result.ecode == 0 else None

def iterate_hg_file_data(patch_status_text, resolve_list_text=""):
    unresolved_file_set = set(line[2:] for line in resolve_list_text.splitlines() if line[0] == FSTATUS_UNRESOLVED)
    lines = iter(patch_status_text.splitlines())
    for line in lines:
        while True:
            file_path = line[2:]
            status = FSTATUS_UNRESOLVED if file_path in unresolved_file_set else line[0]
            if line[0] == FSTATUS_ADDED:
                try:
                    next_line = next(lines)
                    if next_line[0] == FSTATUS_ORIGIN:
                        rfp = next_line[2:]
                        reln = fsdb.Relation.COPIED_FROM if os.path.exists(rfp) else fsdb.Relation.MOVED_FROM
                        yield (file_path, status, fsdb.RFD(path=rfp, relation=reln))
                        break
                    else:
                        yield (file_path, status, None)
                        line = next_line
                        # DON'T BREAK
                except StopIteration:
                    # line was the last line in the text
                    yield (file_path, status, None)
                    break
            else:
                yield (file_path, status, None)
                break

class WsFileDb(fsdb.GenericSnapshotWsFileDb):
    class FileDir(fsdb.GenericSnapshotWsFileDb.FileDir):
        IGNORED_STATUS_SET = frozenset([FSTATUS_IGNORED])
        CLEAN_STATUS_SET = FSTATUS_CLEAN_SET
        SIGNIFICANT_DATA_SET = frozenset(list(FSTATUS_MODIFIED_SET) + [FSTATUS_NOT_TRACKED])
        def _get_initial_status(self):
            # TODO: fix status calculation to differentiate between MISSING and REMOVED
            if not os.path.isdir(self._dir_path):
                return FSTATUS_MISSING
            elif FSTATUS_UNRESOLVED in self._file_status_snapshot.status_set:
                return FSTATUS_UNRESOLVED
            elif FSTATUS_MODIFIED_SET & self._file_status_snapshot.status_set:
                return FSTATUS_MODIFIED
            elif FSTATUS_NOT_TRACKED in self._file_status_snapshot.status_set:
                return FSTATUS_NOT_TRACKED
            return None
    def __init__(self, **kwargs):
        qparent = get_qparent()
        self._cmd_rev = ["--rev", qparent] if qparent else []
        fsdb.GenericSnapshotWsFileDb.__init__(self)
    def _get_file_data_text(self, h):
        file_data_text = runext.run_cmd(["hg", "status", "-marduiC"] + self._cmd_rev).stdout
        h.update(file_data_text)
        unresolved_file_text = runext.run_cmd(["hg", "resolve", "--list"]).stdout
        h.update(unresolved_file_text)
        return (file_data_text, unresolved_file_text)
    @staticmethod
    def _extract_file_status_snapshot(file_data_text):
        fsd = {file_path: (status, related_file_data) for file_path, status, related_file_data in iterate_hg_file_data(*file_data_text)}
        return fsdb.Snapshot(fsd)

class TopPatchFileDb(fsdb.GenericChangeFileDb):
    class FileDir(fsdb.GenericChangeFileDb.FileDir):
        CLEAN_STATUS_SET = frozenset([FSTATUS_MODIFIED, FSTATUS_ADDED, FSTATUS_REMOVED, FSTATUS_MISSING])
        def _calculate_status(self):
            if not self._status_set:
                return None
            elif FSTATUS_UNRESOLVED in self._status_set:
                return FSTATUS_UNRESOLVED
            elif len(self._status_set) > 1:
                return  FSTATUS_MODIFIED
            else:
                return list(self._status_set)[0]
    def __init__(self):
        self._parent_rev = self._get_parent_rev()
        fsdb.GenericChangeFileDb.__init__(self)
    @staticmethod
    def _get_parent_rev():
        result = runext.run_cmd(["hg", "qapplied"])
        if result.ecode != 0: return None # we're not in a repo so no patches
        applied_patches = result.stdout.splitlines()
        if not applied_patches:
            return None
        elif len(applied_patches) > 1:
            return applied_patches[-2]
        else:
            return get_qparent()
    @property
    def is_current(self):
        if self._get_parent_rev() != self._parent_rev:
            # somebody's popped or pushed externally
            return False
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_patch_data_text(self, h):
        if self._parent_rev is None:
            return ("", "")
        patch_status_text = runext.run_cmd(["hg", "status", "-mardC", "--rev", self._parent_rev]).stdout
        h.update(patch_status_text)
        resolve_list_text = runext.run_cmd(["hg", "resolve", "--list"]).stdout
        h.update(resolve_list_text)
        return (patch_status_text, resolve_list_text)
    @staticmethod
    def _iterate_file_data(pdt):
        return iterate_hg_file_data(*pdt)

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

class PatchFileDb(fsdb.GenericChangeFileDb):
    FileDir = TopPatchFileDb.FileDir
    def __init__(self, patch_name):
        self._patch_name = patch_name
        self._is_applied = self._get_current_is_applied()
        self._patch_file_path = os.path.join(".hg", "patches", patch_name)
        fsdb.GenericChangeFileDb.__init__(self)
    @property
    def is_current(self):
        if self._get_current_is_applied() != self._is_applied:
            # somebody's popped or pushed externally
            return False
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_current_is_applied(self):
        result = runext.run_cmd(["hg", "qapplied"])
        return False if result.ecode else self._patch_name in result.stdout.splitlines()
    def _get_patch_data_text(self, h):
        if self._is_applied:
            patch_status_text = runext.run_cmd(["hg", "status", "-mardC", "--change", self._patch_name]).stdout
        else:
            patch_status_text = utils.get_file_contents(self._patch_file_path)
        h.update(patch_status_text)
        return patch_status_text
    def _iterate_file_data(self, pdt):
        if self._is_applied:
            return iterate_hg_file_data(pdt, "")
        else:
            return iterate_patchlib_file_data(pdt)

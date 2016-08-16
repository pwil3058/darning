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

from gi.repository import Pango

from . import fsdb
from . import utils
from . import patchlib
from . import runext

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
    None: fsdb.Deco(Pango.Style.NORMAL, 'black'),
    FSTATUS_CLEAN: fsdb.Deco(Pango.Style.NORMAL, 'black'),
    FSTATUS_MODIFIED: fsdb.Deco(Pango.Style.NORMAL, 'blue'),
    FSTATUS_ADDED: fsdb.Deco(Pango.Style.NORMAL, 'darkgreen'),
    FSTATUS_REMOVED: fsdb.Deco(Pango.Style.NORMAL, 'red'),
    FSTATUS_UNRESOLVED: fsdb.Deco(Pango.Style.NORMAL, 'magenta'),
    FSTATUS_MISSING: fsdb.Deco(Pango.Style.ITALIC, 'pink'),
    FSTATUS_NOT_TRACKED: fsdb.Deco(Pango.Style.ITALIC, 'cyan'),
    FSTATUS_IGNORED: fsdb.Deco(Pango.Style.ITALIC, 'grey'),
}

def get_qparent():
    return runext.run_get_cmd(["hg", "log", "--template", "{rev}", "-rqparent"], default=None)

def iterate_hg_file_data(file_data_text, related_file_data):
    patch_status_text, resolve_list_text = file_data_text
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
                        if reln == fsdb.Relation.MOVED_FROM:
                            related_file_data.append((file_path, rfp))
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
        self._cmd_rev = ["--rev", "qparent"] if get_qparent() else []
        fsdb.GenericSnapshotWsFileDb.__init__(self, **kwargs)
    def _get_file_data_text(self, h):
        file_data_text = runext.run_get_cmd(["hg", "status", "-marduiC"] + self._cmd_rev)
        h.update(file_data_text.encode())
        unresolved_file_text = runext.run_get_cmd(["hg", "resolve", "--list"])
        h.update(unresolved_file_text.encode())
        return (file_data_text, unresolved_file_text)
    @staticmethod
    def _extract_file_status_snapshot(file_data_text):
        related_file_path_data = []
        fsd = {file_path: (status, related_file_data) for file_path, status, related_file_data in iterate_hg_file_data(file_data_text, related_file_path_data)}
        for file_path, related_file_path in related_file_path_data:
            data = fsd.get(related_file_path, None)
            if data is not None:
                # don't overwrite git's opinion on related file data if it had one
                if data[1] is not None: continue
                status = data[0]
            else:
                stdout = runext.run_get_cmd(["hg", "status", related_file_path], default="")
                status = stdout[:2] if stdout else None
            fsd[related_file_path] = (status, fsdb.RFD(path=file_path, relation=fsdb.Relation.MOVED_TO))
        return fsdb.Snapshot(fsd)

class TopPatchFileDb(fsdb.GenericTopPatchFileDb):
    class FileDir(fsdb.GenericTopPatchFileDb.FileDir):
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
        fsdb.GenericTopPatchFileDb.__init__(self)
    @staticmethod
    def _get_applied_patch_count():
        return len(runext.run_get_cmd(["hg", "qapplied"], default="").splitlines())
    @staticmethod
    def _get_parent_rev():
        applied_patches = runext.run_get_cmd(["hg", "qapplied"], default="").splitlines()
        if not applied_patches:
            return None
        elif len(applied_patches) > 1:
            return applied_patches[-2]
        else:
            return "qparent"
    def _get_patch_data_text(self, h):
        if self._parent_rev is None:
            return ("", "")
        patch_status_text = runext.run_get_cmd(["hg", "status", "-mardC", "--rev", self._parent_rev])
        h.update(patch_status_text.encode())
        resolve_list_text = runext.run_get_cmd(["hg", "resolve", "--list"])
        h.update(resolve_list_text.encode())
        return (patch_status_text, resolve_list_text)
    @staticmethod
    def _iterate_file_data(file_data_text):
        return WsFileDb._extract_file_status_snapshot(file_data_text)

class CombinedPatchFileDb(TopPatchFileDb):
    @staticmethod
    def _get_parent_rev():
        return "qparent" if runext.run_get_cmd(["hg", "qapplied"], default="") else None

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

class PatchFileDb(fsdb.GenericPatchFileDb):
    FileDir = TopPatchFileDb.FileDir
    def __init__(self, patch_name):
        self._patch_file_path = os.path.join(".hg", "patches", patch_name)
        fsdb.GenericPatchFileDb.__init__(self, patch_name=patch_name)
    @staticmethod
    def _get_is_applied(patch_name):
        return patch_name in runext.run_get_cmd(["hg", "qapplied"], default="").splitlines()
    def _get_patch_data_text(self, h):
        if self._is_applied:
            patch_status_text = runext.run_get_cmd(["hg", "status", "-mardC", "--change", self.patch_name])
        else:
            # handle the case where the patch file gets deleted
            try:
                patch_status_text = utils.get_file_contents(self._patch_file_path)
            except IOError as edata:
                if edata.errno == 2:
                    patch_status_text = ""
                else:
                    raise
        h.update(patch_status_text.encode())
        return patch_status_text
    def _iterate_file_data(self, pdt):
        if self._is_applied:
            return iterate_hg_file_data((pdt, ""), [])
        else:
            return iterate_patchlib_file_data(pdt)

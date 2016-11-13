### Copyright (C) 2015 Peter Williams <pwil3058@gmail.com>
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

from gi.repository import Pango

from ..gtx import fsdb

from .. import patch_db

_STATUS_DECO_MAP = {
    None: fsdb.Deco(Pango.Style.NORMAL, "black"),
    patch_db.Presence.ADDED: fsdb.Deco(Pango.Style.NORMAL, "darkgreen"),
    patch_db.Presence.REMOVED: fsdb.Deco(Pango.Style.NORMAL, "red"),
    patch_db.Presence.EXTANT: fsdb.Deco(Pango.Style.NORMAL, "black"),
}

class FileData(fsdb.FileData):
    STATUS_DECO_MAP = _STATUS_DECO_MAP
    @property
    def deco(self):
        return self.STATUS_DECO_MAP[self.status.presence]
    @property
    def icon(self):
        from .. import wsm_icons
        if self.status.validity == patch_db.Validity.REFRESHED:
            return wsm_icons.STOCK_FILE_REFRESHED
        elif self.status.validity == patch_db.Validity.NEEDS_REFRESH:
            return wsm_icons.STOCK_FILE_NEEDS_REFRESH
        elif self.status.validity == patch_db.Validity.UNREFRESHABLE:
            return wsm_icons.STOCK_FILE_UNREFRESHABLE
        else:
            return Gtk.STOCK_FILE
    @property
    def status_str(self):
        return self.status.presence

class DirData(fsdb.DirData):
    STATUS_DECO_MAP = _STATUS_DECO_MAP
    @property
    def deco(self):
        return self.STATUS_DECO_MAP[self.status.presence]
    @property
    def clean_deco(self):
        return self.STATUS_DECO_MAP[self.clean_status.presence]
    @property
    def status_str(self):
        return self.status.presence
    @property
    def clean_status_str(self):
        return self.clean_status.presence

class _PatchFileDir(fsdb.GenericChangeFileDb.FileDir):
    FILE_DATA = FileData
    DIR_DATA = DirData
    def _calculate_status(self):
        if not self._status_set:
            validity = patch_db.Validity.REFRESHED
        else:
            validity = max([s.validity for s in list(self._status_set)])
        return patch_db.FileStatus(None, validity)
    def _calculate_clean_status(self):
        if not self._status_set:
            validity = patch_db.Validity.REFRESHED
        else:
            validity = max([s.validity for s in list(self._status_set)])
        return patch_db.FileStatus(None, validity)
    def dirs_and_files(self, hide_clean=False, **kwargs):
        if hide_clean:
            dirs = filter((lambda x: x.status.validity), self._subdirs_data)
            files = filter((lambda x: x.status.validity), self._files_data)
        else:
            dirs = iter(self._subdirs_data)
            files = iter(self._files_data)
        return (dirs, files)

class TopPatchFileDb(fsdb.GenericTopPatchFileDb):
    FileDir = _PatchFileDir
    @staticmethod
    def _get_applied_patch_count():
        return patch_db.get_applied_patch_count()
    @staticmethod
    def _get_patch_data_text(h):
        patch_status_text = patch_db.get_patch_file_table()
        h.update(str(patch_status_text).encode())
        return patch_status_text
    @staticmethod
    def _iterate_file_data(pdt):
        for item in pdt:
            yield item

class CombinedPatchFileDb(TopPatchFileDb):
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_combined_patch_file_table()
        h.update(str(patch_status_text).encode())
        return patch_status_text

class PatchFileDb(fsdb.GenericPatchFileDb):
    FileDir = _PatchFileDir
    @property
    def is_current(self):
        import hashlib
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    @staticmethod
    def _get_is_applied(patch_name):
        return patch_db.is_patch_applied(patch_name)
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_patch_file_table(self.patch_name)
        h.update(str(patch_status_text).encode())
        return patch_status_text
    def _iterate_file_data(self, pdt):
        for item in pdt:
            yield item

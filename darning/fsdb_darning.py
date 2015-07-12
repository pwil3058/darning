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

import pango

from . import fsdb
from . import patch_db

STATUS_DECO_MAP = {
    None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
    patch_db.FileData.Presence.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
    patch_db.FileData.Presence.REMOVED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
    patch_db.FileData.Presence.EXTANT: fsdb.Deco(pango.STYLE_NORMAL, "black"),
}

class PatchFileDb(fsdb.GenericChangeFileDb):
    class FileDir(fsdb.GenericChangeFileDb.FileDir):
        def _calculate_status(self):
            if not self._status_set:
                validity = patch_db.FileData.Validity.REFRESHED
            else:
                validity = max([s.validity for s in list(self._status_set)])
            return patch_db.FileData.Status(None, validity)
        def dirs_and_files(self, hide_clean=False, **kwargs):
            if hide_clean:
                dirs = ifilter((lambda x: x.status.validity), self._subdirs_data)
                files = ifilter((lambda x: x.status.validity), self._files_data)
            else:
                dirs = iter(self._subdirs_data)
                files = iter(self._files_data)
            return (dirs, files)
    def __init__(self, patch_name=None):
        self._patch_name = patch_name
        fsdb.GenericChangeFileDb.__init__(self)
    @property
    def is_current(self):
        import hashlib
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_patch_file_table(self._patch_name)
        h.update(str(patch_status_text))
        return patch_status_text
    def _iterate_file_data(self, pdt):
        for item in pdt:
            yield item

class CombinedPatchFileDb(PatchFileDb):
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_combined_patch_file_table()
        h.update(str(patch_status_text))
        return patch_status_text

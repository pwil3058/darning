### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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
import collections
import hashlib
import re
import time

from aipoed import CmdResult

from aipoed import enotify

E_PUSH, E_POP, E_NEW_PATCH, E_PATCH_STACK_CHANGES = enotify.new_event_flags_and_mask(3)
E_DELETE_PATCH, E_MODIFY_PATCH, E_MODIFY_GUARDS, E_PATCH_QUEUE_CHANGES = enotify.new_event_flags_and_mask(3)
E_PATCH_LIST_CHANGES = E_PATCH_STACK_CHANGES|E_PATCH_QUEUE_CHANGES

E_FILE_ADDED, E_FILE_DELETED, E_PATCH_REFRESH, E_FILE_CHANGES = enotify.new_event_flags_and_mask(3)
E_FILE_MOVED = E_FILE_ADDED|E_FILE_DELETED

class Presence(object):
    from . import patchlib
    ADDED = patchlib.FilePathPlus.ADDED
    REMOVED = patchlib.FilePathPlus.DELETED
    EXTANT = patchlib.FilePathPlus.EXTANT

class Validity(object):
    REFRESHED, NEEDS_REFRESH, UNREFRESHABLE = range(3)

class FileStatus(collections.namedtuple("FileStatus", ["presence", "validity"])):
    def __str__(self):
        return self.presence

class PatchState(object):
    NOT_APPLIED = " "
    APPLIED_REFRESHED = "+"
    APPLIED_NEEDS_REFRESH = "?"
    APPLIED_UNREFRESHABLE = "!"

PatchTableRow = collections.namedtuple("PatchTableRow", ["name", "state", "pos_guards", "neg_guards"])

def patch_timestamp_tz_str(tz_seconds=None):
    '''Return the timezone as a string suitable for use in patch header'''
    if tz_seconds is None:
        tz_seconds = -time.timezone
    if tz_seconds > 0:
        hrs = tz_seconds / 3600
    else:
        hrs = -(-tz_seconds / 3600)
    mins = (abs(tz_seconds) % 3600) / 60
    return '{0:0=+3}{1:02}'.format(hrs, mins)

_PTS_TEMPL = '%Y-%m-%d %H:%M:%S.{0:09} ' + patch_timestamp_tz_str()

def patch_timestamp_str(secs=None):
    '''Return the "in patch" timestamp string for "secs" seconds'''
    ts_str = time.strftime(_PTS_TEMPL, time.localtime(secs))
    return ts_str.format(int((secs % 1) * 1000000000))

MERGE_CRE = re.compile("^(<<<<<<<|>>>>>>>).*$")

_BACKEND = {}
_MISSING_BACKEND = {}

def add_backend(newifce):
    if newifce.is_available:
        _BACKEND[newifce.name] = newifce
    else:
        _MISSING_BACKEND[newifce.name] = newifce

def backend_requirements():
    msg = _("No back ends are available. At least one of:") + os.linesep
    for key in list(_MISSING_BACKEND.keys()):
        msg += '\t' + _MISSING_BACKEND[key].requires() + os.linesep
    msg += _("must be installed/available for \"gquilt\" to do.anything useful.")
    return msg

def report_backend_requirements(parent=None):
    dialogue.main_window.inform_user(backend_requirements(), parent=parent)

def avail_backends(include_deprecated=False):
    if include_deprecated:
        return list(_BACKEND.keys())
    else:
        return [be.name for be in _BACKEND.values() if not be.is_deprecated]

def playground_type(dirpath=None):
    for bname in list(_BACKEND.keys()):
        if _BACKEND[bname].dir_is_in_valid_pgnd(dirpath):
            return bname
    return None

def get_ifce(dirpath=None):
    pgt = playground_type(dirpath)
    return _NULL_BACKEND if pgt is None else _BACKEND[pgt]

def create_new_playground(pgdir, backend):
    return _BACKEND[backend].create_new_playground(pgdir)

class PatchListData:
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        h = hashlib.sha1()
        pdt = self._get_data_text(h)
        self._db_hash_digest = h.digest()
        self._current_text_digest = None
        self._finalize(pdt)
    def __getattr__(self, name):
        if name == "is_current": return self._is_current()
        if name == "selected_guards": return self._selected_guards
        raise AttributeError(name)
    def _finalize(self, pdt):
        assert False, "_finalize() must be defined in child"
    def _is_current(self):
        h = hashlib.sha1()
        self._current_text = self._get_data_text(h)
        self._current_text_digest = h.digest()
        return self._current_text_digest == self._db_hash_digest
    def reset(self):
        if self._current_text_digest is None:
            return self.__class__(**self._kwargs)
        if self._current_text_digest != self._db_hash_digest:
            self._db_hash_digest = self._current_text_digest
            self._finalize(self._current_text)
        return self
    def _get_data_text(self, h):
        assert False, "_get_data_text() must be defined in child"
    def iter_rows(self):
        for patch_data in self._patches_data:
            yield patch_data

class NullPatchListData:
    def __getattr__(self, name):
        if name == "is_current": return True
        if name == "selected_guards": return []
    def reset(self):
        pass
    def iter_rows(self):
        return []

class _NULL_BACKEND:
    name = "null"
    cmd_label = "null"
    in_valid_pgnd = False
    has_finish_patch = False
    has_guards = False
    has_refresh_non_top = False
    is_extdiff_for_full_patch_ok = False
    is_poppable = False
    is_pushable = False
    all_applied_patches_refreshed = False
    # no caching so no state ergo all methods will be static/class methods
    # "do" methods should never be called for the null interface
    # so we won't provide them
    # "get" methods may be called so return the approriate "nothing"
    @staticmethod
    def get_applied_patches():
        return []
    @staticmethod
    def get_applied_patch_count():
        return 0
    @staticmethod
    def get_author_name_and_email():
        return None
    @staticmethod
    def get_base_patch():
        return None
    @staticmethod
    def get_combined_patch_diff_text(file_path_list=None):
        return ""
    @staticmethod
    def get_combined_patch_file_db():
        from . import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_default_new_patch_save_file():
        return None
    @staticmethod
    def get_description_is_finish_ready(patch_name):
        return False
    @staticmethod
    def get_extension_enabled(extension):
        return False
    @staticmethod
    def get_named_patch_diff_text(patch_name, file_path_list=None):
        return ""
    @staticmethod
    def get_next_patch():
        return None
    @staticmethod
    def get_patch_description(patch_name):
        return ""
    @staticmethod
    def get_patch_file_db(patch_name):
        from . import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_patch_file_path(patch_name):
        return None
    @staticmethod
    def get_patch_files(patch_name, with_status=False):
        return []
    @staticmethod
    def get_patch_guards(patch_name):
        return []
    @staticmethod
    def get_patch_list_data():
        return NullPatchListData()
    @staticmethod
    def get_patch_text(patch_name):
        return ""
    @staticmethod
    def get_playground_root(dir_name=None):
        return None
    @staticmethod
    def get_selected_guards():
        return []
    @staticmethod
    def get_top_patch():
        return None
    @staticmethod
    def get_top_patch_diff_text(file_path_list=None):
        return ""
    @staticmethod
    def get_top_patch_file_db():
        from . import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_ws_update_clean_up_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_merge_ready(unapplied_count=None):
        return False
    @staticmethod
    def get_ws_update_pull_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_qsave_ready(unapplied_count, applied_count):
        return False
    @staticmethod
    def get_ws_update_ready(applied_count=None):
        return False
    @staticmethod
    def get_ws_update_to_ready(applied_count=None):
        return False
    @staticmethod
    def is_patch_applied(patch_name):
        return False
    @staticmethod
    def launch_extdiff_for_patch(patch_name=None, file_path_list=None):
        return
    @staticmethod
    def launch_extdiff_for_top_patch(file_path_list=None):
        return

def generic_delete_files(file_paths):
    from . import os_utils
    return os_utils.os_delete_files(file_paths, events=E_FILE_DELETED)

def set_patch_file_description(patch_file_path, description, overwrite=False):
    from . import patchlib
    from . import utils
    if os.path.isfile(patch_file_path):
        try:
            patch_obj = patchlib.Patch.parse_text(utils.get_file_contents(patch_file_path))
        except IOError as edata:
            return CmdResult.error(stderr=str(edata))
        except patchlib.ParseError:
            if overwrite:
                patch_obj = patchlib.Patch()
            else:
                return CmdResult.error(stderr=_("{0}: exists but is not a valid patch file".format(patch_file_path))) | CmdResult.Suggest.OVERWRITE
    else:
        patch_obj = patchlib.Patch()
    patch_obj.set_description(description)
    result = utils.set_file_contents(patch_file_path, str(patch_obj), compress=True)
    return result

def get_patch_file_description(patch_file_path):
    assert os.path.isfile(patch_file_path), _("Patch file \"{0}\" does not exist\n").format(patch_file_path)
    from . import patchlib
    from . import utils
    pobj = patchlib.Patch.parse_text(utils.get_file_contents(patch_file_path))
    return pobj.get_description()

class InterfaceMixin:
    @classmethod
    def _add_extra_patch_file_paths(cls, file_paths):
        patch_file_paths = cls.get_patch_files()
        ep_file_paths_set = {fp for fp in file_paths if fp not in patch_file_paths}
        if ep_file_paths_set:
            return cls.do_add_files(ep_file_paths_set)
        return CmdResult.ok()
    @classmethod
    def do_export_patch_as(cls, patch_name, export_file_name=None, force=False, overwrite=False):
        if not force:
            result = cls._check_patch_export_status(patch_name)
            if result:
                return result
        if not export_file_name:
            export_file_name = utils.convert_patchname_to_filename(patch_name)
        if not overwrite and os.path.exists(export_file_name):
            emsg = _("{0}: file already exists.\n").format(export_file_name)
            return CmdResult.error(stderr=emsg) + CmdResult.Suggest.OVERWRITE_OR_RENAME
        # NB we don't use shutil.copyfile() here as names may dictate (de)compression
        return utils.set_file_contents(export_file_name, cls.get_patch_text(patch_name))
    @classmethod
    def do_set_patch_description(cls, patch_name, description, overwrite=False):
        from .gui import console
        result = set_patch_file_description(cls.get_patch_file_path(patch_name), description, overwrite=overwrite)
        if result.is_ok:
            console.LOG.append_entry(_("set description for \"{0}\" patch.\n{1}\n").format(patch_name, description))
        return result
    @classmethod
    def get_patch_description(cls, patch_name):
        return get_patch_file_description(cls.get_patch_file_path(patch_name))

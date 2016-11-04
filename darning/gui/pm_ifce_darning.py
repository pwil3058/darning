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

from ..wsm.bab import CmdResult
from ..wsm.bab import CmdFailure

from ..wsm.bab import enotify
from ..wsm.bab import utils

from ..wsm.bab.decorators import singleton

from ..wsm.gtx.console import RCTX, LOG

from ..wsm import pm
from ..wsm import pm_gui

from ..wsm.pm import PatchState

from ..wsm.pm_gui import ifce as pm_gui_ifce

from .. import patch_db
from . import fsdb_darning

def _RUN_DO(cmd_text, cmd_do, events, e_always=True):
    RCTX.reset()
    LOG.start_cmd(cmd_text)
    result = CmdResult(cmd_do(), RCTX.stdout.text, RCTX.stderr.text)
    LOG.end_cmd()
    if e_always or result.is_less_than_error:
        enotify.notify_events(events)
    return result

class PatchListData(pm_gui.PatchListData):
    def _finalize(self, pdt):
        self._rows, self._selected_guards = pdt
    def _get_data_text(self, h):
        patches_data = patch_db.get_patch_table_data()
        selected_guards = patch_db.get_selected_guards()
        for patch_data in patches_data:
            h.update(str(patch_data).encode())
        h.update(str(selected_guards).encode())
        return (patches_data, selected_guards)

@singleton
class Interface(pm_gui.InterfaceMixin):
    name = "darning"
    cmd_label = "darning"
    has_add_files = False
    has_finish_patch = True
    has_guards = True
    has_refresh_non_top = True
    is_available = True
    is_deprecated = False
    pgnd_is_mutable = True
    @staticmethod
    def __getattr__(attr_name):
        if attr_name == "in_valid_pgnd": return patch_db.find_base_dir() is not None
        if attr_name == "is_poppable": return patch_db.get_applied_patch_count() > 0
        if attr_name == "is_pushable": return patch_db.is_pushable()
        if attr_name == "all_applied_patches_refreshed": return patch_db.all_applied_patches_refreshed()
        raise AttributeError(attr_name)
    @staticmethod
    def create_new_playground(dir_path=None):
        if dir_path:
            import os
            if not os.path.exists(dir_path):
                try:
                    os.mkdir(dir_path)
                except OSError as edata:
                    return CmdResult.error(stderr=str(edata))
        cmd_str = "init {0}\n".format(dir_path) if dir_path else "init\n"
        events = pm.E_NEW_PM if not dir_path else 0
        return _RUN_DO(cmd_str, lambda: patch_db.do_create_db(dir_path), events)
    @staticmethod
    def dir_is_in_valid_pgnd(dir_path=None):
        return patch_db.find_base_dir(dir_path) is not None
    @staticmethod
    def do_add_files_to_top_patch(file_paths, absorb=False, force=False):
        if absorb:
            cmd_str = "add --absorb {0}\n".format(utils.quoted_join(file_paths))
        elif force:
            cmd_str = "add --force {0}\n".format(utils.quoted_join(file_paths))
        else:
            cmd_str = "add {0}\n".format(utils.quoted_join(file_paths))
        cmd_do = lambda: patch_db.do_add_files_to_top_patch(file_paths, absorb=absorb, force=force)
        events = pm.E_FILE_ADDED|pm.E_PATCH_REFRESH if (absorb or force) else pm.E_FILE_ADDED
        return _RUN_DO(cmd_str, cmd_do, events, False)
    @staticmethod
    def do_copy_file_to_top_patch(file_path, as_file_path, overwrite=False):
        tmpl = "copy --overwrite {0} {1}\n" if overwrite else "copy {0} {1}\n"
        cmd_str = tmpl.format(utils.quote_if_needed(file_path), utils.quote_if_needed(as_file_path))
        return _RUN_DO(cmd_str, lambda: patch_db.do_copy_file_to_top_patch(file_path, as_file_path, overwrite=overwrite), pm.E_FILE_ADDED)
    @staticmethod
    def do_create_new_patch(patch_name, descr):
        cmd_str = _("new patch {0} --msg \"{1}\"\n").format(utils.quote_if_needed(patch_name), descr)
        return _RUN_DO(cmd_str, lambda: patch_db.do_create_new_patch(patch_name, descr), pm.E_NEW_PATCH|pm.E_PUSH, False)
    @staticmethod
    def do_delete_files_in_top_patch(file_paths):
        cmd_str = "delete {0}\n".format(utils.quoted_join(file_paths))
        return _RUN_DO(cmd_str, lambda: patch_db.do_delete_files_in_top_patch(file_paths), pm.E_FILE_DELETED)
    @staticmethod
    def do_drop_files_from_patch(file_paths, patch_name=None):
        if patch_name is None:
            cmd_str = "drop {0}\n".format(utils.quoted_join(file_paths))
        else:
            cmd_stre ="drop --patch={0} {1}\n".format(utils.quote_if_needed(patch_name), utils.quoted_join(file_paths))
        return _RUN_DO(cmd_str, lambda: patch_db.do_drop_files_fm_patch(patch_name, file_paths), pm.E_FILE_DELETED|pm.E_DELETE_PATCH, False)
    @staticmethod
    def do_duplicate_patch(patch_name, as_patch_name, new_description):
        cmd_str = "duplicate patch {0} as {1}".format(utils.quote_if_needed(patch_name), utils.quote_if_needed(as_patch_name))
        cmd_str += " --msg \"{0}\"\n".format(new_description)
        return _RUN_DO(cmd_str, lambda: patch_db.do_duplicate_patch(patch_name, as_patch_name, new_description), pm.E_NEW_PATCH, False)
    @staticmethod
    def do_import_patch(epatch, as_patchname, overwrite=False):
        RCTX.reset()
        if overwrite:
            cmd_str = "import --overwrite {0} as {1}\n".format(utils.quote_if_needed(epatch.source_name), utils.quote_if_needed(as_patchname))
        else:
            cmd_str = "import {0} as {1}\n".format(utils.quote_if_needed(epatch.source_name), utils.quote_if_needed(as_patchname))
        return _RUN_DO(cmd_str, lambda: patch_db.do_import_patch(epatch, as_patchname, overwrite=overwrite), pm.E_NEW_PATCH|pm.E_PUSH)
    @staticmethod
    def do_fold_epatch(epatch, absorb=False, force=False):
        cmd_str = "fold --file {0}\n".format(utils.quote_if_needed(epatch.source_name))
        return _RUN_DO(cmd_str, lambda: patch_db.do_fold_epatch(epatch, absorb=absorb, force=force), pm.E_FILE_CHANGES)
    @staticmethod
    def do_fold_named_patch(patch_name, absorb=False, force=False):
        cmd_str = "fold --patch {0}\n".format(utils.quote_if_needed(patch_name))
        return _RUN_DO(cmd_str, lambda: patch_db.do_fold_named_patch(patch_name, absorb=absorb, force=force), pm.E_FILE_CHANGES|pm.E_DELETE_PATCH, False)
    @staticmethod
    def do_move_files(file_paths, destn_path, force=False, overwrite=False):
        if force:
            if overwrite:
                tmpl = "move --force --overwrite {0} {1}\n"
            else:
                tmpl = "move --force {0} {1}\n"
        elif overwrite:
            tmpl = "move --overwrite {0} {1}\n"
        else:
            tmpl = "move {0} {1}\n"
        cmd_str = tmpl.format(utils.quoted_join(file_paths), utils.quote_if_needed(destn_path))
        return _RUN_DO(cmd_str, lambda: patch_db.do_move_files_in_top_patch(file_paths, destn_path, force=force, overwrite=overwrite), pm.E_FILE_ADDED|pm.E_FILE_DELETED)
    @staticmethod
    def do_pop_top_patch():
        return _RUN_DO("pop\n", lambda: patch_db.do_unapply_top_patch(), pm.E_POP, False)
    @staticmethod
    def do_push_next_patch(absorb=False, force=False):
        if absorb:
            cmd_str = "push --absorb\n"
        elif force:
            cmd_str = "push --force\n"
        else:
            cmd_str = "push\n"
        return _RUN_DO(cmd_str, lambda: patch_db.do_apply_next_patch(absorb=absorb, force=force), pm.E_PUSH, False)
    @staticmethod
    def do_refresh_patch(patch_name=None):
        cmd_str = "refresh {0}\n".format(utils.quote_if_needed(patch_name)) if patch_name else "refresh\n"
        return _RUN_DO(cmd_str, lambda: patch_db.do_refresh_patch(patch_name), pm.E_PATCH_REFRESH)
    @staticmethod
    def do_remove_patch(patch_name):
        cmd_str = "remove patch: {0}\n".format(utils.quote_if_needed(patch_name))
        return _RUN_DO(cmd_str, lambda: patch_db.do_remove_patch(patch_name), pm.E_DELETE_PATCH)
    @staticmethod
    def do_rename_file_in_top_patch(file_path, new_file_path, force=False, overwrite=False):
        if force:
            if overwrite:
                tmpl = "rename --force --overwrite {0} {1}\n"
            else:
                tmpl = "rename --force {0} {1}\n"
        elif overwrite:
            tmpl = "rename --overwrite {0} {1}\n"
        else:
            tmpl = "rename {0} {1}\n"
        cmd_str = tmpl.format(utils.quote_if_needed(file_path), utils.quote_if_needed(new_file_path))
        return _RUN_DO(cmd_str, lambda: patch_db.do_rename_file_in_top_patch(file_path, new_file_path, force=force, overwrite=overwrite), pm.E_FILE_ADDED|pm.E_FILE_DELETED)
    @staticmethod
    def do_rename_patch(patch_name, new_name):
        cmd_str = "rename patch {0} to {1}\n".format(utils.quote_if_needed(patch_name), utils.quote_if_needed(new_name))
        return _RUN_DO(cmd_str, lambda: patch_db.do_rename_patch(patch_name, new_name), pm.E_MODIFY_PATCH, False)
    @staticmethod
    def do_restore_patch(patch_name, as_patch_name=""):
        if not as_patch_name:
            as_patch_name = patch_name
            cmd_str = "restore {0}\n".format(utils.quote_if_needed(patch_name))
        else:
            cmd_str = "restore {0} as {1}\n".format(utils.quote_if_needed(patch_name), utils.quote_if_needed(as_patch_name))
        return _RUN_DO(cmd_str, lambda: patch_db.do_restore_patch(patch_name, as_patch_name), pm.E_NEW_PATCH, False)
    @staticmethod
    def do_scm_absorb_applied_patches():
        # notify events regardless of return value as partial success is possible
        return _RUN_DO("absorb\n", lambda: patch_db.do_scm_absorb_applied_patches(), pm.E_POP)
    @staticmethod
    def do_select_guards(guards_str):
        cmd_str = "select {0}\n".format(guards_str)
        return _RUN_DO(cmd_str, lambda:patch_db.do_select_guards(guards_str.split()), pm.E_MODIFY_GUARDS, False)
    @staticmethod
    def do_set_patch_description(patch_name, descr, overwrite=False):
        cmd_str = "set patch description {0} --msg \"{1}\"\n".format(utils.quote_if_needed(patch_name), descr)
        return _RUN_DO(cmd_str, lambda: patch_db.do_set_patch_description(patch_name, descr), pm.E_MODIFY_PATCH)
    @staticmethod
    def do_set_patch_guards(patch_name, guards_str):
        cmd_str = "set guards {0} {1}\n".format(utils.quote_if_needed(patch_name), guards_str)
        return _RUN_DO(cmd_str, lambda: patch_db.do_set_patch_guards_fm_str(patch_name, guards_str), pm.E_MODIFY_PATCH, False)
    @staticmethod
    def do_set_series_description(text):
        cmd_str = "set series description --msg \"{0}\"\n".format(text)
        return _RUN_DO(cmd_str, lambda: patch_db.do_set_series_description(text), 0)
    @staticmethod
    def get_applied_patch_count():
        return patch_db.get_applied_patch_count()
    @staticmethod
    def get_author_name_and_email():
        return None # let ifce handle this
    @staticmethod
    def get_combined_patch_diff_pluses(file_paths=None):
        if patch_db.get_applied_patch_count() == 0:
            return []
        return patch_db.get_combined_diff_pluses_for_files(file_paths)
    @staticmethod
    def get_combined_patch_file_db():
        return fsdb_darning.CombinedPatchFileDb()
    @staticmethod
    def get_extdiff_files_for(file_path, patch_name):
        if patch_name is None:
            patch_name = patch_db.get_top_patch_for_file(file_path)
        return patch_db.get_extdiff_files_for(file_path, patch_name)
    @staticmethod
    def get_file_combined_diff(file_path):
        return patch_db.get_file_combined_diff(file_path)
    @staticmethod
    def get_file_diff(file_path, patch_name):
        return patch_db.get_file_diff(file_path, patch_name)
    @staticmethod
    def get_filepaths_not_in_patch(patch_name, file_paths):
        return patch_db.get_filepaths_not_in_patch(patch_name, file_paths)
    @staticmethod
    def get_kept_patch_names():
        return patch_db.get_kept_patch_names()
    @staticmethod
    def get_named_patch_diff_pluses(patch_name, file_paths=None, with_timestamps=False):
        return patch_db.get_diff_pluses_for_files(file_paths=file_paths, patch_name=patch_name, with_timestamps=with_timestamps)
    @staticmethod
    def get_outstanding_changes_below_top():
        return patch_db.get_outstanding_changes_below_top()
    @staticmethod
    def get_patch_description(patch_name):
        return patch_db.get_patch_description(patch_name)
    @staticmethod
    def get_patch_file_db(patch_name):
        return fsdb_darning.PatchFileDb(patch_name)
    @staticmethod
    def get_patch_guards(patch_name):
        guards = patch_db.get_patch_guards(patch_name)
        return ["+" + grd for grd in guards.positive] + ["-" + grd for grd in guards.negative]
    @staticmethod
    def get_patch_list_data():
        return PatchListData()
    @staticmethod
    def get_playground_root():
        return patch_db.find_base_dir()
    @staticmethod
    def get_reconciliation_paths(file_path):
        return patch_db.get_reconciliation_paths(file_path)
    @staticmethod
    def get_selected_guards():
        return patch_db.get_selected_guards()
    @staticmethod
    def get_series_description():
        return patch_db.get_series_description()
    @staticmethod
    def get_textpatch(patch_name):
        return patch_db.get_textpatch(patch_name)
    @staticmethod
    def get_top_patch_diff_pluses(file_paths=None, with_timestamps=False):
        if patch_db.get_applied_patch_count() == 0:
            return []
        return patch_db.get_diff_pluses_for_files(file_paths=file_paths, patch_name=None, with_timestamps=with_timestamps)
    @staticmethod
    def get_top_patch_file_db():
        return fsdb_darning.TopPatchFileDb()
    @staticmethod
    def get_top_patch_for_file(file_path):
        return patch_db.get_top_patch_for_file(file_path)
    @staticmethod
    def is_blocked_by_guard(patch_name):
        return patch_db.is_blocked_by_guard(patch_name)
    @staticmethod
    def is_patch_applied(patch_name):
        return quilt_utils.is_patch_applied(patch_name)
    @staticmethod
    def is_top_patch(patch_name):
        return patch_db.is_top_patch(patch_name)

PM = Interface()
pm_gui_ifce.add_backend(PM)

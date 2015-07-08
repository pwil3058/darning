### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>
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

import hashlib

import gtk

from .. import pm_ifce

from . import gutils
from . import ifce
from . import actions
from . import ws_actions
from . import dialogue
from . import ws_event
from . import icons
from . import text_edit
from . import diff
from . import file_tree
from . import dooph_pm

class PatchFileTreeView(file_tree.FileTreeView):
    REPOPULATE_EVENTS = pm_ifce.E_POP|pm_ifce.E_PUSH|pm_ifce.E_PATCH_STACK_CHANGES
    UPDATE_EVENTS = pm_ifce.E_PATCH_REFRESH|pm_ifce.E_FILE_CHANGES
    AUTO_EXPAND = True
    @staticmethod
    def _generate_row_tuple(data, isdir):
        deco = ifce.PM.get_status_deco(data.status)
        row = PatchFileTreeView.Model.Row(
            name=data.name,
            is_dir=isdir,
            icon=ifce.PM.get_status_icon(data.status, isdir),
            status='',
            related_file_data=data.related_file_data,
            style=deco.style,
            foreground=deco.foreground
        )
        return row
    def __init__(self, patch=None, **kwargs):
        self._patch = patch
        file_tree.FileTreeView.__init__(self, show_hidden=True, hide_clean=False)
    @property
    def patch(self):
        return self._patch
    @patch.setter
    def patch(self, new_patch):
        self._patch = new_patch
        self.repopulate()
    def _get_file_db(self):
        return ifce.PM.get_patch_file_db(self._patch)
    def populate_action_groups(self):
        file_tree.FileTreeView.populate_action_groups(self)
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('patch_edit_files', gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Edit the selected file(s)'),
                 lambda _action=None: self.pm_edit_selected_files()
                ),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the diff for selected file'),
                 lambda _action=None: self.pm_diff_selected_file()
                ),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_extdiff_selected_file', icons.STOCK_DIFF, _('E_xtDiff'), None,
                 _('Launch external diff viewer for selected file'),
                 lambda _action=None: self.pm_extdiff_selected_file()
                ),
                ('patch_copy_file', gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'),
                 lambda _action=None: self.pm_copy_selected_file()
                ),
                ('patch_rename_file', icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'),
                 lambda _action=None: self.pm_rename_selected_file()
                ),
            ])
    def pm_delete_selected_files(self):
        return dooph_pm.pm_delete_files(self.get_selected_filepaths())
    def pm_copy_selected_file(self):
        file_paths = self.get_selected_filepaths()
        assert len(file_paths) == 1
        return dooph_pm.pm_copy_file(file_paths[0])
    def pm_rename_selected_file(self):
        file_paths = self.get_selected_filepaths()
        assert len(file_paths) == 1
        return dooph_pm.pm_rename_file(file_paths[0])
    def pm_edit_selected_files(self):
        file_paths = self.get_selected_filepaths()
        if len(file_paths) == 0:
            return
        text_edit.edit_files_extern(file_paths)
    def pm_diff_selected_file(self):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        dialog = diff.ForFileDialog(filepath=filepaths[0], patchname=self.patch)
        dialog.show()
    def pm_extdiff_selected_file(self):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        files = ifce.PM.get_extdiff_files_for(filepath=filepaths[0], patchname=self.patch)
        dialogue.report_any_problems(diff.launch_external_diff(files.original_version, files.patched_version))

class PatchFileTreeWidget(file_tree.FileTreeWidget):
    MENUBAR = None
    BUTTON_BAR_ACTIONS = ["hide_clean_files"]
    TREE_VIEW = PatchFileTreeView
    SIZE = (240, 320)
    def __init__(self, patch=None, **kwargs):
        file_tree.FileTreeWidget.__init__(self, patch=patch, **kwargs)

class TopPatchFileTreeView(PatchFileTreeView):
    UI_DESCR = '''
    <ui>
      <popup name="files_popup">
        <separator/>
          <menuitem action='patch_edit_files'/>
          <menuitem action='top_patch_drop_selected_files'/>
          <menuitem action='top_patch_delete_selected_files'/>
        <separator/>
          <menuitem action='patch_copy_file'/>
          <menuitem action='patch_rename_file'/>
          <menuitem action='top_patch_reconcile_selected_file'/>
        <separator/>
          <menuitem action='patch_diff_selected_file'/>
          <menuitem action='patch_extdiff_selected_file'/>
        <separator/>
      </popup>
    </ui>
    '''
    def __init__(self, patch=None, **kwargs):
        assert patch is None
        PatchFileTreeView.__init__(self, patch=None, **kwargs)
    def populate_action_groups(self):
        PatchFileTreeView.populate_action_groups(self)
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('top_patch_drop_selected_files', gtk.STOCK_REMOVE, _('_Drop'), None,
                 _('Drop/remove the selected files from the top patch'),
                 lambda _action=None: self.pm_drop_selection()
                ),
                ('top_patch_delete_selected_files', gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Delete the selected files'),
                 lambda _action=None: self.pm_delete_selection()
                ),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('top_patch_reconcile_selected_file', icons.STOCK_MERGE, _('_Reconcile'), None,
                 _('Launch reconciliation tool for the selected file'),
                 lambda _action=None: self.pm_reconcile_selected_file()
                ),
            ])
    def pm_drop_selection(self):
        file_list = self.get_selected_filepaths()
        if len(file_list) == 0:
            return
        emsg = '\n'.join(file_list + ["", _('Confirm drop selected file(s) from patch?')])
        if not dialogue.ask_ok_cancel(emsg):
            return
        dialogue.show_busy()
        result = ifce.PM.do_drop_files_from_patch(file_list, self.patch)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
    def pm_reconcile_selected_file(self):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        files = ifce.PM.get_reconciliation_paths(filepath=filepaths[0])
        dialogue.report_any_problems(diff.launch_reconciliation_tool(files.original_version, files.patched_version, files.stashed_version))

class TopPatchFileTreeWidget(PatchFileTreeWidget):
    TREE_VIEW = TopPatchFileTreeView
    def __init__(self, patch=None):
        assert patch is None
        PatchFileTreeWidget.__init__(self, patch=None)

class CombinedPatchFileTreeView(PatchFileTreeView):
    UI_DESCR = '''
    <ui>
      <popup name="files_popup">
        <separator/>
          <menuitem action='patch_edit_files'/>
        <separator/>
          <menuitem action='combined_patch_diff_selected_file'/>
        <separator/>
      </popup>
    </ui>
    '''
    def _get_file_db(self):
        return ifce.PM.get_combined_patch_file_db()
    def __init__(self, patch=None, **kwargs):
        assert patch is None
        PatchFileTreeView.__init__(self, patch=None, **kwargs)
    def populate_action_groups(self):
        PatchFileTreeView.populate_action_groups(self)
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('combined_patch_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the combined diff for selected file'),
                 lambda _action=None: self.pm_combined_diff_selected_file()
                ),
            ])
    def pm_combined_diff_selected_file(self):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        dialog = diff.CombinedForFileDialog(filepath=filepaths[0])
        dialog.show()

class CombinedPatchFileTreeWidget(PatchFileTreeWidget):
    TREE_VIEW = CombinedPatchFileTreeView

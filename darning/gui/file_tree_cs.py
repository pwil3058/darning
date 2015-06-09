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

from .. import patch_db

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
from .file_tree_managed import DeleteCopyRenameMixin

class PatchFileTreeView(file_tree.FileTreeView, DeleteCopyRenameMixin):
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
    def __init__(self, patch=None):
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
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('patch_edit_files', gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Edit the selected file(s)'), self.edit_selected_files_acb),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the diff for selected file'), self.diff_selected_file_acb),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_extdiff_selected_file', icons.STOCK_DIFF, _('E_xtDiff'), None,
                 _('Launch external diff viewer for selected file'), self.extdiff_selected_file_acb),
                ('copy_file_to_top_patch', gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'), self._copy_selected_to_top_patch),
                ('rename_file_in_top_patch', icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'), self._rename_selected_in_top_patch),
            ])
        self.add_notification_cb(ws_event.CHECKOUT|ws_event.CHANGE_WD|ws_event.PATCH_PUSH|ws_event.PATCH_POP, self.repopulate)
        self.add_notification_cb(ws_event.FILE_CHANGES|ws_event.PATCH_REFRESH, self.update)
    def edit_selected_files_acb(self, _action):
        file_list = self.get_selected_filepaths()
        text_edit.edit_files_extern(file_list)
    def diff_selected_file_acb(self, _action):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        dialog = diff.ForFileDialog(filepath=filepaths[0], patchname=self.patch)
        dialog.show()
    def extdiff_selected_file_acb(self, _action):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        files = ifce.PM.get_extdiff_files_for(filepath=filepaths[0], patchname=self.patch)
        dialogue.report_any_problems(diff.launch_external_diff(files.original_version, files.patched_version))

class PatchFileTreeWidget(gtk.VBox, ws_event.Listener):
    TREE_VIEW = PatchFileTreeView
    def __init__(self, patch=None):
        gtk.VBox.__init__(self)
        ws_event.Listener.__init__(self)
        self.tree = self.TREE_VIEW(patch=patch)
        self.pack_start(gutils.wrap_in_scrolled_window(self.tree), expand=True, fill=True)
        hbox = gtk.HBox()
        for action_name in ["hide_clean_files"]:
            button = gtk.CheckButton()
            action = self.tree.action_groups.get_action(action_name)
            action.connect_proxy(button)
            gutils.set_widget_tooltip_text(button, action.get_property("tooltip"))
            hbox.pack_start(button)
        self.pack_end(hbox, expand=False, fill=False)
        self.show_all()

class TopPatchFileTreeView(PatchFileTreeView):
    UI_DESCR = '''
    <ui>
      <popup name="files_popup">
        <placeholder name="selection_indifferent"/>
        <separator/>
        <placeholder name="selection">
          <menuitem action='patch_edit_files'/>
          <menuitem action='top_patch_drop_selected_files'/>
          <menuitem action='top_patch_delete_selected_files'/>
        </placeholder>
        <separator/>
        <placeholder name="selection_not_patched"/>
        <separator/>
        <placeholder name="unique_selection"/>
          <menuitem action='copy_file_to_top_patch'/>
          <menuitem action='rename_file_in_top_patch'/>
          <menuitem action='patch_reconcile_selected_file'/>
          <menuitem action='patch_diff_selected_file'/>
          <menuitem action='patch_extdiff_selected_file'/>
        <separator/>
        <placeholder name="no_selection"/>
        <separator/>
        <placeholder name="no_selection_not_patched"/>
        <separator/>
      </popup>
    </ui>
    '''
    def __init__(self, patch=None):
        assert patch is None
        PatchFileTreeView.__init__(self, patch=None)
    def populate_action_groups(self):
        PatchFileTreeView.populate_action_groups(self)
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('top_patch_drop_selected_files', gtk.STOCK_REMOVE, _('_Drop'), None,
                 _('Drop/remove the selected files from the top patch'), self._drop_selection_from_patch),
                ('top_patch_delete_selected_files', gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Delete the selected files'), self._delete_selection_in_top_patch),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_reconcile_selected_file', icons.STOCK_MERGE, _('_Reconcile'), None,
                 _('Launch reconciliation tool for the selected file'), self.reconcile_selected_file_acb),
            ])
    def _drop_selection_from_patch(self, _arg):
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
    def reconcile_selected_file_acb(self, _action):
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
        <placeholder name="selection_indifferent"/>
        <separator/>
        <placeholder name="selection">
          <menuitem action='patch_edit_files'/>
        </placeholder>
        <separator/>
        <placeholder name="selection_not_patched"/>
        <separator/>
        <placeholder name="unique_selection"/>
          <menuitem action='patch_combined_diff_selected_file'/>
        <separator/>
        <placeholder name="no_selection"/>
        <separator/>
        <placeholder name="no_selection_not_patched"/>
        <separator/>
      </popup>
    </ui>
    '''
    def _get_file_db(self):
        return ifce.PM.get_combined_patch_file_db()
    def __init__(self, patch=None):
        assert patch is None
        PatchFileTreeView.__init__(self, patch=None)
    def populate_action_groups(self):
        PatchFileTreeView.populate_action_groups(self)
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('patch_combined_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the combined diff for selected file'), self.combined_diff_selected_file_acb),
            ])
    def combined_diff_selected_file_acb(self, _action):
        filepaths = self.get_selected_filepaths()
        assert len(filepaths) == 1
        dialog = diff.CombinedForFileDialog(filepath=filepaths[0])
        dialog.show()

class CombinedPatchFileTreeWidget(PatchFileTreeWidget):
    TREE_VIEW = CombinedPatchFileTreeView

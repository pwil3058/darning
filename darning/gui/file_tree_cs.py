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

from gi.repository import Gtk
from gi.repository import GObject

from ..wsm.gtx import actions
from ..wsm.gtx import dialogue
from ..wsm.gtx import file_tree

from ..wsm.bab import enotify

from ..wsm import pm
from ..wsm.pm_gui import ifce as pm_gui_ifce
from ..wsm.pm_gui import actions as pm_actions
from ..wsm.scm_gui import actions as scm_actions

from ..wsm import wsm_icons

from . import pm_diff
from . import dooph_pm

class _GenericPatchFileTreeView(file_tree.FileTreeView, enotify.Listener, scm_actions.WDListenerMixin, pm_actions.WDListenerMixin):
    def __init__(self, **kwargs):
        file_tree.FileTreeView.__init__(self, **kwargs)
        enotify.Listener.__init__(self)
        scm_actions.WDListenerMixin.__init__(self) 
        pm_actions.WDListenerMixin.__init__(self)

class PatchFileTreeModel(file_tree.FileTreeModel):
    REPOPULATE_EVENTS = pm.E_POP|pm.E_PUSH|pm.E_PATCH_STACK_CHANGES
    UPDATE_EVENTS = pm.E_PATCH_REFRESH|pm.E_FILE_CHANGES
    def auto_update(self, _events_so_far, _args):
        if not self._file_db.is_current:
            self.update(fsdb_reset_only=[self])
        # NB Don't trigger any events as nobody else cares
        return 0
    def _get_file_db(self):
        return pm_gui_ifce.PM.get_patch_file_db(self._view._patch_name)

class PatchFileTreeView(file_tree.FileTreeView):
    MODEL = PatchFileTreeModel
    AUTO_EXPAND = True
    UI_DESCR = \
    '''
    <ui>
      <menubar name="files_menubar">
      </menubar>
      <popup name="files_popup">
        <separator/>
          <menuitem action="pm_patch_diff_selected_files"/>
          <menuitem action="pm_patch_extdiff_selected_file"/>
        <separator/>
          <menuitem action="pm_patch_diff"/>
        <separator/>
      </popup>
    </ui>
    '''
    DIRS_SELECTABLE = False
    def __init__(self, patch_name=None):
        self._patch_name = patch_name
        file_tree.FileTreeView.__init__(self, show_hidden=True, hide_clean=False)
    @property
    def patch_name(self):
        return self._patch_name
    @patch_name.setter
    def patch_name(self, new_patch_name):
        self._patch_name = new_patch_name
        self.repopulate()
    def populate_action_groups(self):
        self.action_groups[pm_actions.AC_IN_PM_PGND + pm_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('pm_patch_diff_selected_files', wsm_icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the diff for selected files'),
                 lambda _action=None: pm_diff.NamedPatchDiffPlusesDialog(patch_name=self._patch_name, file_paths=self.get_selected_fsi_paths()).show()
                ),
            ])
        self.action_groups[pm_actions.AC_IN_PM_PGND + pm_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('pm_patch_extdiff_selected_file', wsm_icons.STOCK_DIFF, _('E_xtDiff'), None,
                 _('Launch external diff viewer for selected file'),
                 lambda _action=None: dooph_pm.pm_do_extdiff_for_file(self.get_selected_fsi_path(), patch_name=self._patch_name)
                ),
            ])
        self.action_groups[pm_actions.AC_IN_PM_PGND].add_actions(
            [
                ("menu_files", None, _('_Files')),
            ])

class PatchFilesDialog(dialogue.ListenerDialog, enotify.Listener):
    def __init__(self, patch_name):
        dialogue.ListenerDialog.__init__(self, None, None,
                                       Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                       (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        enotify.Listener.__init__(self)
        self.set_title(_('patch: %s files: %s') % (patch_name, utils.cwd_rel_home()))
        self.add_notification_cb(enotify.E_CHANGE_WD, self._chwd_cb)
        # file tree view wrapped in scrolled window
        self.file_tree = PatchFileTreeView(patch_name=patch_name)
        self.file_tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.file_tree.set_headers_visible(False)
        self.file_tree.set_size_request(240, 320)
        self.vbox.pack_start(gutils.wrap_in_scrolled_window(self.file_tree), expand=True, fill=True, padding=0)
        self.connect("response", self._close_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        self.destroy()
    def _chwd_cb(self, **kwargs):
        self.destroy()


class TopPatchFileTreeModel(file_tree.FileTreeModel):
    REPOPULATE_EVENTS = enotify.E_CHANGE_WD|pm.E_NEW_PM|pm.E_PATCH_STACK_CHANGES|pm.E_PUSH|pm.E_POP|pm.E_NEW_PATCH
    UPDATE_EVENTS = pm.E_FILE_CHANGES|pm.E_PATCH_REFRESH
    @staticmethod
    def _get_file_db():
        return pm_gui_ifce.PM.get_top_patch_file_db()
    def auto_update(self, events_so_far, args):
        if (events_so_far & (self.REPOPULATE_EVENTS|self.UPDATE_EVENTS)) or self._file_db.is_current:
            return 0
        if self._file_db.applied_patch_count_change < 0:
            return pm.E_POP
        elif self._file_db.applied_patch_count_change > 0:
            return pm.E_PUSH
        else:
            try:
                args["fsdb_reset_only"].append(self)
            except KeyError:
                args["fsdb_reset_only"] = [self]
        return pm.E_FILE_CHANGES

class TopPatchFileTreeView(_GenericPatchFileTreeView):
    MODEL = TopPatchFileTreeModel
    AUTO_EXPAND = True
    UI_DESCR = \
    '''
    <ui>
      <popup name="files_popup">
        <separator/>
          <menuitem action="pm_edit_files"/>
          <menuitem action="pm_drop_selected_files"/>
          <menuitem action="pm_delete_selected_files"/>
        <separator/>
          <menuitem action="pm_copy_file"/>
          <menuitem action="pm_rename_file"/>
          <menuitem action="pm_reconcile_selected_file"/>
        <separator/>
          <menuitem action="pm_diff_selected_files"/>
          <menuitem action="pm_extdiff_selected_file"/>
        <separator/>
      </popup>
    </ui>
    '''
    DIRS_SELECTABLE = False
    def __init__(self, **kwargs):
        _GenericPatchFileTreeView.__init__(self, **kwargs)
    def populate_action_groups(self):
        self.action_groups[pm_actions.AC_IN_PM_PGND + pm_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('pm_edit_files', Gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Edit the selected file(s)'),
                 lambda _action=None: dooph_pm.pm_do_edit_files(self.get_selected_fsi_paths())
                ),
                ('pm_diff_selected_files', wsm_icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the diff for selected files'),
                 lambda _action=None: pm_diff.TopPatchDiffPlusesDialog(file_paths=self.get_selected_fsi_paths()).show()
                ),
                ('pm_drop_selected_files', Gtk.STOCK_REMOVE, _('_Drop'), None,
                 _('Drop/remove the selected files from the top patch'),
                 lambda _action=None: dooph_pm.pm_do_drop_files(self.get_selected_fsi_paths())
                ),
                ('pm_delete_selected_files', Gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Delete the selected files'),
                 lambda _action=None: dooph_pm.pm_do_delete_files(self.get_selected_fsi_paths())
                ),
            ])
        self.action_groups[pm_actions.AC_IN_PM_PGND + pm_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('pm_reconcile_selected_file', wsm_icons.STOCK_MERGE, _('_Reconcile'), None,
                 _('Launch reconciliation tool for the selected file'),
                 lambda _action=None: dooph_pm.pm_do_reconcile_file(self.get_selected_fsi_path())
                ),
                ('pm_copy_file', Gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'),
                 lambda _action=None: dooph_pm.pm_do_copy_file(self.get_selected_fsi_path())
                ),
                ('pm_rename_file', wsm_icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'),
                 lambda _action=None: dooph_pm.pm_do_rename_file(self.get_selected_fsi_path())
                ),
                ('pm_extdiff_selected_file', wsm_icons.STOCK_DIFF, _('E_xtDiff'), None,
                 _('Launch external diff viewer for selected file'),
                 lambda _action=None: dooph_pm.pm_do_extdiff_for_file(self.get_selected_fsi_path(), patch_name=None)
                ),
            ])

class TopPatchFileTreeWidget(file_tree.FileTreeWidget):
    MENUBAR = None
    BUTTON_BAR_ACTIONS = ["hide_clean_files"]
    TREE_VIEW = TopPatchFileTreeView
    SIZE = (240, 320)
    @staticmethod
    def get_menu_prefix():
        return pm_gui_ifce.PM.name

class CombinedPatchFileTreeModel(TopPatchFileTreeModel):
    @staticmethod
    def _get_file_db():
        return pm_gui_ifce.PM.get_combined_patch_file_db()

class CombinedPatchFileTreeView(TopPatchFileTreeView):
    MODEL = CombinedPatchFileTreeModel
    UI_DESCR = \
    '''
    <ui>
      <popup name="files_popup">
        <separator/>
          <menuitem action='pm_edit_files'/>
        <separator/>
          <menuitem action='combined_patch_diff_selected_files'/>
        <separator/>
      </popup>
    </ui>
    '''
    DIRS_SELECTABLE = False
    def populate_action_groups(self):
        self.action_groups[pm_actions.AC_IN_PM_PGND + pm_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('combined_patch_diff_selected_files', wsm_icons.STOCK_DIFF, _('_Diff'), None,
                 _('Display the combined diff for selected file'),
                 lambda _action=None: pm_diff.CombinedPatchDiffPlusesDialog(file_paths=self.get_selected_fsi_paths()).show()
                ),
            ])

class CombinedPatchFileTreeWidget(TopPatchFileTreeWidget):
    TREE_VIEW = CombinedPatchFileTreeView

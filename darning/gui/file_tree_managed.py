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

import os

import gtk

from ..cmd_result import CmdFailure

from .. import os_utils
from .. import scm_ifce
from .. import pm_ifce

from . import gutils
from . import ifce
from . import actions
from . import ws_actions
from . import ws_event
from . import icons
from . import text_edit
from . import file_tree
from . import dialogue
from . import dooph_pm
#          <menuitem action='peruse_files'/>
#          <menuitem action='pm_copy_files_to_top_patch'/>
#          <menuitem action='pm_move_files_in_top_patch'/>

class WSTreeView(file_tree.FileTreeView):
    UPDATE_EVENTS = os_utils.E_FILE_CHANGES|ifce.E_NEW_SCM|scm_ifce.E_FILE_CHANGES|pm_ifce.E_FILE_CHANGES|pm_ifce.E_PATCH_STACK_CHANGES|pm_ifce.E_PATCH_REFRESH|pm_ifce.E_POP|pm_ifce.E_PUSH|scm_ifce.E_WD_CHANGES
    AU_FILE_CHANGE_EVENT = scm_ifce.E_FILE_CHANGES|os_utils.E_FILE_CHANGES # event returned by auto_update() if changes found
    UI_DESCR = \
    '''
    <ui>
      <menubar name="scm_files_menubar">
        <menu name="scm_files_menu" action="scm_files_menu_files">
          <menuitem action="refresh_files"/>
        </menu>
      </menubar>
      <popup name="files_popup">
          <menuitem action="edit_files"/>
        <separator/>
          <menuitem action="copy_files_selection"/>
          <menuitem action="move_files_selection"/>
          <menuitem action="rename_file"/>
        <separator/>
          <menuitem action="delete_files"/>
        <separator/>
      </popup>
      <popup name="scmic_files_popup"/>
      <popup name="pmic_files_popup">
        <separator/>
          <menuitem action='pm_edit_files_in_top_patch'/>
        <separator/>
          <menuitem action='pm_add_files_to_top_patch'/>
          <menuitem action='pm_move_files_in_top_patch'/>
          <menuitem action='pm_delete_files_in_top_patch'/>
        <separator/>
        <separator/>
          <menuitem action='pm_copy_file_to_top_patch'/>
          <menuitem action='pm_rename_file_in_top_patch'/>
        <separator/>
          <menuitem action='pm_select_unsettled'/>
        <separator/>
      </popup>
    </ui>
    '''
    DEFAULT_POPUP = "/pmic_files_popup"
    def __init__(self, busy_indicator=None, show_hidden=False, hide_clean=False):
        file_tree.FileTreeView.__init__(self, busy_indicator=busy_indicator, show_hidden=show_hidden, hide_clean=hide_clean)
        self._update_popup_cb()
        self.add_notification_cb(pm_ifce.E_PATCH_STACK_CHANGES|ifce.E_NEW_PM|ifce.E_CHANGE_WD, self._update_popup_cb)
    def _update_popup_cb(self, **kwargs):
        if ifce.PM.is_poppable:
            self.set_popup("/pmic_files_popup")
        elif ifce.SCM.in_valid_pgnd:
            self.set_popup("/scmic_files_popup")
        else:
            self.set_popup(self.DEFAULT_POPUP)
    def populate_action_groups(self):
        file_tree.FileTreeView.populate_action_groups(self)
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("scm_files_menu_files", None, _("_Files")),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('pm_add_files_to_top_patch', gtk.STOCK_ADD, _('_Add'), None,
                 _('Add the selected files to the top patch'),
                 lambda _action=None: dooph_pm.pm_do_add_files(self.get_selected_filepaths())
                ),
                ('pm_move_files_in_top_patch', icons.STOCK_RENAME, _('_Move'), None,
                 _('Move the selected files within the top patch'),
                 lambda _action=None: dooph_pm.pm_do_move_files(self.get_selected_filepaths())
                ),
                ('pm_edit_files_in_top_patch', gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Open the selected files for editing after adding them to the top patch'),
                 lambda _action=None: dooph_pm.pm_do_edit_files(self.get_selected_filepaths())
                ),
                ('pm_delete_files_in_top_patch', gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Add the selected files to the top patch and then delete them'),
                 lambda _action=None: dooph_pm.pm_do_delete_files(self.get_selected_filepaths())
                ),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('pm_copy_file_to_top_patch', gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'),
                 lambda _action=None: dooph_pm.pm_do_copy_file(self.get_selected_filepath())
                ),
                ('pm_rename_file_in_top_patch', icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'),
                 lambda _action=None: dooph_pm.pm_do_rename_file(self.get_selected_filepath())
                ),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC].add_actions(
            [
                ('pm_select_unsettled', None, _('Select _Unsettled'), None,
                 _('Select files that are unrefreshed in patches below top or have uncommitted SCM changes not covered by an applied patch'),
                 lambda _action=None: self.pm_select_unsettled()
                ),
            ])
    @staticmethod
    def _get_file_db():
        return ifce.SCM.get_ws_file_db()
    @classmethod
    def _get_status_deco(cls, status=None):
        try:
            return ifce.SCM.get_status_deco(status)
        except:
            return ifce.SCM.get_status_deco(None)
    def pm_select_unsettled(self):
        unsettled = ifce.PM.get_outstanding_changes_below_top()
        filepaths = [filepath for filepath in unsettled.unrefreshed]
        filepaths += [filepath for filepath in unsettled.uncommitted]
        self.select_filepaths(filepaths)

class WSFilesWidget(file_tree.FileTreeWidget):
    MENUBAR = "/scm_files_menubar"
    BUTTON_BAR_ACTIONS = ["show_hidden_files", "hide_clean_files"]
    TREE_VIEW = WSTreeView
    SIZE = (240, 320)
    @staticmethod
    def get_menu_prefix():
        return ifce.SCM.name

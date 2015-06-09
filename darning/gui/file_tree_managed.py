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

from .. import fsdb
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

class DeleteCopyRenameMixin(object):
    def _delete_selection_in_top_patch(self, _action=None):
        file_list = self.get_selected_filepaths()
        if len(file_list) == 0:
            return
        dialogue.show_busy()
        result = ifce.PM.do_delete_files_in_top_patch(file_list)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
    def _copy_selected_to_top_patch(self, _action=None):
        file_list = self.get_selected_filepaths()
        assert len(file_list) == 1
        filepath = file_list[0]
        overwrite = False
        PROMPT = _('Enter target path for copy of "{0}"'.format(filepath))
        as_filepath = dialogue.ask_file_name(PROMPT, existing=False, suggestion=filepath)
        if as_filepath is None or os.path.relpath(as_filepath) == filepath:
            return
        while True:
            dialogue.show_busy()
            result = ifce.PM.do_copy_file_to_top_patch(filepath, as_filepath, overwrite=overwrite)
            dialogue.unshow_busy()
            if result.suggests_rename:
                resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
                if resp == gtk.RESPONSE_CANCEL:
                    break
                elif resp == dialogue.Response.OVERWRITE:
                    overwrite = True
                elif resp == dialogue.Response.RENAME:
                    as_filepath = dialogue.ask_file_name(PROMPT, existing=False)
                    if as_filepath is None:
                        break
                continue
            dialogue.report_any_problems(result)
            break
    def _rename_selected_in_top_patch(self, _action=None):
        file_list = self.get_selected_filepaths()
        assert len(file_list) == 1
        filepath = file_list[0]
        force = False
        overwrite = False
        refresh_tried = False
        PROMPT = _('Enter new path for "{0}"'.format(filepath))
        new_filepath = dialogue.ask_file_name(PROMPT, existing=False, suggestion=filepath)
        if new_filepath is None or os.path.relpath(new_filepath) == filepath:
            return
        while True:
            dialogue.show_busy()
            result = ifce.PM.do_rename_file_in_top_patch(filepath, new_filepath, force=force, overwrite=overwrite)
            dialogue.unshow_busy()
            if refresh_tried:
                result = result - result.SUGGEST_REFRESH
            if not force and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
                resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
                if resp == gtk.RESPONSE_CANCEL:
                    break
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.REFRESH:
                    refresh_tried = True
                    result = ifce.PM.do_refresh_overlapped_files([filepath])
                    dialogue.report_any_problems(result)
                continue
            elif result.suggests_rename:
                resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
                if resp == gtk.RESPONSE_CANCEL:
                    break
                elif resp == dialogue.Response.OVERWRITE:
                    overwrite = True
                elif resp == dialogue.Response.RENAME:
                    new_filepath = dialogue.ask_file_name(PROMPT, existing=False)
                    if new_filepath is None:
                        break
                continue
            dialogue.report_any_problems(result)
            break

class WSTreeView(file_tree.FileTreeView, DeleteCopyRenameMixin):
    UPDATE_EVENTS = fsdb.E_FILE_CHANGES|ifce.E_NEW_SCM|scm_ifce.E_FILE_CHANGES|pm_ifce.E_FILE_CHANGES|pm_ifce.E_PATCH_STACK_CHANGES|pm_ifce.E_PATCH_REFRESH|pm_ifce.E_POP|pm_ifce.E_PUSH|scm_ifce.E_WD_CHANGES
    AU_FILE_CHANGE_EVENT = scm_ifce.E_FILE_CHANGES|fsdb.E_FILE_CHANGES # event returned by auto_update() if changes found
    UI_DESCR = '''
    <ui>
      <menubar name="scm_files_menubar">
        <menu name="scm_files_menu" action="scm_files_menu_files">
          <menuitem action="refresh_files"/>
        </menu>
      </menubar>
      <popup name="files_popup">
        <placeholder name="selection_indifferent"/>
        <separator/>
        <placeholder name="selection">
          <menuitem action='scm_add_files_to_top_patch'/>
          <menuitem action='scm_edit_files_in_top_patch'/>
          <menuitem action='scm_delete_files_in_top_patch'/>
        </placeholder>
        <separator/>
        <placeholder name="selection_not_patched"/>
        <separator/>
        <placeholder name="unique_selection"/>
          <menuitem action='copy_file_to_top_patch'/>
          <menuitem action='rename_file_in_top_patch'/>
        <separator/>
        <placeholder name="no_selection"/>
        <separator/>
        <placeholder name="no_selection_not_patched"/>
          <menuitem action='scm_select_unsettled'/>
        <separator/>
        <separator/>
        <placeholder name="make_selections"/>
        <separator/>
      </popup>
    </ui>
    '''
    _FILE_ICON = {True : gtk.STOCK_DIRECTORY, False : gtk.STOCK_FILE}
    def __init__(self, busy_indicator=None, show_hidden=False, hide_clean=False):
        file_tree.FileTreeView.__init__(self, busy_indicator=busy_indicator, show_hidden=show_hidden, hide_clean=hide_clean)
    def populate_action_groups(self):
        file_tree.FileTreeView.populate_action_groups(self)
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ('scm_files_menu_files', None, _('_Files')),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_MADE].add_actions(
            [
                ('scm_add_files_to_top_patch', gtk.STOCK_ADD, _('_Add'), None,
                 _('Add the selected files to the top patch'), self._add_selection_to_top_patch),
                ('scm_edit_files_in_top_patch', gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Open the selected files for editing after adding them to the top patch'), self._edit_selection_in_top_patch),
                ('scm_delete_files_in_top_patch', gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Add the selected files to the top patch and then delete them'), self._delete_selection_in_top_patch),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND_MUTABLE + ws_actions.AC_PMIC + actions.AC_SELN_UNIQUE].add_actions(
            [
                ('copy_file_to_top_patch', gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'), self._copy_selected_to_top_patch),
                ('rename_file_in_top_patch', icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'), self._rename_selected_in_top_patch),
            ])
        self.action_groups[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC].add_actions(
            [
                ('scm_select_unsettled', None, _('Select _Unsettled'), None,
                 _('Select files that are unrefreshed in patches below top or have uncommitted SCM changes not covered by an applied patch'),
                 self._select_unsettled),
            ])
    @staticmethod
    def _add_files_to_top_patch(file_list):
        absorb = False
        force = False
        refresh_tried = False
        while True:
            dialogue.show_busy()
            result = ifce.PM.do_add_files_to_top_patch(file_list, absorb=absorb, force=force)
            dialogue.unshow_busy()
            if refresh_tried:
                result = result - result.SUGGEST_REFRESH
            if not (absorb or force) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
                resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
                if resp == gtk.RESPONSE_CANCEL:
                    break
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.ABSORB:
                    absorb = True
                elif resp == dialogue.Response.REFRESH:
                    refresh_tried = True
                    result = ifce.PM.do_refresh_overlapped_files(file_list)
                    dialogue.report_any_problems(result)
                continue
            dialogue.report_any_problems(result)
            break
        return result.is_ok
    def _add_selection_to_top_patch(self, _action=None):
        file_list = self.get_selected_filepaths()
        if len(file_list) == 0:
            return
        self._add_files_to_top_patch(file_list)
    @staticmethod
    def _get_file_db():
        return ifce.SCM.get_ws_file_db()
    @classmethod
    def _get_status_deco(cls, status=None):
        try:
            return ifce.SCM.get_status_deco(status)
        except:
            return ifce.SCM.get_status_deco(None)
    def _edit_selection_in_top_patch(self, _action=None):
        file_list = self.get_selected_filepaths()
        if len(file_list) == 0:
            return
        if self._add_files_to_top_patch(file_list):
            text_edit.edit_files_extern(file_list)
    def _select_unsettled(self, _action=None):
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

class ScmFileTreeWidget(gtk.VBox, ws_event.Listener):
    def __init__(self, hide_clean=False):
        gtk.VBox.__init__(self)
        ws_event.Listener.__init__(self)
        hbox = gtk.HBox()
        name = ifce.SCM.name
        self.scm_label = gtk.Label('' if not name else (name + ':'))
        self.tree = WSTreeView(hide_clean=hide_clean)
        hbox.pack_start(self.scm_label, expand=False, fill=False)
        hbox.pack_start(self.tree.ui_manager.get_widget('/scm_files_menubar'), expand=True, fill=True)
        self.pack_start(hbox, expand=False, fill=False)
        self.pack_start(gutils.wrap_in_scrolled_window(self.tree), expand=True, fill=True)
        hbox = gtk.HBox()
        for action_name in ['show_hidden_files', 'hide_clean_files']:
            button = gtk.CheckButton()
            action = self.tree.action_groups.get_action(action_name)
            action.connect_proxy(button)
            gutils.set_widget_tooltip_text(button, action.get_property('tooltip'))
            hbox.pack_start(button)
        self.pack_end(hbox, expand=False, fill=False)
        self.show_all()
        self.add_notification_cb(ws_event.CHANGE_WD, self._cwd_change_cb)
    def _cwd_change_cb(self):
        name = ifce.SCM.get_name()
        self.scm_label.set_text('' if not name else (name + ':'))

def add_new_file_to_top_patch_acb(_action=None):
    filepath = dialogue.ask_file_name(_('Enter path for new file'), existing=False)
    if not filepath:
        return
    WSTreeView._add_files_to_top_patch([filepath])


actions.CLASS_INDEP_AGS[ws_actions.AC_PMIC | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("file_list_add_new", gtk.STOCK_NEW, _('New'), None,
         _('Add a new file to the top applied patch'), add_new_file_to_top_patch_acb),
    ])

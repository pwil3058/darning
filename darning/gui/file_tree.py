### Copyright (C) 2005-2016 Peter Williams <pwil3058@gmail.com>
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

import collections
import os
import os.path

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from ..cmd_result import CmdResult, CmdFailure

from .. import utils
from .. import fsdb
from .. import os_utils
from .. import enotify

from . import tlview
from . import gutils
from . import actions
from . import dialogue
from . import icons
from . import auto_update
from . import xtnl_edit
from . import doop

AC_FILES_SELECTED, AC_NO_FILES_SELECTED, \
AC_DIRS_SELECTED, AC_NO_DIRS_SELECTED, \
AC_FDS_MASK = actions.ActionCondns.new_flags_and_mask(4)
AC_ONLY_FILES_SELECTED = AC_FILES_SELECTED|AC_NO_DIRS_SELECTED
AC_ONLY_DIRS_SELECTED = AC_DIRS_SELECTED|AC_NO_FILES_SELECTED

def get_masked_seln_conditions(seln):
    if seln is None:
        return actions.MaskedCondns(AC_NO_FILES_SELECTED|AC_NO_DIRS_SELECTED, AC_FDS_MASK)
    model, selection = seln.get_selected_rows()
    files_selected = False
    dirs_selected = False
    for model_iter in selection:
        if model[model_iter][0].is_dir:
            dirs_selected |= True
        else:
            files_selected |= True
    if files_selected:
        if dirs_selected:
            return actions.MaskedCondns(AC_FILES_SELECTED|AC_DIRS_SELECTED, AC_FDS_MASK)
        else:
            return actions.MaskedCondns(AC_FILES_SELECTED|AC_NO_DIRS_SELECTED, AC_FDS_MASK)
    elif dirs_selected:
        return actions.MaskedCondns(AC_NO_FILES_SELECTED|AC_DIRS_SELECTED, AC_FDS_MASK)
    else:
        return actions.MaskedCondns(AC_NO_FILES_SELECTED|AC_NO_DIRS_SELECTED, AC_FDS_MASK)

class FileTreeModel(Gtk.TreeStore, enotify.Listener, auto_update.AutoUpdater, actions.BGUserMixin):
    # NB: this model is volatile/lazy and should only have one associated View
    # as the contenst are dependent on the state of the View
    # NB: the use of a Gtk.TreeStoreFilter has been considered as an
    # alternative mechanism for implementing show_hidden/hide_clean has
    # been considered and rejected as being unable to handle empty
    # directories properly
    REPOPULATE_EVENTS = enotify.E_CHANGE_WD
    UPDATE_EVENTS = os_utils.E_FILE_CHANGES
    AU_FILE_CHANGE_EVENT = os_utils.E_FILE_CHANGES # event returned by auto_update() if changes found
    _FILE_ICON = {True : Gtk.STOCK_DIRECTORY, False : Gtk.STOCK_FILE}
    @staticmethod
    def _get_file_db():
        return fsdb.OsFileDb()
    def __init__(self):
        assert (self.REPOPULATE_EVENTS & self.UPDATE_EVENTS) == 0
        self._view = None
        Gtk.TreeStore.__init__(self, GObject.TYPE_PYOBJECT)
        enotify.Listener.__init__(self)
        self.add_notification_cb(self.REPOPULATE_EVENTS, self.repopulate)
        self.add_notification_cb(self.UPDATE_EVENTS, self.update)
        auto_update.AutoUpdater.__init__(self)
        self.register_auto_update_cb(self.auto_update)
        actions.BGUserMixin.__init__(self)
    # Make it safe to use this in a Dialog.
    def _destroy(self, *args):
        self._view = None
        self.auto_updater_destroy_cb(*args)
        self.listener_destroy_cb(*args)
    def set_view(self, view):
        assert not self._view
        self._view = view
        self._view.connect("destroy", self._destroy)
        self._view.connect("row-expanded", self.on_row_expanded_cb)
        self._view.connect("row-collapsed", self.on_row_collapsed_cb)
    def populate_button_group(self):
        self.button_group.add_buttons(
            [
                ("show_hidden_files", Gtk.CheckButton(_("Show Hidden Files")),
                _("Show/hide ignored files and those beginning with \".\""),
                [("toggled", self._toggle_show_buttons_cb),]
                ),
                ("hide_clean_files", Gtk.CheckButton(_("Hide Clean Files")),
                _("Show/hide ignored files and those beginning with \".\""),
                [("toggled", self._toggle_show_buttons_cb),]
                ),
            ])
    @property
    def show_hidden(self):
        return self.button_group["show_hidden_files"].get_active()
    @show_hidden.setter
    def show_hidden(self, new_value):
        self.button_group["show_hidden_files"].set_active(new_value)
        self.update_dir("", None)
    @property
    def hide_clean(self):
        return self.button_group["hide_clean_files"].get_active()
    @hide_clean.setter
    def hide_clean(self, new_value):
        self.button_group["hide_clean_files"].set_active(new_value)
        self.update_dir("", None)
    def _toggle_show_buttons_cb(self, toggleaction):
        self._view.show_busy()
        self.update_dir("", None)
        self._view.unshow_busy()
    def insert_place_holder(self, dir_iter):
        self.append(dir_iter)
    def insert_place_holder_if_needed(self, dir_iter):
        if self.iter_n_children(dir_iter) == 0:
            self.insert_place_holder(dir_iter)
    def recursive_remove(self, fsobj_iter):
        child_iter = self.iter_children(fsobj_iter)
        if child_iter != None:
            while self.recursive_remove(child_iter):
                pass
        return self.remove(fsobj_iter)
    def repopulate(self, **kwargs):
        self._view.show_busy()
        self._file_db = self._get_file_db()
        self.clear()
        self._populate_dir("", self.get_iter_first())
        self._view.unshow_busy()
    def update(self, fsdb_reset_only=False, **kwargs):
        self._view.show_busy()
        self._file_db = self._file_db.reset() if (fsdb_reset_only and self in fsdb_reset_only) else self._get_file_db()
        self.update_dir("", None)
        self._view.unshow_busy()
    def depopulate(self, dir_iter):
        child_iter = self.iter_children(dir_iter)
        if child_iter != None:
            if self.get_value(child_iter, 0) is None:
                return # already depopulated and placeholder in place
            while self.recursive_remove(child_iter):
                pass
        self.insert_place_holder(dir_iter)
    def get_iter_for_filepath(self, filepath):
        # NB: assumes filepath starts with "./"
        pathparts = fsdb.split_path(filepath)[1:]
        child_iter = self.get_iter_first()
        for index in range(len(pathparts) - 1):
            while child_iter is not None:
                if self.get_value(child_iter, 0).name == pathparts[index]:
                    tpath = self.get_path(child_iter)
                    if not self._view.row_expanded(tpath):
                        self._view.expand_row(tpath, False)
                    child_iter = self.iter_children(child_iter)
                    break
                child_iter = self.iter_next(child_iter)
        while child_iter is not None:
            if self.get_value(child_iter, 0).name == pathparts[-1]:
                return child_iter
            child_iter = self.iter_next(child_iter)
        return None
    def get_file_paths_in_dir(self, dir_path, show_hidden=False, hide_clean=False, recursive=True):
        # TODO: fix get_file_paths_in_dir() -- use model not db
        subdirs, files = self._file_db.dir_contents(dir_path, show_hidden=show_hidden, hide_clean=hide_clean)
        file_paths = [fdata.path for fdata in files]
        if recursive:
            for subdir in subdirs:
                file_paths += self.get_file_paths_in_dir(subdir.path, show_hidden=show_hidden, hide_clean=hide_clean, recursive=recursive)
        return file_paths
    def remove_place_holder(self, dir_iter):
        child_iter = self.iter_children(dir_iter)
        if child_iter and self.get_value(child_iter, 0) is None:
            self.remove(child_iter)
    def _not_yet_populated(self, dir_iter):
        if self.iter_n_children(dir_iter) < 2:
            child_iter = self.iter_children(dir_iter)
            return child_iter is None or self.get_value(child_iter, 0) is None
        return False
    def on_row_expanded_cb(self, view, dir_iter, _dummy):
        if self._not_yet_populated(dir_iter):
            self._populate_dir(self[dir_iter][0].path, dir_iter)
            if self.iter_n_children(dir_iter) > 1:
                self.remove_place_holder(dir_iter)
    def on_row_collapsed_cb(self, _view, dir_iter, _dummy):
        self.insert_place_holder_if_needed(dir_iter)
    def _get_dir_contents(self, dirpath):
        return self._file_db.dir_contents(dirpath, show_hidden=self.show_hidden, hide_clean=self.hide_clean)
    def _populate_dir(self, dirpath, parent_iter):
        dirs, files = self._get_dir_contents(dirpath)
        for dirdata in dirs:
            dir_iter = self.append(parent_iter, [dirdata])
            if self._view.AUTO_EXPAND:
                self._populate_dir(dirdata.path, dir_iter)
                self._view.expand_row(self.get_path(dir_iter), True)
            else:
                self.insert_place_holder(dir_iter)
        for filedata in files:
            dummy = self.append(parent_iter, [filedata])
        if parent_iter is not None:
            self.insert_place_holder_if_needed(parent_iter)
    def update_dir(self, dirpath, parent_iter):
        # TODO: make sure we cater for case where dir becomes file and vice versa in a single update
        changed = False
        place_holder_iter = None
        if parent_iter is None:
            child_iter = self.get_iter_first()
        else:
            child_iter = self.iter_children(parent_iter)
            if child_iter:
                if self.get_value(child_iter, 0) is None:
                    place_holder_iter = child_iter.copy()
                    child_iter = self.iter_next(child_iter)
        dirs, files = self._get_dir_contents(dirpath)
        dead_entries = []
        for dirdata in dirs:
            while (child_iter is not None) and self.get_value(child_iter, 0).is_dir and (self.get_value(child_iter, 0).name < dirdata.name):
                dead_entries.append(child_iter)
                child_iter = self.iter_next(child_iter)
            if child_iter is None:
                dir_iter = self.append(parent_iter, [dirdata])
                changed = True
                if self._view.AUTO_EXPAND:
                    self.update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    self._view.expand_row(self.get_path(dir_iter), True)
                else:
                    self.insert_place_holder(dir_iter)
                continue
            name = self.get_value(child_iter, 0).name
            if (not self.get_value(child_iter, 0).is_dir) or (name > dirdata.name):
                dir_iter = self.insert_before(parent_iter, child_iter, [dirdata])
                changed = True
                if self._view.AUTO_EXPAND:
                    self.update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    self._view.expand_row(self.get_path(dir_iter), True)
                else:
                    self.insert_place_holder(dir_iter)
                continue
            changed |= self.get_value(child_iter, 0) != dirdata
            self.set_value(child_iter, 0, dirdata)
            # This is an update so ignore EXPAND_ALL for existing directories
            # BUT update them if they"re already expanded
            if self._view.row_expanded(self.get_path(child_iter)):
                changed |= self.update_dir(os.path.join(dirpath, name), child_iter)
            else:
                # make sure we don"t leave bad data in children that were previously expanded
                self.depopulate(child_iter)
            child_iter = self.iter_next(child_iter)
        while (child_iter is not None) and self.get_value(child_iter, 0).is_dir:
            dead_entries.append(child_iter)
            child_iter = self.iter_next(child_iter)
        for filedata in files:
            while (child_iter is not None) and (self.get_value(child_iter, 0).name < filedata.name):
                dead_entries.append(child_iter)
                child_iter = self.iter_next(child_iter)
            if child_iter is None:
                dummy = self.append(parent_iter, [filedata])
                changed = True
                continue
            if self.get_value(child_iter, 0).name > filedata.name:
                dummy = self.insert_before(parent_iter, child_iter, [filedata])
                changed = True
                continue
            changed |= self.get_value(child_iter, 0) != filedata
            self.set_value(child_iter, 0, filedata)
            child_iter = self.iter_next(child_iter)
        while child_iter is not None:
            dead_entries.append(child_iter)
            child_iter = self.iter_next(child_iter)
        changed |= len(dead_entries) > 0
        for dead_entry in dead_entries:
            self.recursive_remove(dead_entry)
        if parent_iter is not None:
            n_children = self.iter_n_children(parent_iter)
            if n_children == 0:
                self.insert_place_holder(parent_iter)
            elif place_holder_iter is not None and n_children > 1:
                assert self.get_value(place_holder_iter, 0) is None
                self.remove(place_holder_iter)
        return changed
    def auto_update(self, events_so_far, args):
        if (events_so_far & (self.REPOPULATE_EVENTS|self.UPDATE_EVENTS)) or self._file_db.is_current:
            return 0
        try:
            args["fsdb_reset_only"].append(self)
        except KeyError:
            args["fsdb_reset_only"] = [self]
        return self.AU_FILE_CHANGE_EVENT

def tv_icon_set_func(treeviewcolumn, cell, model, tree_iter, *args):
    file_data = model.get_value(tree_iter, 0)
    if file_data is None:
        cell.set_property("stock_id", None)
    else:
        cell.set_property("stock_id", file_data.icon)

def tf_file_name_set_func(treeviewcolumn, cell, model, tree_iter, *args):
    file_data = model.get_value(tree_iter, 0)
    if file_data is None:
        cell.set_property("text", _("<empty>"))
    else:
        if file_data.is_dir and model.hide_clean:
            cell.set_property("foreground", file_data.clean_deco.foreground)
            cell.set_property("style", file_data.clean_deco.style)
        else:
            cell.set_property("foreground", file_data.deco.foreground)
            cell.set_property("style", file_data.deco.style)
        if file_data.related_file_data:
            cell.set_property("text", " ".join((file_data.name, file_data.related_file_data.relation, file_data.related_file_data.path)))
        else:
            cell.set_property("text", file_data.name)

def tf_status_set_func(treeviewcolumn, cell, model, tree_iter, *args):
    file_data = model.get_value(tree_iter, 0)
    if file_data is None: return
    if file_data.is_dir and model.hide_clean:
        cell.set_property("foreground", file_data.clean_deco.foreground)
        cell.set_property("style", file_data.clean_deco.style)
        cell.set_property("text", file_data.clean_status)
    else:
        cell.set_property("foreground", file_data.deco.foreground)
        cell.set_property("style", file_data.deco.style)
        cell.set_property("text", file_data.status)

def file_tree_view_spec(view, model):
    specification = tlview.ViewSpec(
        properties={"headers-visible" : False},
        selection_mode=Gtk.SelectionMode.MULTIPLE,
        columns=[
            tlview.ColumnSpec(
                title=_("File Name"),
                properties={},
                cells=[
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=Gtk.CellRendererPixbuf,
                            expand=False,
                            start=True,
                            properties={"xalign": 0.0},
                        ),
                        cell_data_function_spec=tlview.CellDataFunctionSpec(function=tv_icon_set_func),
                        attributes={}
                    ),
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=Gtk.CellRendererText,
                            expand=False,
                            start=True,
                            properties={},
                        ),
                        cell_data_function_spec=tlview.CellDataFunctionSpec(function=tf_status_set_func, user_data=None),
                        attributes={}
                    ),
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=Gtk.CellRendererText,
                            expand=False,
                            start=True,
                            properties={},
                        ),
                        cell_data_function_spec=tlview.CellDataFunctionSpec(function=tf_file_name_set_func, user_data=None),
                        attributes={}
                    )
                ]
            )
        ]
    )
    return specification

class FileTreeView(tlview.View, actions.CAGandUIManager, dialogue.BusyIndicatorUser, doop.DoOperationMixin):
    DEFAULT_POPUP = "/files_popup"
    MODEL = FileTreeModel
    SPECIFICATION = file_tree_view_spec
    UI_DESCR = \
    """
    <ui>
      <menubar name="files_menubar">
        <menu name="files_menu" action="menu_files">
         <menuitem action="refresh_files"/>
        </menu>
      </menubar>
      <popup name="files_popup">
          <menuitem action="delete_fs_items"/>
          <menuitem action="new_file"/>
        <separator/>
          <menuitem action="copy_fs_items"/>
          <menuitem action="move_fs_items"/>
          <menuitem action="rename_fs_item"/>
      </popup>
    </ui>
    """
    KEYVAL_c = Gdk.keyval_from_name("c")
    KEYVAL_C = Gdk.keyval_from_name("C")
    KEYVAL_ESCAPE = Gdk.keyval_from_name("Escape")
    AUTO_EXPAND = False
    DIRS_SELECTABLE = True
    ASK_BEFORE_DELETE = True
    OPEN_NEW_FILES_FOR_EDIT = True
    @staticmethod
    def _handle_control_c_key_press_cb(widget, event):
        if event.get_state() & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval in [FileTreeView.KEYVAL_c, FileTreeView.KEYVAL_C]:
                widget.add_selected_fsi_paths_to_clipboard()
                return True
        return False
    @staticmethod
    def _handle_double_click_cb(tree_view, tree_path, tree_column):
        fs_item = tree_view.get_model()[tree_path][0]
        if not fs_item.is_dir:
            xtnl_edit.edit_files_extern([fs_item.path])
    def __init__(self, show_hidden=False, hide_clean=False, busy_indicator=None, parent=None):
        self._parent = parent
        dialogue.BusyIndicatorUser.__init__(self, busy_indicator=busy_indicator)
        tlview.TreeView.__init__(self)
        actions.CAGandUIManager.__init__(self, selection=self.get_selection(), popup=self.DEFAULT_POPUP)
        self.model.set_view(self)
        self.connect("key_press_event", self._handle_control_c_key_press_cb)
        self.connect("row-activated", self._handle_double_click_cb)
        seln = self.get_selection()
        seln.set_select_function(self._selection_filter_func)
        seln.connect('changed', lambda seln: self.action_groups.update_condns(get_masked_seln_conditions(seln)))
        self.model.repopulate()
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("refresh_files", Gtk.STOCK_REFRESH, _("_Refresh Files"), None,
                 _("Refresh/update the file tree display"),
                 lambda _action=None: self.model.update()
                ),
            ])
        self.action_groups[actions.AC_SELN_MADE].add_actions(
            [
                ("copy_fs_items", Gtk.STOCK_COPY, _("Copy"), None,
                 _("Copy the selected file(s) and/or directories"),
                 lambda _action: self._move_or_copy_fs_items(True, self.get_selected_fsi_paths())
                ),
                ("move_fs_items", Gtk.STOCK_PASTE, _("_Move/Rename"), None,
                 _("Move the selected file(s) and/or directories"),
                 lambda _action: self._move_or_copy_fs_items(False, self.get_selected_fsi_paths())
                ),
                ("delete_fs_items", Gtk.STOCK_DELETE, _("_Delete"), None,
                 _("Delete the selected file(s) and/or directories"),
                 lambda _action=None: self.delete_selected_fs_items()
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE].add_actions(
           [
                ("rename_fs_item", icons.STOCK_RENAME, _("Rename/Move"), None,
                 _("Rename/move the selected file or directory"),
                 lambda _action: self._move_or_copy_fs_item(False, self.get_selected_fsi_path())
                ),
            ])
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("new_file", Gtk.STOCK_NEW, _("_New"), None,
                 _("Create a new file"),
                 lambda _action: self.create_new_file()
                ),
            ])
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("menu_files", None, _("_Files")),
            ])
    @classmethod
    def _selection_filter_func(cls, selection, model, path, is_selected, *args,**kwargs):
        if is_selected:
            return True
        elif cls.DIRS_SELECTABLE:
            # don't allow place holders to be selected
            return model[path][0] is not None
        else:
            return model[path][0] and not model[path][0].is_dir
    def select_filepaths(self, filepaths):
        seln = self.get_selection()
        seln.unselect_all()
        for filepath in filepaths:
            seln.select_iter(self.model.get_iter_for_filepath(filepath))
    def get_selected_fsi_path(self):
        store, selection = self.get_selection().get_selected_rows()
        assert len(selection) == 1
        return store[selection[0]][0].path
    def get_selected_file_paths(self, expanded=True):
        store, selection = self.get_selection().get_selected_rows()
        file_path_list = list()
        for x in selection:
            if store[x][0].is_dir:
                if expanded:
                    file_path_list += self.model.get_file_paths_in_dir(store[x][0].path, show_hidden=store.show_hidden, hide_clean=store.hide_clean, recursive=True)
            else:
                file_path_list.append(store[x][0].path)
        return file_path_list
    def get_selected_fsi_paths(self):
        store, selection = self.get_selection().get_selected_rows()
        return [store[x][0].path for x in selection]
    def add_selected_fsi_paths_to_clipboard(self, clipboard=None):
        if not clipboard:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        sel = utils.quoted_join(self.get_selected_fsi_paths())
        clipboard.set_text(sel, len(sel))
    def create_new_file(self):
        selected_fs_item_paths = self.get_selected_fsi_paths()
        suggestion = None
        if len(selected_fs_item_paths) == 1:
            dir_path = selected_fs_item_paths[0] if os.path.isdir(selected_fs_item_paths[0]) else os.path.dirname(selected_fs_item_paths[0])
            if dir_path:
                suggestion = os.path.join(dir_path, "")
        new_file_path = dialogue.ask_file_path(_("New File Path"), suggestion=suggestion, existing=False, parent=self._parent)
        if new_file_path:
            self.show_busy()
            result = os_utils.os_create_file(new_file_path)
            self.unshow_busy()
            dialogue.report_any_problems(result)
            if self.OPEN_NEW_FILES_FOR_EDIT:
                xtnl_edit.edit_files_extern([new_file_path])
            dialogue.report_any_problems(result, parent=self._parent)
    def delete_selected_fs_items(self):
        fsi_paths = self.get_selected_fsi_paths()
        if self.ASK_BEFORE_DELETE and not dialogue.confirm_list_action(fsi_paths, _("About to be deleted. OK?")):
            return
        force = False
        while True:
            self.show_busy()
            result = os_utils.os_delete_fs_items(fsi_paths, force=force)
            self.unshow_busy()
            if not force and result.suggests_force:
                if dialogue.ask_force_or_cancel(result, parent=self._parent) == dialogue.Response.FORCE:
                    force = True
                    fsi_paths = [fsi_path for fsi_path in fsi_paths if os.path.exists(fsi_path)]
                    continue
                else:
                    break
            dialogue.report_any_problems(result, parent=self._parent)
            break
    def _move_or_copy_fs_items(self, do_copy, fsi_paths):
        if len(fsi_paths) == 1:
            return self._move_or_copy_fs_item(do_copy, fsi_paths[0])
        get_target = lambda suggestion=None, parent=self._parent: dialogue.ask_dir_path(_("Target Directory Path"), suggestion=suggestion, parent=parent)
        target = get_target()
        if target:
            do_op = os_utils.os_copy_fs_items if do_copy else os_utils.os_move_fs_items
            return self.do_op_rename_overwrite_force_or_cancel(fsi_paths, target, do_op, get_target)
        return CmdResult.ok()
    def _move_or_copy_fs_item(self, do_copy, fsi_path):
        get_target = lambda suggestion, parent=self._parent: dialogue.ask_file_path(_("New Path"), suggestion=suggestion, parent=parent)
        target = get_target(fsi_path)
        if target:
            do_op = os_utils.os_copy_fs_item if do_copy else os_utils.os_move_fs_item
            return self.do_op_rename_overwrite_force_or_cancel(fsi_path, target, do_op, get_target)
        return CmdResult.ok()

class FileTreeWidget(Gtk.VBox, enotify.Listener):
    MENUBAR = "/files_menubar"
    BUTTON_BAR_ACTIONS = ["show_hidden_files"]
    TREE_VIEW = FileTreeView
    SIZE = (120, 60)
    def __init__(self, show_hidden=False, hide_clean=False, **kwargs):
        Gtk.VBox.__init__(self)
        enotify.Listener.__init__(self)
        # file tree view wrapped in scrolled window
        self.file_tree = self.TREE_VIEW(show_hidden=show_hidden, hide_clean=hide_clean, **kwargs)
        self.file_tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.file_tree.set_headers_visible(False)
        self.file_tree.set_size_request(*self.SIZE)
        scw = gutils.wrap_in_scrolled_window(self.file_tree, use_widget_size=True)
        # file tree menu bar
        mprefix = self.get_menu_prefix()
        self.menu_prefix = Gtk.Label(label="" if not mprefix else (mprefix + ":"))
        if self.MENUBAR:
            hbox = Gtk.HBox()
            self.pack_start(hbox, expand=False, fill=False, padding=0)
            hbox.pack_start(self.menu_prefix, expand=False, fill=False, padding=0)
            self.menu_bar = self.file_tree.ui_manager.get_widget(self.MENUBAR)
            hbox.pack_start(self.menu_bar, expand=False, fill=True, padding=0)
        self.pack_start(scw, expand=True, fill=True, padding=0)
        # Mode selectors
        button_box = self.file_tree.model.button_group.create_button_box(self.BUTTON_BAR_ACTIONS)
        self.pack_start(button_box, expand=False, fill=True, padding=0)
        self.add_notification_cb(enotify.E_CHANGE_WD, self._cwd_change_cb)
        self.show_all()
    @staticmethod
    def get_menu_prefix():
        return None
    def _cwd_change_cb(self, **kwargs):
        mprefix = self.get_menu_prefix()
        self.menu_prefix.set_text("" if not mprefix else (mprefix + ":"))

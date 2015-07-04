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

import collections
import os
import os.path

import gtk
import gobject

from ..cmd_result import CmdResult, CmdFailure

from .. import utils
from .. import fsdb
from .. import os_utils
from .. import scm_ifce
from .. import pm_ifce

from . import tlview
from . import gutils
from . import ifce
from . import actions
from . import ws_actions
from . import dialogue
from . import ws_event
from . import icons
from . import text_edit
from . import auto_update
from . import console

def _check_if_force(result):
    return dialogue.ask_force_or_cancel(result) == dialogue.Response.FORCE

class FileTreeView(tlview.TreeView, ws_actions.AGandUIManager, ws_event.Listener, dialogue.BusyIndicatorUser, auto_update.AutoUpdater):
    REPOPULATE_EVENTS = ifce.E_CHANGE_WD
    UPDATE_EVENTS = os_utils.E_FILE_CHANGES
    AU_FILE_CHANGE_EVENT = os_utils.E_FILE_CHANGES # event returned by auto_update() if changes found
    DEFAULT_POPUP = "/files_popup"
    class Model(tlview.TreeView.Model):
        Row = collections.namedtuple('Row', ['name', 'is_dir', 'style', 'foreground', 'icon', 'status', 'related_file_data'])
        types = Row(
            name=gobject.TYPE_STRING,
            is_dir=gobject.TYPE_BOOLEAN,
            style=gobject.TYPE_INT,
            foreground=gobject.TYPE_STRING,
            icon=gobject.TYPE_STRING,
            status=gobject.TYPE_STRING,
            related_file_data=gobject.TYPE_PYOBJECT
        )
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
        def depopulate(self, dir_iter):
            child_iter = self.iter_children(dir_iter)
            if child_iter != None:
                if self.get_value_named(child_iter, "name") is None:
                    return # already depopulated and placeholder in place
                while self.recursive_remove(child_iter):
                    pass
            self.insert_place_holder(dir_iter)
        def remove_place_holder(self, dir_iter):
            child_iter = self.iter_children(dir_iter)
            if child_iter and self.get_value_named(child_iter, "name") is None:
                self.remove(child_iter)
        def fs_path(self, fsobj_iter):
            if fsobj_iter is None:
                return None
            parent_iter = self.iter_parent(fsobj_iter)
            name = self.get_value_named(fsobj_iter, "name")
            if parent_iter is None:
                return name
            else:
                if name is None:
                    return os.path.join(self.fs_path(parent_iter), '')
                return os.path.join(self.fs_path(parent_iter), name)
        def _not_yet_populated(self, dir_iter):
            if self.iter_n_children(dir_iter) < 2:
                child_iter = self.iter_children(dir_iter)
                return child_iter is None or self.get_value_named(child_iter, "name") is None
            return False
        def on_row_expanded_cb(self, view, dir_iter, _dummy):
            if self._not_yet_populated(dir_iter):
                view._populate(self.fs_path(dir_iter), dir_iter)
                if self.iter_n_children(dir_iter) > 1:
                    self.remove_place_holder(dir_iter)
        def on_row_collapsed_cb(self, _view, dir_iter, _dummy):
            self.insert_place_holder_if_needed(dir_iter)
        def update_iter_row_tuple(self, fsobj_iter, to_tuple):
            for label in ["style", "foreground", "status", "related_file_data", "icon"]:
                self.set_value_named(fsobj_iter, label, getattr(to_tuple, label))
    # This is not a method but a function within the FileTreeView namespace
    def _format_file_name_crcb(_column, cell_renderer, store, tree_iter, *args,**kwargs):
        name = store.get_value_named(tree_iter, "name")
        if name is None:
            cell_renderer.set_property("text", _("<empty>"))
            return
        rfd = store.get_value_named(tree_iter, "related_file_data")
        if rfd:
            cell_renderer.set_property("text", " ".join((name, rfd.relation, rfd.path)))
        else:
            cell_renderer.set_property("text", name)
    UI_DESCR = \
    '''
    <ui>
      <menubar name="files_menubar">
        <menu name="files_menu" action="menu_files">
          <menuitem action="new_file"/>
        </menu>
      </menubar>
      <popup name="files_popup">
          <menuitem action="edit_files"/>
          <menuitem action="delete_files"/>
        <separator/>
          <menuitem action="copy_files_selection"/>
          <menuitem action="move_files_selection"/>
          <menuitem action="rename_file"/>
      </popup>
    </ui>
    '''
    specification = tlview.ViewSpec(
        properties={"headers-visible" : False},
        selection_mode=gtk.SELECTION_MULTIPLE,
        columns=[
            tlview.ColumnSpec(
                title=_("File Name"),
                properties={},
                cells=[
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=gtk.CellRendererPixbuf,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        cell_data_function_spec=None,
                        attributes={"stock-id" : Model.col_index("icon")}
                    ),
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=gtk.CellRendererText,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        cell_data_function_spec=None,
                        attributes={"text" : Model.col_index("status"), "style" : Model.col_index("style"), "foreground" : Model.col_index("foreground")}
                    ),
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=gtk.CellRendererText,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        cell_data_function_spec=tlview.CellDataFunctionSpec(function=_format_file_name_crcb, user_data=None),
                        attributes={"style" : Model.col_index("style"), "foreground" : Model.col_index("foreground")}
                    )
                ]
            )
        ]
    )
    KEYVAL_c = gtk.gdk.keyval_from_name('c')
    KEYVAL_C = gtk.gdk.keyval_from_name('C')
    KEYVAL_ESCAPE = gtk.gdk.keyval_from_name('Escape')
    AUTO_EXPAND = False
    @staticmethod
    def _handle_button_press_cb(widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button == 2:
                widget.get_selection().unselect_all()
                return True
        return False
    @staticmethod
    def _handle_key_press_cb(widget, event):
        if event.state & gtk.gdk.CONTROL_MASK:
            if event.keyval in [FileTreeView.KEYVAL_c, FileTreeView.KEYVAL_C]:
                widget.add_selected_files_to_clipboard()
                return True
        elif event.keyval == FileTreeView.KEYVAL_ESCAPE:
            widget.get_selection().unselect_all()
            return True
        return False
    @staticmethod
    def search_equal_func(model, column, key, model_iter, _data=None):
        text = model.fs_path(model_iter)
        return text.find(key) == -1
    _FILE_ICON = {True : gtk.STOCK_DIRECTORY, False : gtk.STOCK_FILE}
    @classmethod
    def _get_status_deco(cls, status=None):
        try:
            return fsdb.STATUS_DECO_MAP[status]
        except KeyError:
            return fsdb.STATUS_DECO_MAP[None]
    @classmethod
    def _generate_row_tuple(cls, data, isdir):
        deco = cls._get_status_deco(data.status)
        row = cls.Model.Row(
            name=data.name,
            is_dir=isdir,
            icon=cls._FILE_ICON[isdir],
            status=data.status,
            related_file_data=data.related_file_data,
            style=deco.style,
            foreground=deco.foreground
        )
        return row
    def __init__(self, show_hidden=False, hide_clean=False, busy_indicator=None):
        assert (self.REPOPULATE_EVENTS & self.UPDATE_EVENTS) == 0
        dialogue.BusyIndicatorUser.__init__(self, busy_indicator=busy_indicator)
        ws_event.Listener.__init__(self)
        auto_update.AutoUpdater.__init__(self)
        self.show_hidden_action = gtk.ToggleAction('show_hidden_files', _('Show Hidden Files'), _('Show/hide ignored files and those beginning with "."'), None)
        self.show_hidden_action.set_active(show_hidden)
        self.show_hidden_action.connect('toggled', self._toggle_show_hidden_cb)
        self.show_hidden_action.set_menu_item_type(gtk.CheckMenuItem)
        self.show_hidden_action.set_tool_item_type(gtk.ToggleToolButton)
        self.hide_clean_action = gtk.ToggleAction('hide_clean_files', _('Hide Clean Files'), _('Show/hide "clean" files'), None)
        self.hide_clean_action.set_active(hide_clean)
        self.hide_clean_action.connect('toggled', self._toggle_hide_clean_cb)
        self.hide_clean_action.set_menu_item_type(gtk.CheckMenuItem)
        self.hide_clean_action.set_tool_item_type(gtk.ToggleToolButton)
        tlview.TreeView.__init__(self)
        self.set_search_equal_func(self.search_equal_func)
        ws_actions.AGandUIManager.__init__(self, selection=self.get_selection(), popup=self.DEFAULT_POPUP)
        self.connect("row-expanded", self.model.on_row_expanded_cb)
        self.connect("row-collapsed", self.model.on_row_collapsed_cb)
        self.connect("button_press_event", self._handle_button_press_cb)
        self.connect("key_press_event", self._handle_key_press_cb)
        self.get_selection().set_select_function(self._dirs_not_selectable, full=True)
        self.add_notification_cb(self.REPOPULATE_EVENTS, self.repopulate)
        self.add_notification_cb(self.UPDATE_EVENTS, self.update)
        self.register_auto_update_cb(self.auto_update)
        # TODO: investigate whether repopulate() needs to be called here
        self.repopulate()
    def auto_update(self, events_so_far, args):
        if (events_so_far & (self.REPOPULATE_EVENTS|self.UPDATE_EVENTS)) or self._file_db.is_current:
            return 0
        try:
            args["fsdb_reset_only"].append(self)
        except KeyError:
            args["fsdb_reset_only"] = [self]
        return self.AU_FILE_CHANGE_EVENT
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_action(self.show_hidden_action)
        self.action_groups[actions.AC_DONT_CARE].add_action(self.hide_clean_action)
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ('refresh_files', gtk.STOCK_REFRESH, _('_Refresh Files'), None,
                 _('Refresh/update the file tree display'),
                 lambda _action=None: self.update()
                ),
            ])
        self.action_groups[ws_actions.AC_NOT_IN_PM_PGND|actions.AC_SELN_MADE].add_actions(
            [
                ("edit_files", gtk.STOCK_EDIT, _('_Edit'), None,
                 _('Edit the selected file(s)'),
                 lambda _action=None: text_edit.edit_files_extern(self.get_selected_filepaths())
                ),
                ("copy_files_selection", gtk.STOCK_COPY, _('Copy'), None,
                 _('Copy the selected file(s)'),
                 lambda _action=None: self.copy_files(self.get_selected_filepaths())
                ),
                ("move_files_selection", gtk.STOCK_PASTE, _('_Move/Rename'), None,
                 _('Move the selected file(s)'),
                 lambda _action=None: self.move_files(self.get_selected_filepaths())
                ),
                ("delete_files", gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Delete the selected file(s)'),
                 lambda _action=None: self.delete_files(self.get_selected_filepaths(), ask=True)
                ),
            ])
        self.action_groups[ws_actions.AC_NOT_IN_PM_PGND|actions.AC_SELN_UNIQUE].add_actions(
           [
                ("rename_file", icons.STOCK_RENAME, _('Re_name/Move'), None,
                 _('Rename/move the selected file'),
                 lambda _action=None: self.move_selected_files()
                ),
            ])
        self.action_groups[ws_actions.AC_NOT_IN_PM_PGND].add_actions(
            [
                ("new_file", gtk.STOCK_NEW, _('_New'), None,
                 _('Create a new file and open for editing'),
                 lambda _action: create_new_file()
                ),
            ])
    @property
    def show_hidden(self):
        return self.show_hidden_action.get_active()
    @show_hidden.setter
    def show_hidden(self, new_value):
        self.show_hidden_action.set_active(new_value)
        self._update_dir('', None)
    @property
    def hide_clean(self):
        return self.hide_clean_action.get_active()
    @hide_clean.setter
    def hide_clean(self, new_value):
        self.hide_clean_action.set_active(new_value)
        self._update_dir('', None)
    @staticmethod
    def _dirs_not_selectable(selection, model, path, is_selected, *args,**kwargs):
        if not is_selected:
            return not model.get_value_named(model.get_iter(path), 'is_dir')
        return True
    def _toggle_show_hidden_cb(self, toggleaction):
        self.show_busy()
        self._update_dir('', None)
        self.unshow_busy()
    def _toggle_hide_clean_cb(self, toggleaction):
        self.show_busy()
        self._update_dir('', None)
        self.unshow_busy()
    def _get_dir_contents(self, dirpath):
        return self._file_db.dir_contents(dirpath, show_hidden=self.show_hidden, hide_clean=self.hide_clean)
    def _row_expanded(self, dir_iter):
        return self.row_expanded(self.model.get_path(dir_iter))
    def _populate(self, dirpath, parent_iter):
        dirs, files = self._get_dir_contents(dirpath)
        for dirdata in dirs:
            row_tuple = self._generate_row_tuple(dirdata, True)
            dir_iter = self.model.append(parent_iter, row_tuple)
            if self.AUTO_EXPAND:
                self._populate(os.path.join(dirpath, dirdata.name), dir_iter)
                self.expand_row(self.model.get_path(dir_iter), True)
            else:
                self.model.insert_place_holder(dir_iter)
        for filedata in files:
            row_tuple = self._generate_row_tuple(filedata, False)
            dummy = self.model.append(parent_iter, row_tuple)
        if parent_iter is not None:
            self.model.insert_place_holder_if_needed(parent_iter)
    def get_iter_for_filepath(self, filepath):
        pathparts = fsdb.split_path(filepath)
        child_iter = self.model.get_iter_first()
        for index in range(len(pathparts) - 1):
            while child_iter is not None:
                if self.model.get_value_named(child_iter, 'name') == pathparts[index]:
                    tpath = self.model.get_path(child_iter)
                    if not self.row_expanded(tpath):
                        self.expand_row(tpath, False)
                    child_iter = self.model.iter_children(child_iter)
                    break
                child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            if self.model.get_value_named(child_iter, 'name') == pathparts[-1]:
                return child_iter
            child_iter = self.model.iter_next(child_iter)
        return None
    def select_filepaths(self, filepaths):
        seln = self.get_selection()
        seln.unselect_all()
        for filepath in filepaths:
            seln.select_iter(self.get_iter_for_filepath(filepath))
    def _update_dir(self, dirpath, parent_iter=None):
        changed = False
        place_holder_iter = None
        if parent_iter is None:
            child_iter = self.model.get_iter_first()
        else:
            child_iter = self.model.iter_children(parent_iter)
            if child_iter:
                if self.model.get_value_named(child_iter, "name") is None:
                    place_holder_iter = child_iter.copy()
                    child_iter = self.model.iter_next(child_iter)
        dirs, files = self._get_dir_contents(dirpath)
        dead_entries = []
        for dirdata in dirs:
            row_tuple = self._generate_row_tuple(dirdata, True)
            while (child_iter is not None) and self.model.get_value_named(child_iter, 'is_dir') and (self.model.get_value_named(child_iter, 'name') < dirdata.name):
                dead_entries.append(child_iter)
                child_iter = self.model.iter_next(child_iter)
            if child_iter is None:
                dir_iter = self.model.append(parent_iter, row_tuple)
                changed = True
                if self.AUTO_EXPAND:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self.model.insert_place_holder(dir_iter)
                continue
            name = self.model.get_value_named(child_iter, "name")
            if (not self.model.get_value_named(child_iter, "is_dir")) or (name > dirdata.name):
                dir_iter = self.model.insert_before(parent_iter, child_iter, row_tuple)
                changed = True
                if self.AUTO_EXPAND:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self.model.insert_place_holder(dir_iter)
                continue
            changed |= self.model.get_value_named(child_iter, "icon") != row_tuple.icon
            self.model.update_iter_row_tuple(child_iter, row_tuple)
            # This is an update so ignore EXPAND_ALL for existing directories
            if self._row_expanded(child_iter):
                changed |= self._update_dir(os.path.join(dirpath, name), child_iter)
            else:
                # make sure we don't leave bad data in children that were previously expanded
                self.model.depopulate(child_iter)
            child_iter = self.model.iter_next(child_iter)
        while (child_iter is not None) and self.model.get_value_named(child_iter, 'is_dir'):
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        for filedata in files:
            row_tuple = self._generate_row_tuple(filedata, False)
            while (child_iter is not None) and (self.model.get_value_named(child_iter, 'name') < filedata.name):
                dead_entries.append(child_iter)
                child_iter = self.model.iter_next(child_iter)
            if child_iter is None:
                dummy = self.model.append(parent_iter, row_tuple)
                changed = True
                continue
            if self.model.get_value_named(child_iter, "name") > filedata.name:
                dummy = self.model.insert_before(parent_iter, child_iter, row_tuple)
                changed = True
                continue
            changed |= self.model.get_value_named(child_iter, "icon") != row_tuple.icon
            self.model.update_iter_row_tuple(child_iter, row_tuple)
            child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        changed |= len(dead_entries) > 0
        for dead_entry in dead_entries:
            self.model.recursive_remove(dead_entry)
        if parent_iter is not None:
            n_children = self.model.iter_n_children(parent_iter)
            if n_children == 0:
                self.model.insert_place_holder(parent_iter)
            elif place_holder_iter is not None and n_children > 1:
                assert self.model.get_value_named(place_holder_iter, "name") is None
                self.model.remove(place_holder_iter)
        return changed
    @staticmethod
    def _get_file_db():
        return fsdb.OsFileDb()
    def repopulate(self, **kwargs):
        self.show_busy()
        self._file_db = self._get_file_db()
        self.model.clear()
        self._populate('', self.model.get_iter_first())
        self.unshow_busy()
    def update(self, fsdb_reset_only=False, **kwargs):
        self.show_busy()
        self._file_db = self._file_db.reset() if (fsdb_reset_only and self in fsdb_reset_only) else self._get_file_db()
        self._update_dir('', None)
        self.unshow_busy()
    def get_selected_filepath(self):
        store, selection = self.get_selection().get_selected_rows()
        assert len(selection) == 1
        return store.fs_path(store.get_iter(selection[0]))
    def get_selected_filepaths(self, expanded=False):
        store, selection = self.get_selection().get_selected_rows()
        filepath_list = [store.fs_path(store.get_iter(x)) for x in selection]
        if expanded:
            return self.expand_filepaths(filepath_list)
        return filepath_list
    def add_selected_files_to_clipboard(self, clipboard=None):
        if not clipboard:
            clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)
        sel = utils.quoted_join(self.get_selected_filepaths())
        clipboard.set_text(sel)
    def get_filepaths_in_dir(self, dirname, show_hidden=True, recursive=True):
        # TODO: fix get_filepaths_in_dir() -- use os/scm not db
        subdirs, files = self._file_db.dir_contents(dirname, show_hidden=show_hidden)
        filepaths = [os.path.join(dirname, fdata.name) for fdata in files]
        if recursive:
            for subdir in subdirs:
                filepaths += self.get_filepaths_in_dir(os.path.join(dirname, subdir.name), recursive)
        return filepaths
    def is_dir_filepath(self, filepath):
        return self.model.get_value_named(self.get_iter_for_filepath(filepath), "is_dir")
    def expand_filepaths(self, filepath_list, show_hidden=False, recursive=True):
        if isinstance(filepath_list, str):
            filepath_list = [filepath_list]
        expanded_list = []
        for filepath in filepath_list:
            if self.is_dir_filepath(filepath):
                expanded_list += self.get_filepaths_in_dir(filepath, show_hidden=show_hidden, recursive=recursive)
            else:
                expanded_list.append(filepath)
        return expanded_list
    @staticmethod
    def create_new_file(open_for_edit=False):
        new_file_path = dialogue.ask_file_name(_("New File Path"))
        dialogue.show_busy()
        result = os_utils.os_create_file(new_file_name)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
        if result.is_ok and open_for_edit:
            text_edit.edit_files_extern([new_file_name])
        return result
    @staticmethod
    def delete_files(file_paths, ask=True):
        if ask and not dialogue.confirm_list_action(file_paths, _('About to be deleted. OK?')):
            return
        os_utils.os_delete_files(file_paths)
    @staticmethod
    def copy_files(file_paths, dry_run_first=True):
        from . import dooph
        destn = dooph.ask_destination(file_paths)
        if not destn:
            return
        do_op = lambda destn=None, overwrite=False: os_utils.os_copy_files(file_paths, destn=destn, overwrite=overwrite, dry_run=dry_run_first)
        result = dooph.do_overwrite_or_rename(destn, do_op)
        dialogue.report_any_problems(result)
        return result
    @staticmethod
    def move_files(file_paths, dry_run_first=True):
        from . import dooph
        destn = dooph.ask_destination(file_paths)
        if not destn:
            return
        do_op = lambda destn=None, overwrite=False: os_utils.os_move_files(file_paths, destn=destn, overwrite=overwrite, dry_run=dry_run_first)
        result = dooph.do_overwrite_or_rename(destn, do_op)
        dialogue.report_any_problems(result)
        return result

class FileTreeWidget(gtk.VBox, ws_event.Listener):
    MENUBAR = "/files_menubar"
    BUTTON_BAR_ACTIONS = ["show_hidden_files"]
    TREE_VIEW = FileTreeView
    SIZE = (240, 320)
    def __init__(self, show_hidden=False, hide_clean=False, **kwargs):
        gtk.VBox.__init__(self)
        ws_event.Listener.__init__(self)
        # file tree view wrapped in scrolled window
        self.file_tree = self.TREE_VIEW(show_hidden=show_hidden, hide_clean=hide_clean, **kwargs)
        scw = gtk.ScrolledWindow()
        scw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.file_tree.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.file_tree.set_headers_visible(False)
        self.file_tree.set_size_request(*self.SIZE)
        scw.add(self.file_tree)
        # file tree menu bar
        mprefix = self.get_menu_prefix()
        self.menu_prefix = gtk.Label('' if not mprefix else (mprefix + ':'))
        if self.MENUBAR:
            hbox = gtk.HBox()
            self.pack_start(hbox, expand=False, fill=False)
            hbox.pack_start(self.menu_prefix, expand=False, fill=False)
            self.menu_bar = self.file_tree.ui_manager.get_widget(self.MENUBAR)
            hbox.pack_start(self.menu_bar, expand=False)
        self.pack_start(scw, expand=True, fill=True)
        # Mode selectors
        hbox = gtk.HBox()
        for action_name in self.BUTTON_BAR_ACTIONS:
            button = gtk.CheckButton()
            action = self.file_tree.action_groups.get_action(action_name)
            action.connect_proxy(button)
            gutils.set_widget_tooltip_text(button, action.get_property("tooltip"))
            hbox.pack_start(button)
        self.pack_start(hbox, expand=False)
        self.add_notification_cb(ifce.E_CHANGE_WD|ifce.E_NEW_SCM_OR_PM, self._cwd_change_cb)
        self.show_all()
    @staticmethod
    def get_menu_prefix():
        return None
    def _cwd_change_cb(self, **kwargs):
        mprefix = self.get_menu_prefix()
        self.menu_prefix.set_text('' if not mprefix else (mprefix + ':'))

### Copyright (C) 2007 Peter Williams <peter_ono@users.sourceforge.net>
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

"""
Provide generic enhancements to Textview widgets primarily to create
them from templates and allow easier access to named contents.
"""

import gtk

from darning.gui import gutils
from darning.gui import actions
from darning.gui import ws_actions
from darning.gui import ws_event
from darning.gui import tlview
from darning.gui import icons
from darning.gui import dialogue

ALWAYS_ON = 'table_always_on'
MODIFIED = 'table_modified'
NOT_MODIFIED = 'table_not_modified'
SELECTION = 'table_selection'
NO_SELECTION = 'table_no_selection'
UNIQUE_SELECTION = 'table_unique_selection'

TABLE_STATES = \
    [ALWAYS_ON, MODIFIED, NOT_MODIFIED, SELECTION, NO_SELECTION,
     UNIQUE_SELECTION]

class Table(gtk.VBox):
    View = tlview.ListView
    def __init__(self, size_req=None):
        gtk.VBox.__init__(self)
        self.view = self.View()
        self.seln = self.view.get_selection()
        if size_req:
            self.view.set_size_request(*size_req)
        self.pack_start(gutils.wrap_in_scrolled_window(self.view))
        self.action_groups = {}
        for key in TABLE_STATES:
            self.action_groups[key] = gtk.ActionGroup(key)
        self.action_groups[ALWAYS_ON].add_actions(
            [
                ('table_add_row', gtk.STOCK_ADD, _('_Add'), None,
                 _('Add a new entry to the table'), self._add_row_acb),
            ])
        self.action_groups[MODIFIED].add_actions(
            [
                ('table_undo_changes', gtk.STOCK_UNDO, _('_Undo'), None,
                 _('Undo unapplied changes'), self._undo_changes_acb),
                ('table_apply_changes', gtk.STOCK_APPLY, _('_Apply'), None,
                 _('Apply outstanding changes'), self._apply_changes_acb),
            ])
        self.action_groups[SELECTION].add_actions(
            [
                ('table_delete_selection', gtk.STOCK_DELETE, _('_Delete'), None,
                 _('Delete selected row(s)'), self._delete_selection_acb),
                ('table_insert_row', icons.STOCK_INSERT, _('_Insert'), None,
                 _('Insert a new entry before the selected row(s)'), self._insert_row_acb),
            ])
        self._modified = False
        self.model.connect('row-inserted', self._row_inserted_cb)
        self.seln.connect('changed', self._selection_changed_cb)
        self.view.register_modification_callback(self._set_modified, True)
        self.seln.unselect_all()
        self._selection_changed_cb(self.seln)
    @property
    def model(self):
        return self.view.get_model()
    def _set_modified(self, val):
        self._modified = val
        self.action_groups[MODIFIED].set_sensitive(val)
        self.action_groups[NOT_MODIFIED].set_sensitive(not val)
    def _fetch_contents(self):
        assert False, _("Must be defined in child")
    def set_contents(self):
        self.model.set_contents(self._fetch_contents())
        self._set_modified(False)
    def get_contents(self):
        return [row for row in self.model.named()]
    def apply_changes(self):
        assert False, _("Must be defined in child")
    def _row_inserted_cb(self, model, path, model_iter):
        self._set_modified(True)
    def _selection_changed_cb(self, selection):
        rows = selection.count_selected_rows()
        self.action_groups[SELECTION].set_sensitive(rows > 0)
        self.action_groups[NO_SELECTION].set_sensitive(rows == 0)
        self.action_groups[UNIQUE_SELECTION].set_sensitive(rows == 1)
    def _undo_changes_acb(self, _action=None):
        self.set_contents()
    def _apply_changes_acb(self, _action=None):
        self.apply_changes()
    def _add_row_acb(self, _action=None):
        model_iter = self.model.append(None)
        self.view.get_selection().select_iter(model_iter)
        return
    def _delete_selection_acb(self, _action=None):
        model, paths = self.seln.get_selected_rows()
        iters = []
        for path in paths:
            iters.append(model.get_iter(path))
        for model_iter in iters:
            model.remove(model_iter)
    def _insert_row_acb(self, _action=None):
        model, paths = self.seln.get_selected_rows()
        if not paths:
            return
        model_iter = self.model.insert_before(model.get_iter(paths[0]), None)
        self.view.get_selection().select_iter(model_iter)
        return
    def get_selected_data(self, columns=None):
        store, selected_rows = self.seln.get_selected_rows()
        if not columns:
            columns = list(range(store.get_n_columns()))
        result = []
        for row in selected_rows:
            model_iter = store.get_iter(row)
            assert model_iter is not None
            result.append(store.get(model_iter, *columns))
        return result
    def get_selected_data_by_label(self, labels):
        columns = self.model.col_indices(labels)
        return self.get_selected_data(columns)

class TableView(tlview.ListView, ws_actions.AGandUIManager, dialogue.BusyIndicatorUser):
    PopUp = None
    def __init__(self, busy_indicator=None, size_req=None):
        tlview.ListView.__init__(self)
        dialogue.BusyIndicatorUser.__init__(self, busy_indicator)
        ws_actions.AGandUIManager.__init__(self, selection=self.get_selection(), popup=self.PopUp)
        if size_req:
            self.set_size_request(size_req[0], size_req[1])
        self.connect("button_press_event", self._handle_clear_selection_cb)
        self.connect("key_press_event", self._handle_clear_selection_cb)
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("table_refresh_contents", gtk.STOCK_REFRESH, _('Refresh'), None,
                 _('Refresh the tables contents'), self._refresh_contents_acb),
            ])
    @property
    def model(self):
        return self.get_model()
    @property
    def seln(self):
        return self.get_selection()
    def _handle_clear_selection_cb(self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button == 2:
                self.seln.unselect_all()
                return True
        elif event.type == gtk.gdk.KEY_PRESS:
            if event.keyval == gtk.gdk.keyval_from_name('Escape'):
                self.seln.unselect_all()
                return True
        return False
    def _fetch_contents(self):
        assert False, _("Must be defined in child")
    def _set_contents(self):
        model = self.Model()
        model.set_contents(self._fetch_contents())
        self.set_model(model)
        self.columns_autosize()
        self.seln.unselect_all()
    def set_contents(self):
        self.show_busy()
        self._set_contents()
        self.unshow_busy()
    def refresh_contents(self):
        self.show_busy()
        selected_keys = self.get_selected_keys()
        visible_range = self.get_visible_range()
        if visible_range is not None:
            start = visible_range[0][0]
            end = visible_range[1][0]
            length = end - start + 1
            middle_offset = length / 2
            align = float(middle_offset) / float(length)
            middle = start + middle_offset
            middle_key = self.model.get_value(self.model.get_iter(middle), 0)
        self._set_contents()
        for key in selected_keys:
            model_iter = self.model.find_named(lambda x: x[0] == key)
            if model_iter is not None:
                self.seln.select_iter(model_iter)
        if visible_range is not None:
            middle_iter = self.model.find_named(lambda x: x[0] == middle_key)
            if middle_iter is not None:
                middle = self.model.get_path(middle_iter)
                self.scroll_to_cell(middle, use_align=True, row_align=align)
        self.unshow_busy()
    def _refresh_contents_acb(self, _action):
        self.refresh_contents()
    def get_contents(self):
        return [row for row in self.model.named()]
    def get_selected_data(self, columns=None):
        store, selected_rows = self.seln.get_selected_rows()
        if not columns:
            columns = list(range(store.get_n_columns()))
        result = []
        for row in selected_rows:
            model_iter = store.get_iter(row)
            assert model_iter is not None
            result.append(store.get(model_iter, *columns))
        return result
    def get_selected_keys(self, keycol=0):
        store, selected_rows = self.seln.get_selected_rows()
        keys = []
        for row in selected_rows:
            model_iter = store.get_iter(row)
            assert model_iter is not None
            keys.append(store.get_value(model_iter, keycol))
        return keys
    def get_selected_data_by_label(self, labels):
        return self.get_selected_data(self.model.col_indices(labels))
    def get_selected_keys_by_label(self, label):
        return self.get_selected_keys(self.model.col_index(label))
    def get_selected_key(self, keycol=0):
        keys = self.get_selected_keys(keycol)
        assert len(keys) <= 1
        if keys:
            return keys[0]
        else:
            return None
    def get_selected_key_by_label(self, label):
        return self.get_selected_key(self.model.col_index(label))
    def select_and_scroll_to_row_with_key_value(self, key_value, key=None):
        index = 0 if key is None else (key if isinstance(key, int) else self.model.col_index(key))
        model_iter = self.model.find_named(lambda x: x[index] == key_value)
        if not model_iter:
            return False
        self.seln.select_iter(model_iter)
        path = self.model.get_path(model_iter)
        self.scroll_to_cell(path, use_align=True, row_align=0.5)
        return True

_NEEDS_RESET = 123

class MapManagedTableView(TableView, gutils.MappedManager):
    def __init__(self, busy_indicator=None, size_req=None):
        TableView.__init__(self, busy_indicator=busy_indicator, size_req=size_req)
        gutils.MappedManager.__init__(self)
        self._needs_refresh = True
        self.add_notification_cb(ws_event.CHANGE_WD, self.reset_contents_if_mapped)
    def map_action(self):
        if self._needs_refresh == _NEEDS_RESET:
            self.show_busy()
            self.set_contents()
            self.unshow_busy()
        elif self._needs_refresh:
            self.show_busy()
            self.refresh_contents()
            self.unshow_busy()
    def unmap_action(self):
        pass
    def set_contents(self):
        TableView.set_contents(self)
        self._needs_refresh = False
    def refresh_contents(self):
        TableView.refresh_contents(self)
        self._needs_refresh = False
    def refresh_contents_if_mapped(self, *_args):
        if self.is_mapped:
            self.refresh_contents()
        elif not self._needs_refresh:
            self._needs_refresh = True
    def reset_contents_if_mapped(self, *_args):
        if self.is_mapped:
            self.set_contents()
        else:
            self._needs_refresh = _NEEDS_RESET
    def _refresh_contents_acb(self, _action):
        self.refresh_contents()

class TableWidget(gtk.VBox):
    View = TableView
    def __init__(self, scroll_bar=True, busy_indicator=None, size_req=None, **kwargs):
        gtk.VBox.__init__(self)
        self.header = gutils.SplitBar()
        self.pack_start(self.header, expand=False)
        self.view = self.View(busy_indicator=busy_indicator, size_req=size_req, **kwargs)
        if scroll_bar:
            self.pack_start(gutils.wrap_in_scrolled_window(self.view))
        else:
            self.pack_start(self.view)
        self.show_all()
    @property
    def ui_manager(self):
        return self.view.ui_manager
    @property
    def action_groups(self):
        return self.view.action_groups
    @property
    def seln(self):
        return self.view.get_selection()
    def unselect_all(self):
        self.seln.unselect_all()

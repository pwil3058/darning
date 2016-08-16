### Copyright (C) 2007-2015 Peter Williams <pwil3058@gmail.com>
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

from gi.repository import Gtk
from gi.repository import Gdk

from .. import enotify

from . import gutils
from . import actions
from . import tlview
from . import icons
from . import dialogue
from . import auto_update

ALWAYS_ON = 'table_always_on'
MODIFIED = 'table_modified'
NOT_MODIFIED = 'table_not_modified'
SELECTION = 'table_selection'
NO_SELECTION = 'table_no_selection'
UNIQUE_SELECTION = 'table_unique_selection'

TABLE_STATES = \
    [ALWAYS_ON, MODIFIED, NOT_MODIFIED, SELECTION, NO_SELECTION,
     UNIQUE_SELECTION]

# TODO: modify this code to use the new actions model
class Table(Gtk.VBox):
    View = tlview.ListView
    def __init__(self, size_req=None):
        Gtk.VBox.__init__(self)
        self.view = self.View()
        self.seln = self.view.get_selection()
        if size_req:
            self.view.set_size_request(*size_req)
        self.pack_start(gutils.wrap_in_scrolled_window(self.view), expand=True, fill=True, padding=0)
        self.action_groups = {}
        for key in TABLE_STATES:
            self.action_groups[key] = Gtk.ActionGroup(key)
        self.action_groups[ALWAYS_ON].add_actions(
            [
                ('table_add_row', Gtk.STOCK_ADD, _('_Add'), None,
                 _('Add a new entry to the table'), self._add_row_acb),
            ])
        self.action_groups[MODIFIED].add_actions(
            [
                ('table_undo_changes', Gtk.STOCK_UNDO, _('_Undo'), None,
                 _('Undo unapplied changes'), self._undo_changes_acb),
                ('table_apply_changes', Gtk.STOCK_APPLY, _('_Apply'), None,
                 _('Apply outstanding changes'), self._apply_changes_acb),
            ])
        self.action_groups[SELECTION].add_actions(
            [
                ('table_delete_selection', Gtk.STOCK_DELETE, _('_Delete'), None,
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

def simple_text_specification(model, *hdrs_flds_xalign):
    specification = tlview.ViewSpec(
        properties={
            "enable-grid-lines" : False,
            "reorderable" : False,
            "rules_hint" : False,
            "headers-visible" : True,
        },
        selection_mode=Gtk.SelectionMode.SINGLE,
        columns=[tlview.simple_column(hdr, tlview.fixed_text_cell(model, fld, xalign)) for hdr, fld, xalign in hdrs_flds_xalign]
    )
    return specification

class TableView(tlview.ListView, actions.CAGandUIManager, dialogue.BusyIndicatorUser, auto_update.AutoUpdater, enotify.Listener):
    __g_type_name__ = "TableView"
    from . import ifce
    PopUp = None
    SET_EVENTS = ifce.E_CHANGE_WD
    REFRESH_EVENTS = 0
    AU_REQ_EVENTS = 0
    def __init__(self, busy_indicator=None, size_req=None):
        tlview.ListView.__init__(self)
        dialogue.BusyIndicatorUser.__init__(self, busy_indicator)
        actions.CAGandUIManager.__init__(self, selection=self.get_selection(), popup=self.PopUp)
        auto_update.AutoUpdater.__init__(self)
        enotify.Listener.__init__(self)
        self._table_db = self._get_table_db()
        if self.SET_EVENTS:
            self.add_notification_cb(self.SET_EVENTS, self.set_contents)
        if self.REFRESH_EVENTS:
            self.add_notification_cb(self.REFRESH_EVENTS, self.refresh_contents)
        if self.AU_REQ_EVENTS:
            self.register_auto_update_cb(self.auto_update_cb)
        if size_req:
            self.set_size_request(size_req[0], size_req[1])
        self.connect("button_press_event", self._handle_clear_selection_cb)
        self.connect("key_press_event", self._handle_clear_selection_cb)
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("table_refresh_contents", Gtk.STOCK_REFRESH, _("Refresh"), None,
                 _("Refresh the table's contents"),
                 lambda _action=None: self.refresh_contents()
                ),
            ])
    @property
    def model(self):
        return self.get_model()
    @property
    def seln(self):
        return self.get_selection()
    def auto_update_cb(self, events_so_far, args):
        if (events_so_far & (self.SET_EVENTS|self.REFRESH_EVENTS)) or  self._table_db.is_current:
            return 0
        try:
            args["tbd_reset_only"].append(self)
        except KeyError:
            args["tbd_reset_only"] = [self]
        return self.AU_REQ_EVENTS
    def _handle_clear_selection_cb(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if event.button == 2:
                self.seln.unselect_all()
                return True
        elif event.type == Gdk.EventType.KEY_PRESS:
            if event.keyval == Gdk.keyval_from_name("Escape"):
                self.seln.unselect_all()
                return True
        return False
    def _get_table_db(self):
        assert False, _("Must be defined in child")
    def _fetch_contents(self, tbd_reset_only=False, **kwargs):
        self._table_db = self._table_db.reset() if (tbd_reset_only and self in tbd_reset_only) else self._get_table_db()
        return self._table_db.iter_rows()
    def _set_contents(self, **kwargs):
        model = self.Model()
        model.set_contents(self._fetch_contents(**kwargs))
        self.set_model(model)
        self.columns_autosize()
        self.seln.unselect_all()
    def set_contents(self, **kwargs):
        self.show_busy()
        self._set_contents(**kwargs)
        self.unshow_busy()
    def refresh_contents(self, **kwargs):
        self.show_busy()
        selected_keys = self.get_selected_keys()
        visible_range = self.get_visible_range()
        if visible_range is not None:
            start = visible_range[0][0]
            end = visible_range[1][0]
            length = end - start + 1
            middle_offset = length // 2
            align = float(middle_offset) / float(length)
            middle = start + middle_offset
            middle_key = self.model.get_value(self.model.get_iter(middle), 0)
        self._set_contents(**kwargs)
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

class MapManagedTableView(TableView, gutils.MappedManager):
    __g_type_name__ = "MapManagedTableView"
    _NEEDS_RESET = 123
    def __init__(self, busy_indicator=None, size_req=None):
        TableView.__init__(self, busy_indicator=busy_indicator, size_req=size_req)
        gutils.MappedManager.__init__(self)
        self._needs_refresh = True
    def auto_update_cb(self, events_so_far, args):
        if self._needs_refresh:
            # This implies (both) that we're not mapped AND that we're
            # already scheduled for update when we become mapped so
            # there's no point in wasting effort making any checks
            return 0
        return TableView.auto_update_cb(self, events_so_far, args)
    def map_action(self):
        if self._needs_refresh == self._NEEDS_RESET:
            TableView.set_contents(self)
            self._needs_refresh = False
        elif self._needs_refresh:
            TableView.refresh_contents(self)
            self._needs_refresh = False
    def unmap_action(self):
        pass
    def set_contents(self, **kwargs):
        if self.is_mapped:
            TableView.set_contents(self, **kwargs)
            self._needs_refresh = False
        else:
            self._needs_refresh = self._NEEDS_RESET
    def refresh_contents(self, **kwargs):
        if self.is_mapped:
            TableView.refresh_contents(self, **kwargs)
            self._needs_refresh = False
        else:
            self._needs_refresh = True

class TableWidget(Gtk.VBox):
    __g_type_name__ = "TableWidget"
    View = TableView
    def __init__(self, scroll_bar=True, busy_indicator=None, size_req=None, **kwargs):
        Gtk.VBox.__init__(self)
        self.header = gutils.SplitBar()
        self.pack_start(self.header, expand=False, fill=True, padding=0)
        self.view = self.View(busy_indicator=busy_indicator, size_req=size_req, **kwargs)
        if scroll_bar:
            self.pack_start(gutils.wrap_in_scrolled_window(self.view), expand=True, fill=True, padding=0)
        else:
            self.pack_start(self.view, expand=True, fill=True, padding=0)
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

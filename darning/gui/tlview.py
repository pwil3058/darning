### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>
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
Provide generic enhancements to Tree and List View widgets primarily to create
them from templates and allow easier access to named contents.
"""

import collections

import gtk
import gobject

class NamedTreeModel(gtk.TreeModel):
    # TODO: trim and improve NamedTreeModel
    Row = None # this is a namedtuple type
    types = None # this is an instance of Row defining column types
    @classmethod
    def col_index(cls, label):
        return cls.Row._fields.index(label)
    @classmethod
    def col_indices(cls, labels):
        return [cls.Row._fields.index(label) for label in labels]
    @staticmethod
    def get_selected_rows(selection):
        model, paths = selection.get_selected_rows()
        return [model.Row(*model[p]) for p in paths]
    def get_row(self, model_iter):
        return self.Row(*self[model_iter])
    def get_named(self, model_iter, *labels):
        return self.get(model_iter, *self.col_indices(labels))
    def get_value_named(self, model_iter, label):
        return self.get_value(model_iter, self.col_index(label))
    def set_value_named(self, model_iter, label, value):
        self.set_value(model_iter, self.col_index(label), value)
    def set_named(self, model_iter, *label_values):
        col_values = []
        for index in len(label_values):
            if (index % 2) == 0:
                col_values.append(self.col_index(label_values[index]))
            else:
                col_values.append(label_values[index])
        self.set(model_iter, *col_values)
    def named(self):
        # Iterate over rows as instances of type Row()
        model_iter = self.get_iter_first()
        while model_iter is not None:
            yield self.get_row(model_iter)
            model_iter = self.iter_next(model_iter)
        return
    def find_named(self, select_func):
        model_iter = self.get_iter_first()
        while model_iter:
            if select_func(self.get_row(model_iter)):
                return model_iter
            else:
                model_iter = self.iter_next(model_iter)
        return None

class NamedListStore(gtk.ListStore, NamedTreeModel):
    def __init__(self):
        gtk.ListStore.__init__(*[self] + list(self.types))
    def append_contents(self, rows):
        for row in rows:
            self.append(row)
    def set_contents(self, rows):
        self.clear()
        for row in rows:
            self.append(row)

class NamedTreeStore(gtk.TreeStore, NamedTreeModel):
    def __init__(self):
        gtk.TreeStore.__init__(*[self] + list(self.types))

class View(gtk.TreeView):
    Model = None
    Template = collections.namedtuple('ViewTemplate', ['properties', 'selection_mode', 'columns'])
    Column = collections.namedtuple('Column', ['title', 'properties', 'cells'])
    CellCreator = collections.namedtuple('CellCreator', ['function', 'expand', 'start'])
    Renderer = collections.namedtuple('Renderer', ['function', 'user_data'])
    Cell = collections.namedtuple('Cell', ['creator', 'properties', 'renderer', 'attributes'])
    ColumnAndCells = collections.namedtuple('ColumnAndCells', ['column', 'cells'])
    template = None
    def __init__(self, model=None):
        if model is None:
            model = self.Model()
        else:
            assert isinstance(model, self.Model)
        gtk.TreeView.__init__(self, model)
        for prop_name, prop_val in self.template.properties.items():
            self.set_property(prop_name, prop_val)
        if self.template.selection_mode is not None:
            self.get_selection().set_mode(self.template.selection_mode)
        self._columns = collections.OrderedDict()
        for col_d in self.template.columns:
            self._view_add_column(col_d)
        self.connect("button_press_event", self._handle_button_press_cb)
        self._modified_cbs = []
    @staticmethod
    def _create_cell(column, descr):
        """descr is a CellCreator"""
        cell = descr.function()
        if descr.expand is not None:
            if descr.start:
                column.pack_start(cell, descr.expand)
            else:
                column.pack_end(cell, descr.expand)
        else:
            if descr.start:
                column.pack_start(cell)
            else:
                column.pack_end(cell)
        return cell
    def _view_add_column(self, col_d):
        col = gtk.TreeViewColumn(col_d.title)
        col_cells = View.ColumnAndCells(col, [])
        self._columns[col_d.title] = col_cells
        self.append_column(col)
        for prop_name, prop_val in col_d.properties.items():
            col.set_property(prop_name, prop_val)
        for cell_d in col_d.cells:
            self._view_add_cell(col, cell_d)
    def _view_add_cell(self, col, cell_d):
        cell = self._create_cell(col, cell_d.creator)
        self._columns[col.get_title()].cells.append(cell)
        for prop_name, prop_val in cell_d.properties.items():
            cell.set_property(prop_name, prop_val)
        if cell_d.renderer is not None:
            col.set_cell_data_func(cell, cell_d.renderer.function, cell_d.renderer.user_data)
        for attr_name, attr_index in cell_d.attributes.items():
            col.add_attribute(cell, attr_name, attr_index)
            if attr_name == 'text':
                cell.connect('edited', self._cell_text_edited_cb, attr_index)
            elif attr_name == 'active':
                cell.connect('toggled', self._cell_toggled_cb, attr_index)
    @property
    def model(self):
        return self.get_model()
    @model.setter
    def model(self, new_model):
        self.set_model(new_model)
    def set_model(self, model):
        assert model is None or isinstance(model, self.Model)
        gtk.TreeView.set_model(self, model)
    def _notify_modification(self):
        for cbk, data in self._modified_cbs:
            if data is None:
                cbk()
            else:
                cbk(data)
    def register_modification_callback(self, cbk, data=None):
        self._modified_cbs.append([cbk, data])
    def _handle_button_press_cb(self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button == 2:
                self.get_selection().unselect_all()
                return True
        return False
    def _cell_text_edited_cb(self, cell, path, new_text, index):
        self.get_model()[path][index] = new_text
        self._notify_modification()
    def _cell_toggled_cb(self, cell, path, index):
        self.model[path][index] = cell.get_active()
        self._notify_modification()
    def get_col_with_title(self, title):
        return self._columns[title].column
    def get_cell_with_title(self, title, index=0):
        return self._columns[title].cells[index]
    def get_cell(self, col_index, cell_index=0):
        key = list(self._columns.keys())[col_index]
        return self._columns[key].cells[cell_index]

class ListView(View):
    Model = NamedListStore

class TreeView(View):
    Model = NamedTreeStore

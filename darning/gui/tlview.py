### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""
Provide generic enhancements to Textview widgets primarily to create
them from templates and allow easier access to named contents.
"""

import gtk, collections

def model_col(descr, label):
    """Return the index of the column with the given label in the descr
    which is named tuple"""
    return descr._fields.index(label)

class Model(gtk.TreeModel):
    def __init__(self, descr):
        """descr is a named tuple"""
        self.row_tuple_type = type(descr)
    def get_col(self, label):
        return model_col(self.row_tuple_type, label)
    def get_cols(self, labels):
        return [self.get_col(col) for col in labels]
    def get_values(self, model_iter, cols):
        return self.get(*([model_iter] + cols))
    def set_values(self, model_iter, col_vals):
        return self.set(*([model_iter] + col_vals))
    def get_row(self, model_iter):
        return self.get_values(model_iter, list(range(self.get_n_columns())))
    def get_labelled_value(self, model_iter, label):
        return self.get_value(model_iter, self.get_col(label))
    def get_labelled_values(self, model_iter, labels):
        return self.get_values(model_iter, self.get_cols(labels))
    def set_labelled_value(self, model_iter, label, value):
        self.set_value(model_iter, self.get_col(label), value)
    def set_labelled_values(self, model_iter, label_values):
        col_values = []
        for index in len(label_values):
            if (index % 2) == 0:
                col_values.append(self.get_col(label_values[index]))
            else:
                col_values.append(label_values[index])
        self.set_values(model_iter, col_values)
    def get_contents(self):
        contents = []
        model_iter = self.get_iter_first()
        while model_iter:
            contents.append(self.get_row(model_iter))
            model_iter = self.iter_next(model_iter)
        return contents
    def get_row_with_key_value(self, key_value, key=None):
        if key is None:
            index = 0
        elif isinstance(key, int):
            index = key
        else:
            index = self.get_col(key)
        model_iter = self.get_iter_first()
        while model_iter:
            if self.get_value(model_iter, index) == key_value:
                return model_iter
            else:
                model_iter = self.iter_next(model_iter)
        return None

class ListStore(Model, gtk.ListStore):
    def __init__(self, descr):
        """descr is a named tuple"""
        Model.__init__(self, descr)
        gtk.ListStore.__init__(*[self] + list(descr))
    def append_contents(self, rows):
        for row in rows:
            self.append(row)
    def set_contents(self, rows):
        self.clear()
        for row in rows:
            self.append(row)

class TreeStore(Model, gtk.TreeStore):
    def __init__(self, descr):
        """descr is a named tuple"""
        Model.__init__(self, descr)
        gtk.TreeStore.__init__(*[self] + list(descr))
    def insert_contents(self, rows):
        assert True, "append_contents(%s) must be defined in child" % rows
    def set_contents(self, rows):
        assert True, "set_contents(%s) must be defined in child" % rows

ViewTemplate = collections.namedtuple('ViewTemplate', ['properties', 'selection_mode', 'columns'])
#properties is a dictionary: {property_name: value, ...}
#selection_mode is one of gtk.SELECTION_NONE, gtk.SELECTION_SINGLE,
#    gtk.SELECTION_BROWSE or gtk.SELECTION_MULTIPLE
#column_descr is class Column

Column = collections.namedtuple('Column', ['title', 'properties', 'cells'])
#title is a string
#properties is a dictionary: {property_name: value, ...}
#selection_mode is one of gtk.SELECTION_NONE, gtk.SELECTION_SINGLE,
#    gtk.SELECTION_BROWSE or gtk.SELECTION_MULTIPLE
#cells is a list of class Cell

CellCreator = collections.namedtuple('CellCreator', ['function', 'expand', 'start'])
#function is a gtk cell class creation function
#expand is boolean
#start is boolean

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

Renderer = collections.namedtuple('Renderer', ['function', 'user_data'])

Cell = collections.namedtuple('Cell', ['creator', 'properties', 'renderer', 'attributes'])
#creator is a class CellCreator
#properties is a dictionary: {property_name: value, ...}
#renderer is a named tuple Renderer
#attributes is a dictionary: {attribute_name: index, ...}

ColumnAndCells = collections.namedtuple('ColumnAndCells', ['column', 'cells'])

class View(gtk.TreeView):
    def __init__(self, descr, model=None):
        gtk.TreeView.__init__(self, model)
        for prop_name, prop_val in descr.properties.items():
            self.set_property(prop_name, prop_val)
        if descr.selection_mode is not None:
            self.get_selection().set_mode(descr.selection_mode)
        self._view_col_dict = {}
        self._view_col_list = []
        for col_d in descr.columns:
            self._view_add_column(col_d)
        self.connect("button_press_event", self._handle_button_press_cb)
        self._modified_cbs = []
    def _view_add_column(self, col_d):
        col = gtk.TreeViewColumn(col_d.title)
        col_cells = ColumnAndCells(col, [])
        self._view_col_dict[col_d.title] = col_cells
        self._view_col_list.append(col_cells)
        self.append_column(col)
        for prop_name, prop_val in col_d.properties.items():
            col.set_property(prop_name, prop_val)
        for cell_d in col_d.cells:
            self._view_add_cell(col, cell_d)
    def _view_add_cell(self, col, cell_d):
        cell = _create_cell(col, cell_d.creator)
        self._view_col_dict[col.get_title()].cells.append(cell)
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
        return self._view_col_dict[title].column
    def get_cell_with_title(self, title, index=0):
        return self._view_col_dict[title].cells[index]
    def get_cell(self, col_index, cell_index=0):
        return self._view_col_list[col_index].cells[cell_index]

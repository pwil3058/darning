### Copyright (C) 2011 Peter Williams <peter@users.sourceforge.net>
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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gtk
import gobject
import collections
import os

from darning.gui import tlview
from darning.gui import gutils
from darning.gui import ifce
from darning.gui import actions

class Tree(tlview.TreeView):
    class Model(tlview.TreeView.Model):
        Row = collections.namedtuple('Row', ['name', 'is_dir', 'style', 'foreground', 'icon', 'status', 'origin'])
        types = Row(
            name=gobject.TYPE_STRING,
            is_dir=gobject.TYPE_BOOLEAN,
            style=gobject.TYPE_INT,
            foreground=gobject.TYPE_STRING,
            icon=gobject.TYPE_STRING,
            status=gobject.TYPE_STRING,
            origin=gobject.TYPE_STRING
        )
    #@staticmethod
    def _format_file_name_crcb(_column, cell_renderer, store, tree_iter, _arg=None):
        name = store.get_value(tree_iter, store.col_index('name'))
        xinfo = store.get_value(tree_iter, store.col_index('origin'))
        if xinfo:
            name += ' <- %s' % xinfo
        cell_renderer.set_property('text', name)
    template =tlview.TreeView.Template(
        properties={'headers-visible' : False},
        selection_mode=gtk.SELECTION_MULTIPLE,
        columns=[
            tlview.TreeView.Column(
                title='File Name',
                properties={},
                cells=[
                    tlview.TreeView.Cell(
                        creator=tlview.TreeView.CellCreator(
                            function=gtk.CellRendererPixbuf,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        renderer=None,
                        attributes={'stock-id' : Model.col_index('icon')}
                    ),
                    tlview.TreeView.Cell(
                        creator=tlview.TreeView.CellCreator(
                            function=gtk.CellRendererText,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        renderer=None,
                        attributes={'text' : Model.col_index('status'), 'style' : Model.col_index('style'), 'foreground' : Model.col_index('foreground')}
                    ),
                    tlview.TreeView.Cell(
                        creator=tlview.TreeView.CellCreator(
                            function=gtk.CellRendererText,
                            expand=False,
                            start=True
                        ),
                        properties={},
                        renderer=tlview.TreeView.Renderer(function=_format_file_name_crcb, user_data=None),
                        attributes={'style' : Model.col_index('style'), 'foreground' : Model.col_index('foreground')}
                    )
                ]
            )
        ]
    )
    def __init__(self, show_hidden=False, populate_all=False):
        tlview.TreeView.__init__(self)
        self.show_hidden_action = gtk.ToggleAction('show_hidden_files', 'Show Hidden Files',
                                                   'Show/hide ignored files and those beginning with "."', None)
        self.show_hidden_action.set_active(show_hidden)
        self.show_hidden_action.connect('toggled', self._toggle_show_hidden_cb)
        self.show_hidden_action.set_menu_item_type(gtk.CheckMenuItem)
        self.show_hidden_action.set_tool_item_type(gtk.ToggleToolButton)
        self._populate_all = populate_all
        self.connect("row-expanded", self.on_row_expanded_cb)
        self.connect("row-collapsed", self.on_row_collapsed_cb)
        self._file_db = None
        self.repopulate()
    def _update_iter_row_tuple(self, fsobj_iter, to_tuple):
        for label in ['style', 'foreground', 'status', 'origin']:
            index = self.model.col_index(label)
            self.model.set_value(fsobj_iter, index, to_tuple[index])
    def _toggle_show_hidden_cb(self, toggleaction):
        self._update_dir('', None)
    def _get_dir_contents(self, dirpath):
        return self._file_db.dir_contents(dirpath, self.show_hidden_action.get_active())
    def _insert_place_holder(self, dir_iter):
        self.model.append(dir_iter)
    def _insert_place_holder_if_needed(self, dir_iter):
        if self.model.iter_n_children(dir_iter) == 0:
            self._insert_place_holder(dir_iter)
    def _remove_place_holder(self, dir_iter):
        child_iter = self.model.iter_children(dir_iter)
        if child_iter and self.model.get_labelled_value(child_iter, 'name') is None:
            self.model.remove(child_iter)
    def _row_expanded(self, dir_iter):
        return self.row_expanded(self.model.get_path(dir_iter))
    def fs_path(self, fsobj_iter):
        if fsobj_iter is None:
            return None
        parent_iter = self.model.iter_parent(fsobj_iter)
        name = self.model.get_labelled_value(fsobj_iter, 'name')
        if parent_iter is None:
            return name
        else:
            if name is None:
                return os.path.join(self.fs_path(parent_iter), '')
            return os.path.join(self.fs_path(parent_iter), name)
    def on_row_expanded_cb(self, _view, dir_iter, _dummy):
        assert self == _view
        if not self._populate_all:
            self._update_dir(self.fs_path(dir_iter), dir_iter)
            if self.model.iter_n_children(dir_iter) > 1:
                self._remove_place_holder(dir_iter)
    def on_row_collapsed_cb(self, _view, dir_iter, _dummy):
        assert self == _view
        self._insert_place_holder_if_needed(dir_iter)
    def _populate(self, dirpath, parent_iter):
        dirs, files = self._get_dir_contents(dirpath)
        for dirdata in dirs:
            row_tuple = self._generate_row_tuple(dirdata, True)
            dir_iter = self.model.append(parent_iter, row_tuple)
            if self._populate_all:
                self._populate(os.path.join(dirpath, dirdata.name), dir_iter)
                if self._expand_new_rows():
                    self.expand_row(self.get_path(dir_iter), True)
            else:
                self._insert_place_holder(dir_iter)
        for filedata in files:
            row_tuple = self._generate_row_tuple(filedata, False)
            dummy = self.model.append(parent_iter, row_tuple)
        if parent_iter is not None:
            self._insert_place_holder_if_needed(parent_iter)
    def _update_dir(self, dirpath, parent_iter=None):
        if parent_iter is None:
            child_iter = self.model.get_iter_first()
        else:
            child_iter = self.model.iter_children(parent_iter)
            if child_iter:
                if self.model.get_labelled_value(child_iter, 'name') is None:
                    child_iter = self.model.iter_next(child_iter)
        dirs, files = self._get_dir_contents(dirpath)
        dead_entries = []
        for dirdata in dirs:
            row_tuple = self._generate_row_tuple(dirdata, True)
            while (child_iter is not None) and self.model.get_labelled_value(child_iter, 'is_dir') and (self.model.get_labelled_value(child_iter, 'name') < dirdata.name):
                dead_entries.append(child_iter)
                child_iter = self.model.iter_next(child_iter)
            if child_iter is None:
                dir_iter = self.model.append(parent_iter, row_tuple)
                if self._populate_all:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    if self._expand_new_rows():
                        self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self._insert_place_holder(dir_iter)
                continue
            name = self.model.get_labelled_value(child_iter, 'name')
            if (not self.model.get_labelled_value(child_iter, 'is_dir')) or (name > dirdata.name):
                dir_iter = self.model.insert_before(parent_iter, child_iter, row_tuple)
                if self._populate_all:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    if self._expand_new_rows():
                        self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self._insert_place_holder(dir_iter)
                continue
            self._update_iter_row_tuple(child_iter, row_tuple)
            if self._populate_all or self._row_expanded(child_iter):
                self._update_dir(os.path.join(dirpath, name), child_iter)
            child_iter = self.model.iter_next(child_iter)
        while (child_iter is not None) and self.model.get_labelled_value(child_iter, 'is_dir'):
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        for filedata in files:
            row_tuple = self._generate_row_tuple(filedata, False)
            while (child_iter is not None) and (self.model.get_labelled_value(child_iter, 'name') < filedata.name):
                dead_entries.append(child_iter)
                child_iter = self.model.iter_next(child_iter)
            if child_iter is None:
                dummy = self.model.append(parent_iter, row_tuple)
                continue
            if self.model.get_labelled_value(child_iter, 'name') > filedata.name:
                dummy = self.model.insert_before(parent_iter, child_iter, row_tuple)
                continue
            self._update_iter_row_tuple(child_iter, row_tuple)
            child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        for dead_entry in dead_entries:
            self._recursive_remove(dead_entry)
        if parent_iter is not None:
            self._insert_place_holder_if_needed(parent_iter)
    @staticmethod
    def _get_file_db():
        assert False, '_get_file_db() must be defined in descendants'
    def repopulate(self):
        self._file_db = self._get_file_db()
        self.model.clear()
        self._populate('', self.model.get_iter_first())
    def update(self):
        self._file_db = self._get_file_db()
        self._update_dir('', None)

class ScmTreeWidget(gtk.VBox):
    class ScmTree(Tree, actions.AGandUIManager):
        UI_DESCR = '''
        <ui>
        </ui>
        '''
        _FILE_ICON = {True : gtk.STOCK_DIRECTORY, False : gtk.STOCK_FILE}
        @staticmethod
        def _get_file_db():
            return ifce.SCM.get_file_db()
        @staticmethod
        def _generate_row_tuple(data, isdir=None):
            deco = ifce.SCM.get_status_deco(data.status)
            row = ScmTreeWidget.ScmTree.Model.Row(
                name=data.name,
                is_dir=isdir,
                icon=ScmTreeWidget.ScmTree._FILE_ICON[isdir],
                status=data.status,
                origin=data.origin,
                style=deco.style,
                foreground=deco.foreground
            )
            return row
        def __init__(self):
            Tree.__init__(self)
            actions.AGandUIManager.__init__(self, self.get_selection())
            self.add_conditional_action(actions.Condns.DONT_CARE, self.show_hidden_action)
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
    def __init__(self):
        gtk.VBox.__init__(self)
        self.tree = self.ScmTree()
        self.pack_start(gutils.wrap_in_scrolled_window(self.tree), expand=True, fill=True)
        hbox = gtk.HBox()
        for action_name in ['show_hidden_files']:
            button = gtk.CheckButton()
            action = self.tree.get_conditional_action(action_name)
            action.connect_proxy(button)
            gutils.set_widget_tooltip_text(button, action.get_property('tooltip'))
            hbox.pack_start(button)
        self.pack_end(hbox, expand=False, fill=False)
        self.show_all()

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

from darning import utils
from darning import patch_db

from darning.gui import tlview
from darning.gui import gutils
from darning.gui import ifce
from darning.gui import actions
from darning.gui import dialogue
from darning.gui import ws_event
from darning.gui import icons
from darning.gui import text_edit

class Tree(tlview.TreeView, actions.AGandUIManager):
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
        def remove_place_holder(self, dir_iter):
            child_iter = self.iter_children(dir_iter)
            if child_iter and self.get_labelled_value(child_iter, 'name') is None:
                self.remove(child_iter)
        def fs_path(self, fsobj_iter):
            if fsobj_iter is None:
                return None
            parent_iter = self.iter_parent(fsobj_iter)
            name = self.get_labelled_value(fsobj_iter, 'name')
            if parent_iter is None:
                return name
            else:
                if name is None:
                    return os.path.join(self.fs_path(parent_iter), '')
                return os.path.join(self.fs_path(parent_iter), name)
        def on_row_expanded_cb(self, view, dir_iter, _dummy):
            if not view._populate_all:
                view._update_dir(self.fs_path(dir_iter), dir_iter)
                if self.iter_n_children(dir_iter) > 1:
                    self.remove_place_holder(dir_iter)
        def on_row_collapsed_cb(self, _view, dir_iter, _dummy):
            self.insert_place_holder_if_needed(dir_iter)
        def update_iter_row_tuple(self, fsobj_iter, to_tuple):
            for label in ['style', 'foreground', 'status', 'origin', 'icon']:
                index = self.col_index(label)
                self.set_value(fsobj_iter, index, to_tuple[index])
    # This is not a method but a function within the Tree namespace
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
    KEYVAL_c = gtk.gdk.keyval_from_name('c')
    KEYVAL_C = gtk.gdk.keyval_from_name('C')
    KEYVAL_ESCAPE = gtk.gdk.keyval_from_name('Escape')
    @staticmethod
    def _handle_button_press_cb(widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button == 3:
                menu = widget.ui_manager.get_widget('/files_popup')
                if menu is not None:
                    menu.popup(None, None, None, event.button, event.time)
                return True
            elif event.button == 2:
                widget.get_selection().unselect_all()
                return True
        return False
    @staticmethod
    def _handle_key_press_cb(widget, event):
        if event.state & gtk.gdk.CONTROL_MASK:
            if event.keyval in [Tree.KEYVAL_c, Tree.KEYVAL_C]:
                widget.add_selected_files_to_clipboard()
                return True
        elif event.keyval == Tree.KEYVAL_ESCAPE:
            widget.get_selection().unselect_all()
            return True
        return False
    @staticmethod
    def search_equal_func(model, column, key, model_iter, _data=None):
        text = model.fs_path(model_iter)
        return text.find(key) == -1
    def __init__(self, show_hidden=False, populate_all=False, auto_expand=False, auto_refresh=False):
        tlview.TreeView.__init__(self)
        self.set_search_equal_func(self.search_equal_func)
        actions.AGandUIManager.__init__(self, self.get_selection())
        self.show_hidden_action = gtk.ToggleAction('show_hidden_files', 'Show Hidden Files',
                                                   'Show/hide ignored files and those beginning with "."', None)
        self.show_hidden_action.set_active(show_hidden)
        self.show_hidden_action.connect('toggled', self._toggle_show_hidden_cb)
        self.show_hidden_action.set_menu_item_type(gtk.CheckMenuItem)
        self.show_hidden_action.set_tool_item_type(gtk.ToggleToolButton)
        self.add_conditional_action(actions.Condns.DONT_CARE, self.show_hidden_action)
        self._refresh_interval = 20000 # milliseconds
        self.auto_refresh_action = gtk.ToggleAction('auto_refresh_files', 'Auto Refresh Files',
                                                   'Automatically/periodically refresh file display', None)
        self.auto_refresh_action.set_active(auto_refresh)
        self.auto_refresh_action.connect('toggled', self._toggle_auto_refresh_cb)
        self.auto_refresh_action.set_menu_item_type(gtk.CheckMenuItem)
        self.auto_refresh_action.set_tool_item_type(gtk.ToggleToolButton)
        self.add_conditional_action(actions.Condns.DONT_CARE, self.auto_refresh_action)
        self.add_conditional_actions(actions.Condns.DONT_CARE,
            [
                ('refresh_files', gtk.STOCK_REFRESH, '_Refresh Files', None,
                 'Refresh/update the file tree display', self.update),
            ])
        self._populate_all = populate_all
        self._auto_expand = auto_expand
        self.connect("row-expanded", self.model.on_row_expanded_cb)
        self.connect("row-collapsed", self.model.on_row_collapsed_cb)
        self.connect('button_press_event', self._handle_button_press_cb)
        self.connect('key_press_event', self._handle_key_press_cb)
        self._file_db = None
        self.repopulate()
        self._toggle_auto_refresh_cb()
    def _toggle_show_hidden_cb(self, toggleaction):
        dialogue.show_busy()
        self._update_dir('', None)
        dialogue.unshow_busy()
    def _do_auto_refresh(self):
        if self.auto_refresh_action.get_active():
            self.update()
            return True
        else:
            return False
    def _toggle_auto_refresh_cb(self, action=None):
        if self.auto_refresh_action.get_active():
            gobject.timeout_add(self._refresh_interval, self._do_auto_refresh)
    def _get_dir_contents(self, dirpath):
        return self._file_db.dir_contents(dirpath, self.show_hidden_action.get_active())
    def _row_expanded(self, dir_iter):
        return self.row_expanded(self.model.get_path(dir_iter))
    def _populate(self, dirpath, parent_iter):
        dirs, files = self._get_dir_contents(dirpath)
        for dirdata in dirs:
            row_tuple = self._generate_row_tuple(dirdata, True)
            dir_iter = self.model.append(parent_iter, row_tuple)
            if self._populate_all:
                self._populate(os.path.join(dirpath, dirdata.name), dir_iter)
                if self._auto_expand:
                    self.expand_row(self.model.get_path(dir_iter), True)
            else:
                self.model.insert_place_holder(dir_iter)
        for filedata in files:
            row_tuple = self._generate_row_tuple(filedata, False)
            dummy = self.model.append(parent_iter, row_tuple)
        if parent_iter is not None:
            self.model.insert_place_holder_if_needed(parent_iter)
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
                    if self._auto_expand:
                        self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self.model.insert_place_holder(dir_iter)
                continue
            name = self.model.get_labelled_value(child_iter, 'name')
            if (not self.model.get_labelled_value(child_iter, 'is_dir')) or (name > dirdata.name):
                dir_iter = self.model.insert_before(parent_iter, child_iter, row_tuple)
                if self._populate_all:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    if self._auto_expand:
                        self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self.model.insert_place_holder(dir_iter)
                continue
            self.model.update_iter_row_tuple(child_iter, row_tuple)
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
            self.model.update_iter_row_tuple(child_iter, row_tuple)
            child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        for dead_entry in dead_entries:
            self.model.recursive_remove(dead_entry)
        if parent_iter is not None:
            self.model.insert_place_holder_if_needed(parent_iter)
    def _get_file_db():
        assert False, '_get_file_db() must be defined in descendants'
    def repopulate(self, _arg=None):
        dialogue.show_busy()
        self._file_db = self._get_file_db()
        self.model.clear()
        self._populate('', self.model.get_iter_first())
        dialogue.unshow_busy()
    def update(self, _arg=None):
        dialogue.show_busy()
        self._file_db = self._get_file_db()
        self._update_dir('', None)
        dialogue.unshow_busy()
    def get_selected_files(self):
        store, selection = self.get_selection().get_selected_rows()
        return [store.fs_path(store.get_iter(x)) for x in selection]
    def add_selected_files_to_clipboard(self, clipboard=None):
        if not clipboard:
            clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)
        sel = utils.file_list_to_string(self.get_selected_files())
        clipboard.set_text(sel)
    def get_filepaths_in_dir(self, dirname, recursive=True):
        subdirs, files = self._file_db.dir_contents(dirname, show_hidden=True)
        filepaths = [os.path.join(dirname, fdata.name) for fdata in files]
        if recursive:
            for subdir in subdirs:
                filepaths += self.get_filepaths_in_dir(os.path.join(dirname, subdir.name), recursive)
        return filepaths

class ScmFileTreeWidget(gtk.VBox, ws_event.Listener):
    class ScmTree(Tree):
        UI_DESCR = '''
        <ui>
          <menubar name="scm_files_menubar">
            <menu name="scm_files_menu" action="scm_files_menu_files">
              <menuitem action="refresh_files"/>
              <menuitem action="auto_refresh_files"/>
            </menu>
          </menubar>
          <popup name="files_popup">
            <placeholder name="selection_indifferent"/>
            <separator/>
            <placeholder name="selection">
              <menuitem action='scm_add_files_to_top_patch'/>
            </placeholder>
            <separator/>
            <placeholder name="selection_not_patched"/>
            <separator/>
            <placeholder name="unique_selection"/>
            <separator/>
            <placeholder name="no_selection"/>
            <separator/>
            <placeholder name="no_selection_not_patched"/>
            <separator/>
          </popup>
        </ui>
        '''
        _FILE_ICON = {True : gtk.STOCK_DIRECTORY, False : gtk.STOCK_FILE}
        @staticmethod
        def _get_file_db():
            return ifce.SCM.get_file_db()
        @staticmethod
        def _generate_row_tuple(data, isdir):
            deco = ifce.SCM.get_status_deco(data.status)
            row = ScmFileTreeWidget.ScmTree.Model.Row(
                name=data.name,
                is_dir=isdir,
                icon=ScmFileTreeWidget.ScmTree._FILE_ICON[isdir],
                status=data.status,
                origin=data.origin,
                style=deco.style,
                foreground=deco.foreground
            )
            return row
        def __init__(self, auto_refresh=False, hide_clean=False):
            self.hide_clean_action = gtk.ToggleAction('hide_clean_files', 'Hide Clean Files',
                                                       'Show/hide "clean" files', None)
            self.hide_clean_action.set_active(hide_clean)
            Tree.__init__(self, show_hidden=False, populate_all=False, auto_expand=False, auto_refresh=auto_refresh)
            self.hide_clean_action.connect('toggled', self._toggle_hide_clean_cb)
            self.hide_clean_action.set_menu_item_type(gtk.CheckMenuItem)
            self.hide_clean_action.set_tool_item_type(gtk.ToggleToolButton)
            self.add_conditional_action(actions.Condns.DONT_CARE, self.hide_clean_action)
            self.add_conditional_actions(actions.Condns.DONT_CARE,
                [
                    ('scm_files_menu_files', None, '_Files'),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('scm_add_files_to_top_patch', gtk.STOCK_ADD, '_Add', None,
                     'Add the selected files to the top patch', self._add_selection_to_top_patch),
                ])
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
            self.add_notification_cb(ws_event.CHECKOUT|ws_event.CHANGE_WD, self.repopulate)
            self.add_notification_cb(ws_event.FILE_CHANGES, self.update)
        def _toggle_hide_clean_cb(self, toggleaction):
            dialogue.show_busy()
            self._update_dir('', None)
            dialogue.unshow_busy()
        def _get_dir_contents(self, dirpath):
            show_hidden = self.show_hidden_action.get_active()
            if not show_hidden and self.hide_clean_action.get_active():
                dirs, files = self._file_db.dir_contents(dirpath, show_hidden)
                return ([ncd for ncd in dirs if not ifce.SCM.is_clean(ncd.status)],
                        [ncf for ncf in files if not ifce.SCM.is_clean(ncf.status)])
            return self._file_db.dir_contents(dirpath, show_hidden)
        def _add_selection_to_top_patch(self, _action=None):
            files = self.get_selected_files()
            if len(files) == 0:
                return
            dialogue.show_busy()
            result = ifce.PM.do_add_files_to_patch(files)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
    def __init__(self, auto_refresh=False, hide_clean=False):
        gtk.VBox.__init__(self)
        ws_event.Listener.__init__(self)
        hbox = gtk.HBox()
        name = ifce.SCM.get_name()
        self.scm_label = gtk.Label('' if not name else (name + ':'))
        self.tree = self.ScmTree(auto_refresh=auto_refresh, hide_clean=hide_clean)
        hbox.pack_start(self.scm_label, expand=False, fill=False)
        hbox.pack_start(self.tree.ui_manager.get_widget('/scm_files_menubar'), expand=True, fill=True)
        self.pack_start(hbox, expand=False, fill=False)
        self.pack_start(gutils.wrap_in_scrolled_window(self.tree), expand=True, fill=True)
        hbox = gtk.HBox()
        for action_name in ['show_hidden_files', 'hide_clean_files']:
            button = gtk.CheckButton()
            action = self.tree.get_conditional_action(action_name)
            action.connect_proxy(button)
            gutils.set_widget_tooltip_text(button, action.get_property('tooltip'))
            hbox.pack_start(button)
        self.pack_end(hbox, expand=False, fill=False)
        self.show_all()
        self.add_notification_cb(ws_event.CHANGE_WD, self._cwd_change_cb)
    def _cwd_change_cb(self):
        name = ifce.SCM.get_name()
        self.scm_label.set_text('' if not name else (name + ':'))

class PatchFileTreeWidget(gtk.VBox):
    class PatchFileTree(Tree):
        @staticmethod
        def _generate_row_tuple(data, isdir):
            deco = ifce.PM.get_status_deco(data.status)
            if isdir:
                icon = gtk.STOCK_DIRECTORY
            elif data.status.validity == patch_db.FileData.Validity.REFRESHED:
                icon = icons.STOCK_FILE_REFRESHED
            elif data.status.validity == patch_db.FileData.Validity.NEEDS_REFRESH:
                icon = icons.STOCK_FILE_NEEDS_REFRESH
            elif data.status.validity == patch_db.FileData.Validity.UNREFRESHABLE:
                icon = icons.STOCK_FILE_UNREFRESHABLE
            else:
                icon = gtk.STOCK_FILE
            row = PatchFileTreeWidget.PatchFileTree.Model.Row(
                name=data.name,
                is_dir=isdir,
                icon=icon,
                status='',
                origin=data.origin,
                style=deco.style,
                foreground=deco.foreground
            )
            return row
        def __init__(self, patch=None, auto_refresh=True):
            self.patch = patch
            Tree.__init__(self, show_hidden=True, populate_all=True, auto_expand=True, auto_refresh=auto_refresh)
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('patch_edit_files', gtk.STOCK_EDIT, '_Edit', None,
                     'Edit the selected file(s)', self.edit_selected_files_acb),
                ])
            self.add_notification_cb(ws_event.CHECKOUT|ws_event.CHANGE_WD|ws_event.PATCH_PUSH|ws_event.PATCH_POP, self.repopulate)
            self.add_notification_cb(ws_event.FILE_CHANGES|ws_event.PATCH_REFRESH, self.update)
        def _get_file_db(self):
            return ifce.PM.get_file_db(self.patch)
        def _edit_named_files_extern(self, file_list):
            text_edit.edit_files_extern(file_list)
        def edit_selected_files_acb(self, _menu_item):
            self._edit_named_files_extern(self.get_selected_files())
    def __init__(self, patch=None, auto_refresh=True):
        gtk.VBox.__init__(self)
        self.tree = self.PatchFileTree(patch=patch, auto_refresh=auto_refresh)
        self.pack_start(gutils.wrap_in_scrolled_window(self.tree), expand=True, fill=True)
        self.show_all()

class TopPatchFileTreeWidget(PatchFileTreeWidget):
    class PatchFileTree(PatchFileTreeWidget.PatchFileTree):
        UI_DESCR = '''
        <ui>
          <popup name="files_popup">
            <placeholder name="selection_indifferent"/>
            <separator/>
            <placeholder name="selection">
              <menuitem action='patch_edit_files'/>
              <menuitem action='top_patch_drop_selected_files'/>
            </placeholder>
            <separator/>
            <placeholder name="selection_not_patched"/>
            <separator/>
            <placeholder name="unique_selection"/>
            <separator/>
            <placeholder name="no_selection"/>
            <separator/>
            <placeholder name="no_selection_not_patched"/>
            <separator/>
          </popup>
        </ui>
        '''
        def __init__(self, patch=None, auto_refresh=True):
            assert patch is None
            PatchFileTreeWidget.PatchFileTree.__init__(self, patch=None, auto_refresh=auto_refresh)
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('top_patch_drop_selected_files', gtk.STOCK_REMOVE, '_Drop', None,
                     'Drop/remove the selected files from the top patch', self._drop_selection_from_patch),
                ])
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
        def _drop_selection_from_patch(self, _arg):
            files = self.get_selected_files()
            if len(files) == 0:
                return
            file_list = []
            for path in files:
                if os.path.isdir(path):
                    file_list += self.get_filepaths_in_dir(path, recursive=True)
                else:
                    file_list.append(path)
            emsg = '\n'.join(file_list + ["", "Confirm drop selected file(s) from patch?"])
            if not dialogue.ask_ok_cancel(emsg):
                return
            dialogue.show_busy()
            result = ifce.PM.do_drop_files_from_patch(file_list, self.patch)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
    def __init__(self, patch=None, auto_refresh=True):
        assert patch is None
        PatchFileTreeWidget.__init__(self, patch=None, auto_refresh=auto_refresh)

class CombinedPatchFileTreeWidget(PatchFileTreeWidget):
    class PatchFileTree(PatchFileTreeWidget.PatchFileTree):
        UI_DESCR = '''
        <ui>
          <popup name="files_popup">
            <placeholder name="selection_indifferent"/>
            <separator/>
            <placeholder name="selection">
              <menuitem action='patch_edit_files'/>
            </placeholder>
            <separator/>
            <placeholder name="selection_not_patched"/>
            <separator/>
            <placeholder name="unique_selection"/>
            <separator/>
            <placeholder name="no_selection"/>
            <separator/>
            <placeholder name="no_selection_not_patched"/>
            <separator/>
          </popup>
        </ui>
        '''
        def _get_file_db(self):
            return ifce.PM.get_combined_patch_file_db()
        def __init__(self, patch=None, auto_refresh=True):
            assert patch is None
            PatchFileTreeWidget.PatchFileTree.__init__(self, patch=None, auto_refresh=auto_refresh)
            self.ui_manager.add_ui_from_string(self.UI_DESCR)

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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import gtk
import gobject
import collections
import os

from darning import utils
from darning import patch_db
from darning import cmd_result
from darning import fsdb

from darning.gui import tlview
from darning.gui import gutils
from darning.gui import ifce
from darning.gui import actions
from darning.gui import dialogue
from darning.gui import ws_event
from darning.gui import icons
from darning.gui import text_edit
from darning.gui import diff

class Tree(tlview.TreeView, actions.AGandUIManager):
    class Model(tlview.TreeView.Model):
        Row = collections.namedtuple('Row', ['name', 'is_dir', 'style', 'foreground', 'icon', 'status', 'related_file_str'])
        types = Row(
            name=gobject.TYPE_STRING,
            is_dir=gobject.TYPE_BOOLEAN,
            style=gobject.TYPE_INT,
            foreground=gobject.TYPE_STRING,
            icon=gobject.TYPE_STRING,
            status=gobject.TYPE_STRING,
            related_file_str=gobject.TYPE_STRING
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
            for label in ['style', 'foreground', 'status', 'related_file_str', 'icon']:
                index = self.col_index(label)
                self.set_value(fsobj_iter, index, to_tuple[index])
    # This is not a method but a function within the Tree namespace
    def _format_file_name_crcb(_column, cell_renderer, store, tree_iter, _arg=None):
        name = store.get_value(tree_iter, store.col_index('name'))
        name += store.get_value(tree_iter, store.col_index('related_file_str'))
        cell_renderer.set_property('text', name)
    template =tlview.TreeView.Template(
        properties={'headers-visible' : False},
        selection_mode=gtk.SELECTION_MULTIPLE,
        columns=[
            tlview.TreeView.Column(
                title=_('File Name'),
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
    def _get_related_file_str(data):
        if data.related_file:
            return ' {0} {1}'.format(data.related_file.relation, data.related_file.path)
        return ''
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
    def __init__(self, show_hidden=False, populate_all=False, auto_expand=False):
        tlview.TreeView.__init__(self)
        self.set_search_equal_func(self.search_equal_func)
        actions.AGandUIManager.__init__(self, self.get_selection())
        self.show_hidden_action = gtk.ToggleAction('show_hidden_files', _('Show Hidden Files'),
                                                   _('Show/hide ignored files and those beginning with "."'), None)
        self.show_hidden_action.set_active(show_hidden)
        self.show_hidden_action.connect('toggled', self._toggle_show_hidden_cb)
        self.show_hidden_action.set_menu_item_type(gtk.CheckMenuItem)
        self.show_hidden_action.set_tool_item_type(gtk.ToggleToolButton)
        self.add_conditional_action(actions.Condns.DONT_CARE, self.show_hidden_action)
        self.add_conditional_actions(actions.Condns.DONT_CARE,
            [
                ('refresh_files', gtk.STOCK_REFRESH, _('_Refresh Files'), None,
                 _('Refresh/update the file tree display'), self.update),
            ])
        self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.UNIQUE_SELN,
            [
                ('copy_file_to_top_patch', gtk.STOCK_COPY, _('_Copy'), None,
                 _('Add a copy of the selected file to the top patch'), self._copy_selected_to_top_patch),
                ('rename_file_in_top_patch', icons.STOCK_RENAME, _('_Rename'), None,
                 _('Rename the selected file within the top patch'), self._rename_selected_in_top_patch),
            ])
        self._populate_all = populate_all
        self._auto_expand = auto_expand
        self.connect("row-expanded", self.model.on_row_expanded_cb)
        self.connect("row-collapsed", self.model.on_row_collapsed_cb)
        self.connect('button_press_event', self._handle_button_press_cb)
        self.connect('key_press_event', self._handle_key_press_cb)
        self.get_selection().set_select_function(self._dirs_not_selectable, full=True)
        self._file_db = None
        self.repopulate()
    def _dirs_not_selectable(self, selection, model, path, is_selected, _arg=None):
        if not is_selected:
            return not model.get_labelled_value(model.get_iter(path), 'is_dir')
        return True
    def _toggle_show_hidden_cb(self, toggleaction):
        dialogue.show_busy()
        self._update_dir('', None)
        dialogue.unshow_busy()
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
    def get_iter_for_filepath(self, filepath):
        pathparts = fsdb.split_path(filepath)
        child_iter = self.model.get_iter_first()
        for index in range(len(pathparts) - 1):
            while child_iter is not None:
                if self.model.get_labelled_value(child_iter, 'name') == pathparts[index]:
                    tpath = self.model.get_path(child_iter)
                    if not self.row_expanded(tpath):
                        self.expand_row(tpath, False)
                    child_iter = self.model.iter_children(child_iter)
                    break
                child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            if self.model.get_labelled_value(child_iter, 'name') == pathparts[-1]:
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
                changed = True
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
                changed = True
                if self._populate_all:
                    self._update_dir(os.path.join(dirpath, dirdata.name), dir_iter)
                    if self._auto_expand:
                        self.expand_row(self.model.get_path(dir_iter), True)
                else:
                    self.model.insert_place_holder(dir_iter)
                continue
            changed |= self.model.get_labelled_value(child_iter, 'icon') != row_tuple.icon
            self.model.update_iter_row_tuple(child_iter, row_tuple)
            if self._populate_all or self._row_expanded(child_iter):
                changed |= self._update_dir(os.path.join(dirpath, name), child_iter)
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
                changed = True
                continue
            if self.model.get_labelled_value(child_iter, 'name') > filedata.name:
                dummy = self.model.insert_before(parent_iter, child_iter, row_tuple)
                changed = True
                continue
            changed |= self.model.get_labelled_value(child_iter, 'icon') != row_tuple.icon
            self.model.update_iter_row_tuple(child_iter, row_tuple)
            child_iter = self.model.iter_next(child_iter)
        while child_iter is not None:
            dead_entries.append(child_iter)
            child_iter = self.model.iter_next(child_iter)
        changed |= len(dead_entries) > 0
        for dead_entry in dead_entries:
            self.model.recursive_remove(dead_entry)
        if parent_iter is not None:
            self.model.insert_place_holder_if_needed(parent_iter)
        return changed
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
    def get_filepaths_in_dir(self, dirname, show_hidden=True, recursive=True):
        subdirs, files = self._file_db.dir_contents(dirname, show_hidden=show_hidden)
        filepaths = [os.path.join(dirname, fdata.name) for fdata in files]
        if recursive:
            for subdir in subdirs:
                filepaths += self.get_filepaths_in_dir(os.path.join(dirname, subdir.name), recursive)
        return filepaths
    def _delete_selection_in_top_patch(self, _action=None):
        file_list = self.get_selected_files()
        if len(file_list) == 0:
            return
        dialogue.show_busy()
        result = ifce.PM.do_delete_files_in_top_patch(file_list)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
    def _copy_selected_to_top_patch(self, _action=None):
        file_list = self.get_selected_files()
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
            if result.eflags & cmd_result.SUGGEST_RENAME != 0:
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
        file_list = self.get_selected_files()
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
                result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
            if not force and result.eflags & cmd_result.SUGGEST_FORCE_ABSORB_OR_REFRESH != 0:
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
            elif result.eflags & cmd_result.SUGGEST_RENAME != 0:
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

class ScmFileTreeWidget(gtk.VBox, ws_event.Listener):
    class ScmTree(Tree):
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
                related_file_str=Tree._get_related_file_str(data),
                style=deco.style,
                foreground=deco.foreground
            )
            return row
        def __init__(self, hide_clean=False):
            self.hide_clean_action = gtk.ToggleAction('hide_clean_files', _('Hide Clean Files'),
                                                       _('Show/hide "clean" files'), None)
            self.hide_clean_action.set_active(hide_clean)
            Tree.__init__(self, show_hidden=False, populate_all=False, auto_expand=False)
            self.hide_clean_action.connect('toggled', self._toggle_hide_clean_cb)
            self.hide_clean_action.set_menu_item_type(gtk.CheckMenuItem)
            self.hide_clean_action.set_tool_item_type(gtk.ToggleToolButton)
            self.add_conditional_action(actions.Condns.DONT_CARE, self.hide_clean_action)
            self.add_conditional_actions(actions.Condns.DONT_CARE,
                [
                    ('scm_files_menu_files', None, _('_Files')),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('scm_add_files_to_top_patch', gtk.STOCK_ADD, _('_Add'), None,
                     _('Add the selected files to the top patch'), self._add_selection_to_top_patch),
                    ('scm_edit_files_in_top_patch', gtk.STOCK_EDIT, _('_Edit'), None,
                     _('Open the selected files for editing after adding them to the top patch'), self._edit_selection_in_top_patch),
                    ('scm_delete_files_in_top_patch', gtk.STOCK_DELETE, _('_Delete'), None,
                     _('Add the selected files to the top patch and then delete them'), self._delete_selection_in_top_patch),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC,
                [
                    ('scm_select_unsettled', None, _('Select _Unsettled'), None,
                     _('Select files that are unrefreshed in patches below top or have uncommitted SCM changes not covered by an applied patch'),
                     self._select_unsettled),
                ])
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
            self.add_notification_cb(ws_event.CHECKOUT|ws_event.CHANGE_WD, self.repopulate)
            self.add_notification_cb(ws_event.FILE_CHANGES|ws_event.AUTO_UPDATE, self.update)
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
                    result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
                if not (absorb or force) and result.eflags & cmd_result.SUGGEST_FORCE_ABSORB_OR_REFRESH != 0:
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
            return result.eflags == cmd_result.OK
        def _add_selection_to_top_patch(self, _action=None):
            file_list = self.get_selected_files()
            if len(file_list) == 0:
                return
            self._add_files_to_top_patch(file_list)
        def _edit_selection_in_top_patch(self, _action=None):
            file_list = self.get_selected_files()
            if len(file_list) == 0:
                return
            if self._add_files_to_top_patch(file_list):
                text_edit.edit_files_extern(file_list)
        def _select_unsettled(self, _action=None):
            unsettled = ifce.PM.get_outstanding_changes_below_top()
            filepaths = [filepath for filepath in unsettled.unrefreshed]
            filepaths += [filepath for filepath in unsettled.uncommitted]
            self.select_filepaths(filepaths)
    def __init__(self, hide_clean=False):
        gtk.VBox.__init__(self)
        ws_event.Listener.__init__(self)
        hbox = gtk.HBox()
        name = ifce.SCM.get_name()
        self.scm_label = gtk.Label('' if not name else (name + ':'))
        self.tree = self.ScmTree(hide_clean=hide_clean)
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
                related_file_str=Tree._get_related_file_str(data),
                style=deco.style,
                foreground=deco.foreground
            )
            return row
        def __init__(self, patch=None):
            self.patch = patch
            Tree.__init__(self, show_hidden=True, populate_all=True, auto_expand=True)
            self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('patch_edit_files', gtk.STOCK_EDIT, _('_Edit'), None,
                     _('Edit the selected file(s)'), self.edit_selected_files_acb),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC + actions.Condns.UNIQUE_SELN,
                [
                    ('patch_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                     _('Display the diff for selected file'), self.diff_selected_file_acb),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.UNIQUE_SELN,
                [
                    ('patch_extdiff_selected_file', icons.STOCK_DIFF, _('E_xtDiff'), None,
                     _('Launch external diff viewer for selected file'), self.extdiff_selected_file_acb),
                ])
            self.add_notification_cb(ws_event.CHECKOUT|ws_event.CHANGE_WD|ws_event.PATCH_PUSH|ws_event.PATCH_POP, self.repopulate)
            self.add_notification_cb(ws_event.FILE_CHANGES|ws_event.PATCH_REFRESH|ws_event.AUTO_UPDATE, self.update)
        def _get_file_db(self):
            return ifce.PM.get_file_db(self.patch)
        def edit_selected_files_acb(self, _action):
            file_list = self.get_selected_files()
            text_edit.edit_files_extern(file_list)
        def diff_selected_file_acb(self, _action):
            filepaths = self.get_selected_files()
            assert len(filepaths) == 1
            dialog = diff.ForFileDialog(filepath=filepaths[0], patchname=self.patch)
            dialog.show()
        def extdiff_selected_file_acb(self, _action):
            filepaths = self.get_selected_files()
            assert len(filepaths) == 1
            files = ifce.PM.get_extdiff_files_for(filepath=filepaths[0], patchname=self.patch)
            dialogue.report_any_problems(diff.launch_external_diff(files.original_version, files.patched_version))
    def __init__(self, patch=None):
        gtk.VBox.__init__(self)
        self.tree = self.PatchFileTree(patch=patch)
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
              <menuitem action='top_patch_delete_selected_files'/>
            </placeholder>
            <separator/>
            <placeholder name="selection_not_patched"/>
            <separator/>
            <placeholder name="unique_selection"/>
              <menuitem action='copy_file_to_top_patch'/>
              <menuitem action='rename_file_in_top_patch'/>
              <menuitem action='patch_reconcile_selected_file'/>
              <menuitem action='patch_diff_selected_file'/>
              <menuitem action='patch_extdiff_selected_file'/>
            <separator/>
            <placeholder name="no_selection"/>
            <separator/>
            <placeholder name="no_selection_not_patched"/>
            <separator/>
          </popup>
        </ui>
        '''
        def __init__(self, patch=None):
            assert patch is None
            PatchFileTreeWidget.PatchFileTree.__init__(self, patch=None)
            self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.SELN,
                [
                    ('top_patch_drop_selected_files', gtk.STOCK_REMOVE, _('_Drop'), None,
                     _('Drop/remove the selected files from the top patch'), self._drop_selection_from_patch),
                    ('top_patch_delete_selected_files', gtk.STOCK_DELETE, _('_Delete'), None,
                     _('Delete the selected files'), self._delete_selection_in_top_patch),
                ])
            self.add_conditional_actions(actions.Condns.IN_PGND_MUTABLE + actions.Condns.PMIC + actions.Condns.UNIQUE_SELN,
                [
                    ('patch_reconcile_selected_file', icons.STOCK_MERGE, _('_Reconcile'), None,
                     _('Launch reconciliation tool for the selected file'), self.reconcile_selected_file_acb),
                ])
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
        def _drop_selection_from_patch(self, _arg):
            file_list = self.get_selected_files()
            if len(file_list) == 0:
                return
            emsg = '\n'.join(file_list + ["", _('Confirm drop selected file(s) from patch?')])
            if not dialogue.ask_ok_cancel(emsg):
                return
            dialogue.show_busy()
            result = ifce.PM.do_drop_files_from_patch(file_list, self.patch)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
        def reconcile_selected_file_acb(self, _action):
            filepaths = self.get_selected_files()
            assert len(filepaths) == 1
            files = ifce.PM.get_reconciliation_paths(filepath=filepaths[0])
            dialogue.report_any_problems(diff.launch_reconciliation_tool(files.original_version, files.patched_version, files.stashed_version))
    def __init__(self, patch=None):
        assert patch is None
        PatchFileTreeWidget.__init__(self, patch=None)

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
              <menuitem action='patch_combined_diff_selected_file'/>
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
        def __init__(self, patch=None):
            assert patch is None
            PatchFileTreeWidget.PatchFileTree.__init__(self, patch=None)
            self.add_conditional_actions(actions.Condns.IN_PGND + actions.Condns.PMIC + actions.Condns.UNIQUE_SELN,
                [
                    ('patch_combined_diff_selected_file', icons.STOCK_DIFF, _('_Diff'), None,
                     _('Display the combined diff for selected file'), self.combined_diff_selected_file_acb),
                ])
            self.ui_manager.add_ui_from_string(self.UI_DESCR)
        def combined_diff_selected_file_acb(self, _action):
            filepaths = self.get_selected_files()
            assert len(filepaths) == 1
            dialog = diff.CombinedForFileDialog(filepath=filepaths[0])
            dialog.show()

def add_new_file_to_top_patch_acb(_action=None):
    filepath = dialogue.ask_file_name(_('Enter path for new file'), existing=False)
    if not filepath:
        return
    ScmFileTreeWidget.ScmTree._add_files_to_top_patch([filepath])


actions.add_class_indep_actions(actions.Condns.PMIC | actions.Condns.IN_PGND_MUTABLE,
    [
        ("file_list_add_new", gtk.STOCK_NEW, _('New'), None,
         _('Add a new file to the top applied patch'), add_new_file_to_top_patch_acb),
    ])

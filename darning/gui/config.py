### Copyright (C) 2005-2011 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import os
import gobject
import gtk
import fnmatch
import collections
import hashlib

from .. import config_data
from .. import utils
from .. import urlops

from . import dialogue
from . import gutils
from . import tlview
from . import table
from . import actions
from . import ifce
from . import icons
from . import ws_event

SAVED_PGND_FILE_NAME = os.sep.join([config_data.CONFIG_DIR_NAME, "playgrounds"])

_KEYVAL_ESCAPE = gtk.gdk.keyval_from_name('Escape')

class AliasPathTable(table.Table):
    SAVED_FILE_NAME = None
    @staticmethod
    def _extant_path(path):
        return os.path.exists(os.path.expanduser(path))
    @staticmethod
    def _same_paths(path1, path2):
        return utils.samefile(os.path.expanduser(path1), path2)
    @staticmethod
    def _default_alias(path):
        return os.path.basename(path)
    @staticmethod
    def _abbrev_path(path):
        return utils.path_rel_home(path)
    @classmethod
    def append_saved_pgnd(cls, path, alias=None):
        if cls._extant_path(path):
            content = cls._fetch_contents()
            found = modified = False
            for row in content:
                if cls._same_paths(row.Path, path):
                    found = True
                    if alias:
                        modified = True
                        row.Alias = alias
                    break
            if not found:
                abbr_path = cls._abbrev_path(path)
                if not alias:
                    alias = os.path.basename(path)
                content.append(cls.View.Model.Row(Path=abbr_path, Alias=alias))
                modified = True
            if modified:
                cls._write_list_to_file(content)
    @classmethod
    def _fetch_contents(cls):
        extant_ap_list = []
        if not os.path.exists(cls.SAVED_FILE_NAME):
            return []
        fobj = open(cls.SAVED_FILE_NAME, 'r')
        lines = fobj.readlines()
        fobj.close()
        for line in lines:
            data = cls.View.Model.Row(*line.strip().split(os.pathsep, 1))
            if data in extant_ap_list:
                continue
            if cls._extant_path(data.Path):
                extant_ap_list.append(data)
        extant_ap_list.sort()
        cls._write_list_to_file(extant_ap_list)
        return extant_ap_list
    @classmethod
    def _write_list_to_file(cls, ap_list):
        fobj = open(cls.SAVED_FILE_NAME, 'w')
        for alpth in ap_list:
            fobj.write(os.pathsep.join(alpth))
            fobj.write(os.linesep)
        fobj.close()
    class View(table.Table.View):
        class Model(table.Table.View.Model):
            Row = collections.namedtuple('Row', ['Alias', 'Path'])
            types = Row(Alias=gobject.TYPE_STRING, Path=gobject.TYPE_STRING)
        specification = tlview.ViewSpec(
            properties={
                'enable-grid-lines' : False,
                'reorderable' : False,
                'rules_hint' : False,
                'headers-visible' : True,
            },
            selection_mode=gtk.SELECTION_SINGLE,
            columns=[
                tlview.ColumnSpec(
                    title=_('Alias'),
                    properties={'expand': False, 'resizable' : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=gtk.CellRendererText,
                                expand=False,
                                start=True
                            ),
                            properties={'editable' : True},
                            cell_data_function_spec=None,
                            attributes = {'text' : Model.col_index('Alias')}
                        ),
                    ],
                ),
                tlview.ColumnSpec(
                    title=_('Path'),
                    properties={'expand': False, 'resizable' : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=gtk.CellRendererText,
                                expand=False,
                                start=True
                            ),
                            properties={'editable' : False},
                            cell_data_function_spec=None,
                            attributes = {'text' : Model.col_index('Path')}
                        ),
                    ],
                ),
            ]
        )
    def __init__(self):
        table.Table.__init__(self, size_req=(480, 160))
        self.view.register_modification_callback(self.save_to_file)
        self.connect("key_press_event", self._key_press_cb)
        self.connect('button_press_event', self._handle_button_press_cb)
        self.set_contents()
    def add_ap(self, path, alias=""):
        if self._extant_path(path):
            model_iter = self.model.get_iter_first()
            while model_iter:
                if self._same_paths(self.model.get_value_named(model_iter, 'Path'), path):
                    if alias:
                        self.model.set_value_named(model_iter, 'Alias', alias)
                    return
                model_iter = self.model.iter_next(model_iter)
            if not alias:
                alias = self._default_alias(path)
            data = self.model.Row(Path=self._abbrev_path(path), Alias=alias)
            self.model.append(data)
            self.save_to_file()
    def save_to_file(self, *args,**kwargs):
        ap_list = self.get_contents()
        self._write_list_to_file(ap_list)
    def get_selected_ap(self):
        data = self.get_selected_data_by_label(['Path', 'Alias'])
        if not data:
            return False
        return data[0]
    def _handle_button_press_cb(self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button == 2:
                self.seln.unselect_all()
                return True
        return False
    def _key_press_cb(self, widget, event):
        if event.keyval == _KEYVAL_ESCAPE:
            self.seln.unselect_all()
            return True
        return False

class PgndPathTable(AliasPathTable):
    SAVED_FILE_NAME = SAVED_PGND_FILE_NAME

class PathSelectDialog(dialogue.Dialog):
    def __init__(self, create_table, label, parent=None):
        dialogue.Dialog.__init__(self, title=_('gdarn: Select {0}').format(label), parent=parent,
                                 flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
                                 buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                          gtk.STOCK_OK, gtk.RESPONSE_OK)
                                )
        hbox = gtk.HBox()
        self.ap_table = create_table()
        hbox.pack_start(self.ap_table)
        self.vbox.pack_start(hbox)
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label("%s:" % label), expand=False)
        self._path = gutils.MutableComboBoxEntry()
        self._path.child.set_width_chars(32)
        self._path.child.connect("activate", self._path_cb)
        hbox.pack_start(self._path, expand=True, fill=True)
        self._browse_button = gtk.Button(label=_('_Browse'))
        self._browse_button.connect("clicked", self._browse_cb)
        hbox.pack_start(self._browse_button, expand=False, fill=False)
        self.vbox.pack_start(hbox, expand=False, fill=False)
        self.show_all()
        self.ap_table.seln.unselect_all()
        self.ap_table.seln.connect("changed", self._selection_cb)
    def _selection_cb(self, _selection=None):
        alpth = self.ap_table.get_selected_ap()
        if alpth:
            self._path.set_text(alpth[0])
    def _path_cb(self, entry=None):
        self.response(gtk.RESPONSE_OK)
    def _browse_cb(self, button=None):
        dirname = dialogue.ask_dir_name(_('gdarn: Browse for Directory'), existing=True, parent=self)
        if dirname:
            self._path.set_text(utils.path_rel_home(dirname))
    def get_path(self):
        return os.path.expanduser(self._path.get_text())

class PgndOpenDialog(PathSelectDialog):
    def __init__(self, parent=None):
        PathSelectDialog.__init__(self, create_table=PgndPathTable,
            label=_('Playground/Directory'), parent=parent)

# Manage external editors

EDITORS_THAT_NEED_A_TERMINAL = ["vi", "joe", "vim"]
DEFAULT_EDITOR = "gedit"
DEFAULT_TERMINAL = "gnome-terminal"
if os.name == 'nt' or os.name == 'dos':
    DEFAULT_EDITOR = "notepad"

for env in ['VISUAL', 'EDITOR']:
    try:
        ed = os.environ[env]
        if ed != "":
            DEFAULT_EDITOR = ed
            break
    except KeyError:
        pass

for env in ['COLORTERM', 'TERM']:
    try:
        term = os.environ[env]
        if term != "":
            DEFAULT_TERMINAL = term
            break
    except KeyError:
        pass

EDITOR_GLOB_FILE_NAME = os.sep.join([config_data.CONFIG_DIR_NAME, "editors"])

def _read_editor_defs(edeff=EDITOR_GLOB_FILE_NAME):
    editor_defs = []
    if os.path.isfile(edeff):
        for line in open(edeff, 'r').readlines():
            eqi = line.find('=')
            if eqi < 0:
                continue
            glob = line[:eqi].strip()
            edstr = line[eqi+1:].strip()
            editor_defs.append([glob, edstr])
    return editor_defs

def _write_editor_defs(edefs, edeff=EDITOR_GLOB_FILE_NAME):
    fobj = open(edeff, 'w')
    for edef in edefs:
        fobj.write('='.join(edef))
        fobj.write(os.linesep)
    fobj.close()

if not os.path.exists(EDITOR_GLOB_FILE_NAME):
    _write_editor_defs([('*', DEFAULT_EDITOR)])

def _assign_extern_editors(file_list, edeff=EDITOR_GLOB_FILE_NAME):
    ed_assignments = {}
    unassigned_files = []
    editor_defs = _read_editor_defs(edeff)
    for fobj in file_list:
        assigned = False
        for globs, edstr in editor_defs:
            for glob in globs.split(os.pathsep):
                if fnmatch.fnmatch(fobj, glob):
                    if edstr in ed_assignments:
                        ed_assignments[edstr].append(fobj)
                    else:
                        ed_assignments[edstr] = [fobj]
                    assigned = True
                    break
            if assigned:
                break
        if not assigned:
            unassigned_files.append(fobj)
    return ed_assignments, unassigned_files

def assign_extern_editors(file_list):
    ed_assignments, unassigned_files = _assign_extern_editors(file_list, EDITOR_GLOB_FILE_NAME)
    if unassigned_files:
        if DEFAULT_EDITOR in ed_assignments:
            ed_assignments[DEFAULT_EDITOR] += unassigned_files
        else:
            ed_assignments[DEFAULT_EDITOR] = unassigned_files
    return ed_assignments

class EditorAllocationTable(table.Table):
    class View(table.Table.View):
        class Model(table.Table.View.Model):
            Row = collections.namedtuple('Row', ['globs', 'editor'])
            types = Row(globs=gobject.TYPE_STRING, editor=gobject.TYPE_STRING)
        specification = tlview.ViewSpec(
            properties={
                'enable-grid-lines' : True,
                'reorderable' : True,
            },
            selection_mode=gtk.SELECTION_MULTIPLE,
            columns=[
                tlview.ColumnSpec(
                    title=_('File Pattern(s)'),
                    properties={'expand' : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=gtk.CellRendererText,
                                expand=False,
                                start=True
                            ),
                            properties={'editable' : True},
                            cell_data_function_spec=None,
                            attributes={'text' : Model.col_index('globs')}
                        ),
                    ],
                ),
                tlview.ColumnSpec(
                    title=_('Editor Command'),
                    properties={'expand' : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=gtk.CellRendererText,
                                expand=False,
                                start=True
                            ),
                            properties={'editable' : True},
                            cell_data_function_spec=None,
                            attributes={'text' : Model.col_index('editor')}
                        ),
                    ],
                ),
            ]
        )
    def __init__(self, edeff=EDITOR_GLOB_FILE_NAME):
        table.Table.__init__(self, (320, 160))
        self._edeff = edeff
        self.set_contents()
    def _fetch_contents(self):
        return _read_editor_defs(self._edeff)
    def apply_changes(self):
        _write_editor_defs(edefs=self.get_contents(), edeff=self._edeff)
        self.set_contents()

class EditorAllocationDialog(dialogue.Dialog):
    def __init__(self, edeff=EDITOR_GLOB_FILE_NAME, parent=None):
        dialogue.Dialog.__init__(self, title=_('gdarn: Editor Allocation'), parent=parent,
                                 flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                                 buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE,
                                          gtk.STOCK_OK, gtk.RESPONSE_OK)
                                )
        self._table = EditorAllocationTable(edeff=edeff)
        self._buttons = gutils.ActionHButtonBox(list(self._table.action_groups.values()))
        self.vbox.pack_start(self._table)
        self.vbox.pack_start(self._buttons, expand=False)
        self.connect("response", self._handle_response_cb)
        self.show_all()
        self._table.view.get_selection().unselect_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            self._table.apply_changes()
        self.destroy()

# Define some actions that are widget independent
def editor_allocation_acb(_arg):
    EditorAllocationDialog().show()

def change_pgnd_acb(_arg):
    open_dialog = PgndOpenDialog()
    if open_dialog.run() == gtk.RESPONSE_OK:
        newpg = open_dialog.get_path()
        if newpg:
            open_dialog.show_busy()
            result = ifce.chdir(newpg)
            open_dialog.unshow_busy()
            open_dialog.report_any_problems(result)
    open_dialog.destroy()

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("config_menu", None, _("_Configuration")),
        ("config_change_playground", gtk.STOCK_OPEN, _("_Open"), "",
         _("Change current playground"), change_pgnd_acb),
        ("config_allocate_editors", gtk.STOCK_PREFERENCES, _("_Editor Allocation"), "",
         _('Allocate editors to file types'), editor_allocation_acb),
    ])

class RepositoryMenu(gtk.MenuItem):
    def __init__(self, label=_("Playgrounds")):
        gtk.MenuItem.__init__(self, label)
        self.set_submenu(gtk.Menu())
        self.connect("enter_notify_event", self._enter_notify_even_cb)
    def _build_submenu(self):
        _menu = gtk.Menu()
        repos = PgndPathTable._fetch_contents()
        repos.sort()
        for repo in repos:
            label = "{0.Alias}:->({0.Path})".format(repo)
            _menu_item = gtk.MenuItem(label)
            _menu_item.connect("activate", change_repository_cb, os.path.expanduser(repo.Path))
            _menu_item.show()
            _menu.append(_menu_item)
        return _menu
    def _enter_notify_even_cb(self, widget, _event):
        widget.remove_submenu()
        widget.set_submenu(self._build_submenu())

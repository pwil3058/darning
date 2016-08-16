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

import os
import fnmatch
import collections

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

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

SAVED_PGND_FILE_NAME = os.sep.join([config_data.CONFIG_DIR_NAME, "playgrounds"])

_KEYVAL_ESCAPE = Gdk.keyval_from_name("Escape")

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
    def append_saved_path(cls, path, alias=None):
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
        fobj = open(cls.SAVED_FILE_NAME, "r")
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
        fobj = open(cls.SAVED_FILE_NAME, "w")
        for alpth in ap_list:
            fobj.write(os.pathsep.join(alpth))
            fobj.write(os.linesep)
        fobj.close()
    class View(table.Table.View):
        class Model(table.Table.View.Model):
            Row = collections.namedtuple("Row", ["Alias", "Path"])
            types = Row(Alias=GObject.TYPE_STRING, Path=GObject.TYPE_STRING)
        specification = tlview.ViewSpec(
            properties={
                "enable-grid-lines" : False,
                "reorderable" : False,
                "rules_hint" : False,
                "headers-visible" : True,
            },
            selection_mode=Gtk.SelectionMode.SINGLE,
            columns=[
                tlview.ColumnSpec(
                    title=_("Alias"),
                    properties={"expand": False, "resizable" : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=Gtk.CellRendererText,
                                expand=False,
                                start=True,
                                properties={"editable" : True},
                            ),
                            cell_data_function_spec=None,
                            attributes = {"text" : Model.col_index("Alias")}
                        ),
                    ],
                ),
                tlview.ColumnSpec(
                    title=_("Path"),
                    properties={"expand": False, "resizable" : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=Gtk.CellRendererText,
                                expand=False,
                                start=True,
                                properties={"editable" : False},
                            ),
                            cell_data_function_spec=None,
                            attributes = {"text" : Model.col_index("Path")}
                        ),
                    ],
                ),
            ]
        )
    def __init__(self):
        table.Table.__init__(self, size_req=(480, 160))
        self.view.register_modification_callback(self.save_to_file)
        self.connect("key_press_event", self._key_press_cb)
        self.connect("button_press_event", self._handle_button_press_cb)
        self.set_contents()
    def add_ap(self, path, alias=""):
        if self._extant_path(path):
            model_iter = self.model.get_iter_first()
            while model_iter:
                if self._same_paths(self.model.get_value_named(model_iter, "Path"), path):
                    if alias:
                        self.model.set_value_named(model_iter, "Alias", alias)
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
        data = self.get_selected_data_by_label(["Path", "Alias"])
        if not data:
            return False
        return data[0]
    def _handle_button_press_cb(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
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

class PathSelectDialog(dialogue.BusyDialog):
    PATH_TABLE = AliasPathTable
    def __init__(self, label, suggestion=None, parent=None):
        dialogue.BusyDialog.__init__(self, title=_("{0}: Select {1}").format(config_data.APP_NAME, label), parent=parent,
                                 flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                 buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
                                )
        hbox = Gtk.HBox()
        self.ap_table = self.PATH_TABLE()
        hbox.pack_start(self.ap_table, expand=True, fill=True, padding=0)
        self.vbox.pack_start(hbox, expand=True, fill=True, padding=0)
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label("%s:" % label), expand=False, fill=True, padding=0)
        self._path = gutils.new_mutable_combox_text_with_entry()
        self._path.get_child().set_width_chars(32)
        self._path.get_child().connect("activate", self._path_cb)
        hbox.pack_start(self._path, expand=True, fill=True, padding=0)
        self._browse_button = Gtk.Button(label=_("Browse"))
        self._browse_button.connect("clicked", self._browse_cb)
        hbox.pack_start(self._browse_button, expand=False, fill=False, padding=0)
        self.vbox.pack_start(hbox, expand=False, fill=False, padding=0)
        self.show_all()
        self.ap_table.seln.unselect_all()
        self.ap_table.seln.connect("changed", self._selection_cb)
    def _selection_cb(self, _selection=None):
        alpth = self.ap_table.get_selected_ap()
        if alpth:
            self._path.set_text(alpth[0])
    def _path_cb(self, entry=None):
        self.response(Gtk.ResponseType.OK)
    def _browse_cb(self, button=None):
        dirname = dialogue.select_directory(_("{0}: Browse for Directory").format(config_data.APP_NAME), existing=True, parent=self)
        if dirname:
            self._path.set_text(utils.path_rel_home(dirname))
    def get_path(self):
        return os.path.expanduser(self._path.get_text())

class PgndOpenDialog(PathSelectDialog):
    PATH_TABLE = PgndPathTable
    def __init__(self, suggestion=None, parent=None):
        PathSelectDialog.__init__(self, label=_("Playground/Directory"), suggestion=suggestion, parent=parent)

def ask_working_directory_path(parent=None):
    open_dialog = PgndOpenDialog(parent=parent)
    if open_dialog.run() != Gtk.ResponseType.OK:
        open_dialog.destroy()
        return None
    wd_path = open_dialog.get_path()
    open_dialog.destroy()
    return wd_path if wd_path else None

# Manage external editors

EDITORS_THAT_NEED_A_TERMINAL = ["vi", "joe", "vim"]
DEFAULT_EDITOR = "gedit"
DEFAULT_TERMINAL = "gnome-terminal"
if os.name == "nt" or os.name == "dos":
    DEFAULT_EDITOR = "notepad"

for env in ["VISUAL", "EDITOR"]:
    try:
        ed = os.environ[env]
        if ed != "":
            DEFAULT_EDITOR = ed
            break
    except KeyError:
        pass

DEFAULT_PERUSER = os.environ.get("GQUILT_PERUSER", None)

for env in ["COLORTERM", "TERM"]:
    try:
        term = os.environ[env]
        if term != "":
            DEFAULT_TERMINAL = term
            break
    except KeyError:
        pass

EDITOR_GLOB_FILE_NAME = os.sep.join([config_data.CONFIG_DIR_NAME, "editors"])
PERUSER_GLOB_FILE_NAME = os.sep.join([config_data.CONFIG_DIR_NAME, "perusers"])

def _read_editor_defs(edeff=EDITOR_GLOB_FILE_NAME):
    editor_defs = []
    if os.path.isfile(edeff):
        for line in open(edeff, "r").readlines():
            eqi = line.find("=")
            if eqi < 0:
                continue
            glob = line[:eqi].strip()
            edstr = line[eqi+1:].strip()
            editor_defs.append([glob, edstr])
    return editor_defs

def _write_editor_defs(edefs, edeff=EDITOR_GLOB_FILE_NAME):
    fobj = open(edeff, "w")
    for edef in edefs:
        fobj.write("=".join(edef))
        fobj.write(os.linesep)
    fobj.close()

if not os.path.exists(EDITOR_GLOB_FILE_NAME):
    _write_editor_defs([("*", DEFAULT_EDITOR)])

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

def assign_extern_perusers(file_list):
    peruser_assignments, unassigned_files = _assign_extern_editors(file_list, PERUSER_GLOB_FILE_NAME)
    extra_assigns = assign_extern_editors(unassigned_files)
    for key in extra_assigns:
        if key in peruser_assignments:
            peruser_assignments[key] += extra_assigns[key]
        else:
            peruser_assignments[key] = extra_assigns[key]
    return peruser_assignments

class EditorAllocationTable(table.Table):
    class View(table.Table.View):
        class Model(table.Table.View.Model):
            Row = collections.namedtuple("Row", ["globs", "editor"])
            types = Row(globs=GObject.TYPE_STRING, editor=GObject.TYPE_STRING)
        specification = tlview.ViewSpec(
            properties={
                'enable-grid-lines' : True,
                'reorderable' : True,
            },
            selection_mode=Gtk.SelectionMode.MULTIPLE,
            columns=[
                tlview.ColumnSpec(
                    title=_("File Pattern(s)"),
                    properties={"expand" : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=Gtk.CellRendererText,
                                expand=False,
                                start=True,
                                properties={"editable" : True},
                            ),
                            cell_data_function_spec=None,
                            attributes={"text" : Model.col_index("globs")}
                        ),
                    ],
                ),
                tlview.ColumnSpec(
                    title=_("Editor Command"),
                    properties={"expand" : True},
                    cells=[
                        tlview.CellSpec(
                            cell_renderer_spec=tlview.CellRendererSpec(
                                cell_renderer=Gtk.CellRendererText,
                                expand=False,
                                start=True,
                                properties={"editable" : True},
                            ),
                            cell_data_function_spec=None,
                            attributes={"text" : Model.col_index("editor")}
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

class EditorAllocationDialog(dialogue.BusyDialog):
    EDEFF = EDITOR_GLOB_FILE_NAME
    TITLE = _("{0}: Editor Allocation".format(config_data.APP_NAME))
    def __init__(self, parent=None):
        dialogue.BusyDialog.__init__(self, title=self.TITLE, parent=parent,
                                 flags=Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                 buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,
                                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
                                )
        self._table = EditorAllocationTable(edeff=self.EDEFF)
        self._buttons = gutils.ActionHButtonBox(list(self._table.action_groups.values()))
        self.vbox.pack_start(self._table, expand=True, fill=True, padding=0)
        self.vbox.pack_start(self._buttons, expand=False, fill=True, padding=0)
        self.connect("response", self._handle_response_cb)
        self.show_all()
        self._table.view.get_selection().unselect_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self._table.apply_changes()
        self.destroy()

class PeruserAllocationDialog(EditorAllocationDialog):
    EDEFF = PERUSER_GLOB_FILE_NAME
    TITLE = _("{0}: Peruser Allocation".format(config_data.APP_NAME))

def change_pgnd_cb(_widget, repo):
    dialogue.show_busy()
    result = ifce.chdir(repo)
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

class PlaygroundsMenu(Gtk.MenuItem):
    def __init__(self, label=_("Playgrounds")):
        Gtk.MenuItem.__init__(self, label)
        self.set_submenu(Gtk.Menu())
        self.connect("enter_notify_event", self._enter_notify_even_cb)
    def _build_submenu(self):
        _menu = Gtk.Menu()
        repos = PgndPathTable._fetch_contents()
        repos.sort()
        for repo in repos:
            label = "{0.Alias}:->({0.Path})".format(repo)
            _menu_item = Gtk.MenuItem(label)
            _menu_item.connect("activate", change_pgnd_cb, os.path.expanduser(repo.Path))
            _menu_item.show()
            _menu.append(_menu_item)
        return _menu
    def _enter_notify_even_cb(self, widget, _event):
        widget.set_submenu(self._build_submenu())

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("config_menu", None, _("_Configuration")),
        ("config_allocate_editors", Gtk.STOCK_PREFERENCES, _("_Editor Allocation"), "",
         _("Allocate editors to file types"),
         lambda _action=None: EditorAllocationDialog(parent=dialogue.main_window).show()
        ),
        ("config_allocate_perusers", Gtk.STOCK_PREFERENCES, _("_Peruser Allocation"), "",
         _("Allocate perusers to file types"),
         lambda _action=None: PeruserAllocationDialog(parent=dialogue.main_window).show()
        ),
    ]
)

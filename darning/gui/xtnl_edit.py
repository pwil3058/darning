### Copyright (C) 2007-2016 Peter Williams <pwil3058@gmail.com>
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

# Manage external editors

import collections
import fnmatch
import os
import shlex

from gi.repository import GObject
from gi.repository import Gtk

from .. import config_data
from .. import runext

from . import actions
from . import dialogue
from . import gutils
from . import table
from . import tlview

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

DEFAULT_PERUSER = DEFAULT_EDITOR

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

class EditorAllocationModel(tlview.NamedListStore):
    ROW = collections.namedtuple("ROW", ["globs", "editor"])
    TYPES = ROW(globs=GObject.TYPE_STRING, editor=GObject.TYPE_STRING)

class EditorAllocationView(table.EditableEntriesView):
    EDEFF = EDITOR_GLOB_FILE_NAME
    MODEL = EditorAllocationModel
    SPECIFICATION = tlview.ViewSpec(
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
                        attributes={"text" : MODEL.col_index("globs")}
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
                        attributes={"text" : MODEL.col_index("editor")}
                    ),
                ],
            ),
        ]
    )
    def __init__(self, **kwargs):
        table.EditableEntriesView.__init__(self, **kwargs)
        self.set_contents()
    def _fetch_contents(self):
        return _read_editor_defs(self.EDEFF)
    def apply_changes(self):
        _write_editor_defs(edefs=self.get_contents(), edeff=self.EDEFF)
        self.set_contents()

class EditorAllocationTable(table.EditedEntriesTable):
    VIEW = EditorAllocationView

class EditorAllocationDialog(dialogue.BusyDialog):
    TITLE = _("{0}: Editor Allocation".format(config_data.APP_NAME))
    def __init__(self, parent=None):
        dialogue.BusyDialog.__init__(self, title=self.TITLE, parent=parent,
                                 flags=Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                 buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,
                                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
                                )
        self._table = EditorAllocationTable()
        self.vbox.pack_start(self._table, expand=True, fill=True, padding=0)
        self.connect("response", self._handle_response_cb)
        self.show_all()
        self._table.view.get_selection().unselect_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self._table.view.apply_changes()
        self.destroy()

def _edit_files_extern(file_list, ed_assigns):
    def _launch_editor(filelist, edstr=DEFAULT_EDITOR):
        cmd = shlex.split(edstr) + filelist
        if cmd[0] in EDITORS_THAT_NEED_A_TERMINAL:
            if DEFAULT_TERMINAL == "gnome-terminal":
                flag = '-x'
            else:
                flag = '-e'
            cmd = [DEFAULT_TERMINAL, flag] + cmd
        return runext.run_cmd_in_bgnd(cmd)
    for edstr in list(ed_assigns.keys()):
        _launch_editor(ed_assigns[edstr], edstr)

def edit_files_extern(file_list):
    return _edit_files_extern(file_list, assign_extern_editors(file_list))

class PeruserAllocationView(EditorAllocationView):
    EDEFF = PERUSER_GLOB_FILE_NAME

class PeruserAllocationTable(EditorAllocationTable):
    VIEW = PeruserAllocationView

class PeruserAllocationDialog(EditorAllocationDialog):
    TABLE = PeruserAllocationTable
    TITLE = _("{0}: Peruser Allocation".format(config_data.APP_NAME))

def peruse_files_extern(file_list):
    return _edit_files_extern(file_list, assign_extern_perusers(file_list))

# Define some actions that are widget independent
actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("allocate_xtnl_editors", Gtk.STOCK_PREFERENCES, _("_Editor Allocation"), "",
         _('Allocate editors to file types'),
         lambda _action=None:  EditorAllocationDialog(parent=dialogue.main_window).show()
        ),
        ("allocate_xtnl_perusers", Gtk.STOCK_PREFERENCES, _("_Peruser Allocation"), "",
         _("Allocate perusers to file types"),
         lambda _action=None: PeruserAllocationDialog(parent=dialogue.main_window).show()
        ),
    ])

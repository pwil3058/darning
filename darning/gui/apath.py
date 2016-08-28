### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>
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

from . import dialogue
from . import gutils
from . import tlview
from . import table

class AliasPathModel(tlview.NamedListStore):
    ROW = collections.namedtuple("ROW", ["Alias", "Path"])
    TYPES = ROW(Alias=GObject.TYPE_STRING, Path=GObject.TYPE_STRING)

class AliasPathView(table.EditableEntriesView):
    SAVED_FILE_NAME = None
    MODEL = AliasPathModel
    SPECIFICATION = tlview.ViewSpec(
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
                        attributes = {"text" : MODEL.col_index("Alias")}
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
                        attributes = {"text" : MODEL.col_index("Path")}
                    ),
                ],
            ),
        ]
    )
    def __init__(self):
        table.EditableEntriesView.__init__(self, size_req=(480, 160))
        self.register_modification_callback(self.apply_changes)
        self.set_contents()
    def apply_changes(self, *args,**kwargs):
        ap_list = self.get_contents()
        self._write_list_to_file(ap_list)
    def get_selected_ap(self):
        data = self.get_selected_data_by_label(["Path", "Alias"])
        if not data:
            return False
        return data[0]
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
                content.append(cls.MODEL.ROW(Path=abbr_path, Alias=alias))
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
            data = cls.MODEL.ROW(*line.strip().split(os.pathsep, 1))
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
    @classmethod
    def generate_alias_path_menu(cls, label, item_activation_cb):
        return AliasPathMenu(label, cls._fetch_contents, item_activation_cb)

class AliasPathMenu(Gtk.MenuItem):
    def __init__(self, label, fetch_contents_func, item_activation_action):
        self._fetch_contents = fetch_contents_func
        self._item_activation_action = item_activation_action
        Gtk.MenuItem.__init__(self, label)
        self.set_submenu(Gtk.Menu())
        self.connect("enter_notify_event", self._enter_notify_even_cb)
    def _build_submenu(self):
        _menu = Gtk.Menu()
        newtgnds = self._fetch_contents()
        newtgnds.sort()
        for newtgnd in newtgnds:
            label = _("{0.Alias}:->({0.Path})").format(newtgnd)
            _menu_item = Gtk.MenuItem(label)
            _menu_item.connect("activate", self._item_activation_cb, os.path.expanduser(newtgnd.Path))
            _menu_item.show()
            _menu.append(_menu_item)
        return _menu
    def _enter_notify_even_cb(self, widget, _event):
        widget.set_submenu(self._build_submenu())
    def _item_activation_cb(self, _widget, newtgnd):
        dialogue.show_busy()
        result = self._item_activation_action(newtgnd)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)

class AliasPathTable(table.EditedEntriesTable):
    BUTTONS = []
    VIEW = AliasPathView

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
        if suggestion:
            self._path.set_text(suggestion)
        hbox.pack_start(self._path, expand=True, fill=True, padding=0)
        self._browse_button = Gtk.Button(label=_("Browse"))
        self._browse_button.connect("clicked", self._browse_cb)
        hbox.pack_start(self._browse_button, expand=False, fill=False, padding=0)
        self.vbox.pack_start(hbox, expand=False, fill=False, padding=0)
        self.show_all()
        self.ap_table.seln.unselect_all()
        self.ap_table.seln.connect("changed", self._selection_cb)
    def _selection_cb(self, _selection=None):
        alpth = self.ap_table.view.get_selected_ap()
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

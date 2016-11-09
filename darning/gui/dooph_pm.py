### Copyright (C) 2015 Peter Williams <pwil3058@gmail.com>
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
import collections

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from ..wsm.bab import utils

from ..wsm.bab import CmdResult

from ..wsm.gtx import dialogue
from ..wsm.gtx import actions
from ..wsm.gtx import icons
from ..wsm.gtx import tlview
from ..wsm.gtx import table
from ..wsm.gtx import gutils
from ..wsm.gtx import recollect
from ..wsm.gtx import textview
from ..wsm.gtx import text_edit

from ..wsm import wsm_icons

from .. import APP_NAME

from ..wsm.pm_gui import pm_gui_ifce
from ..wsm.pm_gui import pm_actions
from ..wsm.pm_gui.pm_do_opn_patches import NewSeriesDescrDialog

from ..wsm.scm_gui import scm_actions

def pm_do_fold_external_patch():
    from ..wsm.patch_diff import patchlib
    patch_file_path = dialogue.main_window.ask_file_path(_("Select patch file to be folded"))
    if patch_file_path is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file_path)
    except patchlib.ParseError as edata:
        result = CmdResult.error(stderr="{0}: {1}: {2}\n".format(patch_file_path, edata.lineno, edata.message))
        dialogue.main_window.report_any_problems(result)
        return
    force = False
    absorb = False
    refresh_tried = False
    dlg = FoldPatchDialog(epatch, parent=dialogue.main_window)
    resp = dlg.run()
    while resp != Gtk.ResponseType.CANCEL:
        epatch.set_strip_level(dlg.get_strip_level())
        with dlg.showing_busy():
            result = pm_gui_ifce.PM.do_fold_epatch(epatch, absorb=absorb, force=force)
        if refresh_tried:
            result = result - result.Suggest.REFRESH
        if not (absorb or force) and result.suggests(result.Suggest.FORCE_ABSORB_OR_REFRESH):
            resp = dialogue.main_window.ask_force_refresh_absorb_or_cancel(result)
            if resp == Gtk.ResponseType.CANCEL:
                break
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                with dialogue.main_window.showing_busy():
                    top_patch_file_list = pm_gui_ifce.PM.get_filepaths_in_top_patch()
                    file_paths = [file_path for file_path in epatch.get_file_paths(epatch.num_strip_levels) if file_path not in top_patch_file_list]
                    result = pm_gui_ifce.PM.do_refresh_overlapped_files(file_paths)
                dialogue.main_window.report_any_problems(result)
            continue
        dialogue.main_window.report_any_problems(result)
        break
    dlg.destroy()

def pm_do_import_external_patch():
    suggestion = recollect.get("import", "last_directory")
    from ..wsm.patch_diff import patchlib
    patch_file_path = dialogue.main_window.ask_file_path(_("Select patch file to be imported"), suggestion=suggestion)
    if patch_file_path is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file_path)
    except patchlib.ParseError as edata:
        result = CmdResult.error(stderr="{0}: {1}: {2}\n".format(patch_file_path, edata.lineno, edata.message))
        dialogue.main_window.report_any_problems(result)
        return
    overwrite = False
    dlg = ImportPatchDialog(epatch, parent=dialogue.main_window)
    resp = dlg.run()
    while resp != Gtk.ResponseType.CANCEL:
        epatch.set_strip_level(dlg.get_strip_level())
        with dlg.showing_busy():
            result = pm_gui_ifce.PM.do_import_patch(epatch, dlg.get_as_name(), overwrite=overwrite)
        if not overwrite and result.suggests(result.Suggest.OVERWRITE_OR_RENAME):
            resp = dialogue.main_window.ask_rename_overwrite_or_cancel(result)
            if resp == Gtk.ResponseType.CANCEL:
                break
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            else:
                resp = dlg.run()
            continue
        dialogue.main_window.report_any_problems(result)
        if result.suggests_rename:
            resp = dlg.run()
        else:
            break
    dlg.destroy()

actions.CLASS_INDEP_AGS[pm_actions.AC_POP_POSSIBLE | pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_fold_external_patch", wsm_icons.STOCK_FOLD_PATCH, _("Fold"), None,
         _("Fold an external patch into the top applied patch"),
         lambda _action=None: pm_do_fold_external_patch()
        ),
    ]
)

actions.CLASS_INDEP_AGS[pm_actions.AC_IN_PM_PGND].add_actions(
    [
        ("pm_import_patch", wsm_icons.STOCK_IMPORT_PATCH, _("Import"), None,
         _("Import an external patch behind the top applied patch"),
         lambda _action=None: pm_do_import_external_patch()
        ),
    ]
)

class ImportPatchDialog(dialogue.Dialog):
    def __init__(self, epatch, parent=None):
        flags = ~Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        title = _("Import Patch: {0} : {1} -- {2}").format(epatch.source_name, utils.path_rel_home(os.getcwd()), APP_NAME)
        dialogue.Dialog.__init__(self, title, parent, flags, None)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.epatch = epatch
        #
        patch_file_name = os.path.basename(epatch.source_name)
        self.namebox = Gtk.HBox()
        self.namebox.pack_start(Gtk.Label(_("As Patch:")), expand=False, fill=True, padding=0)
        self.as_name = gutils.new_mutable_combox_text_with_entry()
        self.as_name.get_child().set_width_chars(32)
        self.as_name.set_text(patch_file_name)
        self.namebox.pack_start(self.as_name, expand=True, fill=True, padding=0)
        vbox = self.get_content_area()
        vbox.pack_start(self.namebox, expand=False, fill=False, padding=0)
        #
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label(_("Files: Strip Level:")), expand=False, fill=True, padding=0)
        est_strip_level = self.epatch.estimate_strip_level()
        self.strip_level_buttons = [Gtk.RadioButton(group=None, label="0")]
        self.strip_level_buttons.append(Gtk.RadioButton(group=self.strip_level_buttons[0], label="1"))
        for strip_level_button in self.strip_level_buttons:
            strip_level_button.connect("toggled", self._strip_level_toggle_cb)
            hbox.pack_start(strip_level_button, expand=False, fill=False, padding=0)
            strip_level_button.set_active(False)
        vbox.pack_start(hbox, expand=False, fill=False, padding=0)
        #
        self.file_list_widget = textview.Widget()
        self.strip_level_buttons[1 if est_strip_level is None else est_strip_level].set_active(True)
        self.update_file_list()
        vbox.pack_start(self.file_list_widget, expand=True, fill=True, padding=0)
        self.show_all()
        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_focus_child(self.as_name)
    def get_strip_level(self):
        for strip_level in [0, 1]:
            if self.strip_level_buttons[strip_level].get_active():
                return strip_level
        return None
    def get_as_name(self):
        return self.as_name.get_text()
    def update_file_list(self):
        from ..wsm.patch_diff.patchlib import TooMayStripLevels
        strip_level = self.get_strip_level()
        try:
            filepaths = self.epatch.get_file_paths(strip_level)
            self.file_list_widget.set_contents("\n".join(filepaths))
        except TooMayStripLevels:
            if strip_level == 0:
                return
            self.strip_level_buttons[0].set_active(True)
    def _strip_level_toggle_cb(self, _widget, *args,**kwargs):
        self.update_file_list()

class FoldPatchDialog(ImportPatchDialog):
    def __init__(self, epatch, parent=None):
        ImportPatchDialog.__init__(self, epatch, parent)
        self.set_title( _("Fold Patch: {0} : {1} -- {2}").format(epatch.source_name, utils.path_rel_home(os.getcwd()), APP_NAME))
        self.namebox.hide()

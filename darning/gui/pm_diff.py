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

import re
import os
import hashlib

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

from ..wsm.bab import CmdResult, CmdFailure
from ..wsm.bab import runext
from ..wsm.bab import enotify
from ..wsm.bab import options

from ..wsm.patch_diff import patchlib

from ..wsm.patch_diff_gui import diff

from ..wsm.gtx import dialogue
from ..wsm.gtx import gutils

from ..wsm import pm

from .. import utils

from . import ifce
from . import icons

class TopPatchDiffPlusesWidget(diff.DiffPlusesWidget, enotify.Listener):
    def __init__(self, file_paths=None, num_strip_levels=1):
        self._file_paths = file_paths
        diff.DiffPlusesWidget.__init__(self)
        enotify.Listener.__init__(self)
        self.add_notification_cb(pm.E_PATCH_STACK_CHANGES|pm.E_FILE_CHANGES|enotify.E_CHANGE_WD, self._refresh_ecb)
    def _refresh_ecb(self, **kwargs):
        self.update()
    def _get_diff_pluses(self):
        return ifce.PM.get_top_patch_diff_pluses(self._file_paths)
    @property
    def window_title(self):
        return _("Top Patch: diff: {0}").format(utils.cwd_rel_home())

class CombinedPatchDiffPlusesWidget(TopPatchDiffPlusesWidget):
    def _get_diff_pluses(self):
        return ifce.PM.get_combined_patch_diff_pluses(self._file_paths)
    @property
    def window_title(self):
        return _("Combined Patches diff: {0}").format(utils.cwd_rel_home())

class NamedPatchDiffPlusesWidget(diff.DiffPlusesWidget):
    A_NAME_LIST = ["diff_save", "diff_save_as"]
    def __init__(self, patch_name=None, file_paths=None, num_strip_levels=1):
        self._patch_name = patch_name
        self._file_paths = file_paths
        diff.DiffPlusesWidget.__init__(self)
    def _get_diff_pluses(self):
        return ifce.PM.get_named_patch_diff_pluses(self._patch_name, self._file_paths)
    @property
    def window_title(self):
        return _("Patch \"{0}\" diff: {1}").format(self._patch_name, utils.cwd_rel_home())

class _DiffDialog(dialogue.ListenerDialog):
    DIFFS_WIDGET = None
    def __init__(self, parent=None, **kwargs):
        flags = Gtk.DialogFlags.DESTROY_WITH_PARENT
        dialogue.ListenerDialog.__init__(self, None, parent if parent else dialogue.main_window, flags, ())
        dtw = self.DIFFS_WIDGET(**kwargs)
        self.set_title(dtw.window_title)
        self.vbox.pack_start(dtw, expand=True, fill=True, padding=0)
        tws_display = dtw.tws_display
        self.action_area.pack_end(tws_display, expand=False, fill=False, padding=0)
        for button in dtw.diff_buttons.list:
            self.action_area.pack_start(button, expand=True, fill=True, padding=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.connect("response", self._close_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()

class TopPatchDiffPlusesDialog(_DiffDialog):
    DIFFS_WIDGET = TopPatchDiffPlusesWidget

class CombinedPatchDiffPlusesDialog(_DiffDialog):
    DIFFS_WIDGET = CombinedPatchDiffPlusesWidget

class NamedPatchDiffPlusesDialog(_DiffDialog):
    DIFFS_WIDGET = NamedPatchDiffPlusesWidget

class TopPatchDiffTextWidget(diff.DiffTextsWidget, enotify.Listener):
    def __init__(self, file_paths=None, num_strip_levels=1):
        self._file_paths = file_paths
        diff.DiffTextsWidget.__init__(self)
        enotify.Listener.__init__(self)
        self.add_notification_cb(pm.E_PATCH_STACK_CHANGES|pm.E_FILE_CHANGES|enotify.E_CHANGE_WD, self._refresh_ecb)
    def _refresh_ecb(self, **kwargs):
        self.update()
    def _get_diff_text(self):
        return ifce.PM.get_top_patch_diff_text(self._file_paths)
    @property
    def window_title(self):
        return _("Top Patch: diff: {0}").format(utils.cwd_rel_home())

class TopPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = TopPatchDiffTextWidget

class CombinedPatchDiffTextWidget(TopPatchDiffTextWidget):
    def _get_diff_text(self):
        return ifce.PM.get_combined_patch_diff_text(self._file_paths)
    @property
    def window_title(self):
        return _("Combined Patches diff: {0}").format(utils.cwd_rel_home())

class CombinedPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = CombinedPatchDiffTextWidget

class NamedPatchDiffTextWidget(diff.DiffTextsWidget):
    A_NAME_LIST = ["diff_save", "diff_save_as"]
    def __init__(self, patch_name=None, file_paths=None, num_strip_levels=1):
        self._patch_name = patch_name
        self._file_paths = file_paths
        diff.DiffTextsWidget.__init__(self)
    def _get_diff_text(self):
        return ifce.PM.get_named_patch_diff_text(self._patch_name, self._file_paths)
    @property
    def window_title(self):
        return _("Patch \"{0}\" diff: {1}").format(self._patch_name, utils.cwd_rel_home())

class NamedPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = NamedPatchDiffTextWidget

#GLOBAL ACTIONS
from ..wsm.gtx import actions
from . import ws_actions

actions.CLASS_INDEP_AGS[ws_actions.AC_IN_PM_PGND + ws_actions.AC_PMIC].add_actions(
    [
        ("pm_top_patch_diff_text", icons.STOCK_DIFF, _("_Diff"), None,
         _("Display the diff for all files in the top patch"),
         lambda _action=None: TopPatchDiffTextDialog(parent=dialogue.main_window).show()
        ),
        ("pm_top_patch_diff_pluses", icons.STOCK_DIFF, _("_Diff"), None,
         _("Display the diff for all files in the top patch"),
         lambda _action=None: TopPatchDiffPlusesDialog(parent=dialogue.main_window).show()
        ),
        ("pm_top_patch_extdiff", icons.STOCK_DIFF, _('E_xtdiff'), None,
         _('Launch extdiff for all files in patch'),
         lambda _action=None: ifce.PM.launch_extdiff_for_top_patch()
        ),
        ("pm_combined_patch_diff_text", icons.STOCK_DIFF, _("Combined Diff"), "",
         _("View the combined diff for all files in all currently applied patches"),
         lambda _action=None: CombinedPatchDiffTextDialog(parent=dialogue.main_window).show()
        ),
        ("pm_combined_patch_diff_pluses", icons.STOCK_DIFF, _("Combined Diff"), "",
         _("View the combined diff for all files in all currently applied patches"),
         lambda _action=None: CombinedPatchDiffPlusesDialog(parent=dialogue.main_window).show()
        ),
    ]
)

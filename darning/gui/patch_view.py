### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
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

'''Widget to display a complete patch'''

import os
import hashlib

import gtk

from .. import patchlib
from .. import utils
from .. import pm_ifce

from . import textview
from . import dialogue
from . import icons
from . import diff
from . import ws_event
from . import gutils
from . import ifce
from . import gutils

class Widget(gtk.VBox):
    from ..pm_ifce import PatchState
    status_icons = {
        PatchState.NOT_APPLIED : gtk.STOCK_REMOVE,
        PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
        PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
        PatchState.APPLIED_UNREFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
    }
    status_tooltips = {
        PatchState.NOT_APPLIED : _('This patch is not applied.'),
        PatchState.APPLIED_REFRESHED : _('This patch is applied and refresh is up to date.'),
        PatchState.APPLIED_NEEDS_REFRESH : _('This patch is applied but refresh is NOT up to date.'),
        PatchState.APPLIED_UNREFRESHABLE : _('This patch is applied but has problems (e.g. unresolved merge errosr) that prevent it being refreshed.'),
    }
    class TWSDisplay(diff.TextWidget.TwsLineCountDisplay):
        LABEL = _('File(s) that add TWS: ')
    def __init__(self, patch_name):
        gtk.VBox.__init__(self)
        self.patch_name = patch_name
        self.epatch = self.get_epatch()
        #
        self.status_icon = gtk.image_new_from_stock(self.status_icons[self.epatch.state], gtk.ICON_SIZE_BUTTON)
        self.status_box = gtk.HBox()
        self.status_box.add(self.status_icon)
        self.status_box.show_all()
        gutils.set_widget_tooltip_text(self.status_box, self.status_tooltips[self.epatch.state])
        self.tws_display = self.TWSDisplay()
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        hbox = gtk.HBox()
        hbox.pack_start(self.status_box, expand=False)
        hbox.pack_start(gtk.Label(self.patch_name), expand=False)
        hbox.pack_end(self.tws_display, expand=False)
        self.pack_start(hbox, expand=False)
        #
        pane = gtk.VPaned()
        self.pack_start(pane, expand=True, fill=True)
        #
        self.header_nbook = gtk.Notebook()
        self.header_nbook.popup_enable()
        pane.add1(self._framed(_('Header'), self.header_nbook))
        #
        self.description = textview.Widget()
        self.description.set_contents(self.epatch.get_description())
        self.description.view.set_editable(False)
        self.description.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.description, gtk.Label(_('Description')))
        #
        self.diffstats = textview.Widget()
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self.diffstats.view.set_editable(False)
        self.diffstats.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.diffstats, gtk.Label(_('Diff Statistics')))
        #
        self.comments = textview.Widget(aspect_ratio=0.1)
        self.comments.set_contents(self.epatch.get_comments())
        self.comments.view.set_editable(False)
        self.comments.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.comments, gtk.Label(_('Comments')))
        #
        self.diffs_nbook = diff.DiffPlusNotebook(self.epatch.diff_pluses)
        pane.add2(self._framed(_('File Diffs'), self.diffs_nbook))
        #
        self.show_all()
    def get_patch_text(self):
        # handle the case where our patch file gets deleted
        try:
            return ifce.PM.get_patch_text(self.patch_name)
        except IOError as edata:
            if edata.errno == 2:
                return str(self.epatch)
            else:
                raise
    def get_epatch(self):
        epatch = ifce.PM.get_textpatch(self.patch_name)
        self.text_digest = epatch.get_hash_digest()
        return epatch
    @property
    def is_applied(self):
        return ifce.PM.is_patch_applied(self.patch_name)
    @staticmethod
    def _framed(label, widget):
        frame = gtk.Frame(label)
        frame.add(widget)
        return frame
    def update(self):
        epatch = ifce.PM.get_textpatch(self.patch_name)
        digest = epatch.get_hash_digest()
        if digest == self.text_digest:
            return
        self.text_digest = digest
        self.epatch = epatch
        self.status_box.remove(self.status_icon)
        self.status_icon = gtk.image_new_from_stock(self.status_icons[self.epatch.state], gtk.ICON_SIZE_BUTTON)
        self.status_box.add(self.status_icon)
        self.status_box.show_all()
        gutils.set_widget_tooltip_text(self.status_box, self.status_tooltips[self.epatch.state])
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        self.comments.set_contents(self.epatch.get_comments())
        self.description.set_contents(self.epatch.get_description())
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self.diffs_nbook.set_diff_pluses(self.epatch.diff_pluses)

class Dialogue(dialogue.AmodalDialog):
    AUTO_UPDATE_TD = gutils.TimeOutController.ToggleData("auto_update_toggle", _('Auto _Update'), _('Turn data auto update on/off'), gtk.STOCK_REFRESH)
    def __init__(self, patch_name):
        from ..config_data import APP_NAME
        title = _(APP_NAME + ": Patch \"{0}\" : {1}").format(patch_name, utils.path_rel_home(os.getcwd()))
        dialogue.AmodalDialog.__init__(self, title=title, parent=dialogue.main_window, flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        self.widget = Widget(patch_name)
        self.vbox.pack_start(self.widget, expand=True, fill=True)
        self.refresh_action = gtk.Action('patch_view_refresh', _('_Refresh'), _('Refresh this patch in database.'), icons.STOCK_REFRESH_PATCH)
        self.refresh_action.connect('activate', self._refresh_acb)
        self.refresh_action.set_sensitive(ifce.PM.is_top_patch(self.widget.patch_name))
        refresh_button = gutils.ActionButton(self.refresh_action)
        self.auc = gutils.TimeOutController(toggle_data=self.AUTO_UPDATE_TD, function=self._update_display_cb, is_on=False, interval=10000)
        self.action_area.pack_start(gutils.ActionCheckButton(self.auc.toggle_action))
        self.action_area.pack_start(refresh_button)
        self._save_file = utils.convert_patchname_to_filename(patch_name)
        self.save_action = gtk.Action('patch_view_save', _('_Export'), _('Export current content to text file.'), gtk.STOCK_SAVE_AS)
        self.save_action.connect('activate', self._save_as_acb)
        save_button = gutils.ActionButton(self.save_action)
        self.action_area.pack_start(save_button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._close_cb)
        self.add_notification_cb(pm_ifce.E_PATCH_LIST_CHANGES|pm_ifce.E_FILE_CHANGES, self._update_display_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        self.auc.toggle_action.set_active(False)
        dialog.destroy()
    def _update_display_cb(self, **kwargs):
        self.show_busy()
        self.widget.update()
        self.refresh_action.set_sensitive(ifce.PM.is_top_patch(self.widget.patch_name))
        self.unshow_busy()
    def _refresh_acb(self, _action):
        self.show_busy()
        result = ifce.PM.do_refresh_patch(self.widget.patch_name)
        self.unshow_busy()
        dialogue.report_any_problems(result)
    def _save_as_acb(self, _action):
        from . import recollect
        suggestion = os.path.basename(utils.convert_patchname_to_filename(self.widget.patch_name))
        export_filepath = os.path.join(recollect.get("export", "last_directory"), suggestion)
        while True:
            export_filepath = dialogue.ask_file_name(_("Export as ..."), suggestion=export_filepath, existing=False)
            if export_filepath is None:
                return
            if os.path.exists(export_filepath):
                from ..cmd_result import CmdResult
                problem = CmdResult.error(stderr=_("A file of that name already exists!!")) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
                response = dialogue.ask_rename_overwrite_or_cancel(problem)
                if response == gtk.RESPONSE_CANCEL:
                    return
                elif response == dialogue.Response.RENAME:
                    continue
                else:
                    assert response == dialogue.Response.OVERWRITE
                    break
            else:
                break
        if export_filepath.startswith(os.pardir):
            export_filepath = utils.path_rel_home(export_filepath)
        if export_filepath.startswith(os.pardir):
            export_filepath = os.path.abspath(export_filepath)
        dialogue.report_any_problems(utils.set_file_contents(export_filepath, str(self.widget.epatch)))

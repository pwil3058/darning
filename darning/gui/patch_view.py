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
import gtk

from .. import patch_db
from .. import utils

from . import textview
from . import dialogue
from . import icons
from . import diff
from . import ws_event
from . import gutils
from . import ifce

class DiffDisplay(diff.TextWidget):
    def __init__(self, diffplus):
        self.diffplus = diffplus
        diff.TextWidget.__init__(self)
        self.tws_nav_buttonbox.pack_start(self.tws_display, expand=False)
        self.tws_nav_buttonbox.reorder_child(self.tws_display, 0)
    def _get_diff_text(self):
        return str(self.diffplus)
    def update(self, diffplus):
        self.diffplus = diffplus
        self.set_contents()

class Widget(gtk.VBox):
    status_icons = {
        patch_db.PatchState.UNAPPLIED : gtk.STOCK_REMOVE,
        patch_db.PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
        patch_db.PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
        patch_db.PatchState.APPLIED_UNREFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
    }
    status_tooltips = {
        patch_db.PatchState.UNAPPLIED : _('This patch is not applied.'),
        patch_db.PatchState.APPLIED_REFRESHED : _('This patch is applied and refresh is up to date.'),
        patch_db.PatchState.APPLIED_NEEDS_REFRESH : _('This patch is applied but refresh is NOT up to date.'),
        patch_db.PatchState.APPLIED_UNREFRESHABLE : _('This patch is applied but has problems (e.g. unresolved merge errosr) that prevent it being refreshed.'),
    }
    class TWSDisplay(diff.TextWidget.TwsLineCountDisplay):
        LABEL = _('File(s) that add TWS: ')
    def __init__(self, patchname):
        gtk.VBox.__init__(self)
        self.patchname = patchname
        self.epatch = patch_db.get_textpatch(self.patchname)
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
        hbox.pack_start(gtk.Label(self.patchname), expand=False)
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
        self.comments = textview.Widget(aspect_ratio=0.1)
        self.comments.set_contents(self.epatch.get_comments())
        self.comments.view.set_editable(False)
        self.comments.view.set_cursor_visible(False)
        self.header_nbook.append_page(self.comments, gtk.Label(_('Comments')))
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
        self.diffs_nbook = gtk.Notebook()
        self.diffs_nbook.set_scrollable(True)
        self.diffs_nbook.popup_enable()
        pane.add2(self._framed(_('File Diffs'), self.diffs_nbook))
        self.diff_displays = {}
        self._populate_pages()
        self.update()
        #
        self.show_all()
    @staticmethod
    def _make_file_label(filepath, validity):
        hbox = gtk.HBox()
        if validity == patch_db.FileData.Validity.REFRESHED:
            icon = icons.STOCK_FILE_REFRESHED
        elif validity == patch_db.FileData.Validity.NEEDS_REFRESH:
            icon = icons.STOCK_FILE_NEEDS_REFRESH
        elif validity == patch_db.FileData.Validity.UNREFRESHABLE:
            icon = icons.STOCK_FILE_UNREFRESHABLE
        else:
            icon = gtk.STOCK_FILE
        hbox.pack_start(gtk.image_new_from_stock(icon, gtk.ICON_SIZE_MENU), expand=False)
        label = gtk.Label(filepath)
        label.set_alignment(0, 0)
        label.set_padding(4, 0)
        hbox.pack_start(label, expand=True)
        hbox.show_all()
        return hbox
    @staticmethod
    def _framed(label, widget):
        frame = gtk.Frame(label)
        frame.add(widget)
        return frame
    def _populate_pages(self):
        existing = set([fpath for fpath in self.diff_displays])
        for diffplus in self.epatch.diff_pluses:
            filepath = diffplus.get_file_path(self.epatch.num_strip_levels)
            tab_label = self._make_file_label(filepath, diffplus.validity)
            menu_label = self._make_file_label(filepath, diffplus.validity)
            if filepath in existing:
                self.diff_displays[filepath].update(diffplus)
                self.diffs_nbook.set_tab_label(self.diff_displays[filepath], tab_label)
                self.diffs_nbook.set_menu_label(self.diff_displays[filepath], menu_label)
                existing.remove(filepath)
            else:
                self.diff_displays[filepath] = DiffDisplay(diffplus)
                self.diffs_nbook.append_page_menu(self.diff_displays[filepath], tab_label, menu_label)
        for gone in existing:
            gonedd = self.diff_displays.pop(gone)
            pnum = self.diffs_nbook.page_num(gonedd)
            self.diffs_nbook.remove_page(pnum)
    def update(self):
        self.epatch = patch_db.get_textpatch(self.patchname)
        self.status_box.remove(self.status_icon)
        self.status_icon = gtk.image_new_from_stock(self.status_icons[self.epatch.state], gtk.ICON_SIZE_BUTTON)
        self.status_box.add(self.status_icon)
        self.status_box.show_all()
        gutils.set_widget_tooltip_text(self.status_box, self.status_tooltips[self.epatch.state])
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        self.comments.set_contents(self.epatch.get_comments())
        self.description.set_contents(self.epatch.get_description())
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self._populate_pages()

class Dialogue(dialogue.AmodalDialog):
    def __init__(self, patchname):
        title = _('gdarn: Patch "{0}" : {1}').format(patchname, utils.path_rel_home(os.getcwd()))
        dialogue.AmodalDialog.__init__(self, title=title, parent=dialogue.main_window, flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        self.widget = Widget(patchname)
        self.vbox.pack_start(self.widget, expand=True, fill=True)
        self.refresh_action = gtk.Action('patch_view_refresh', _('_Refresh'), _('Refresh this patch in database.'), icons.STOCK_REFRESH_PATCH)
        self.refresh_action.connect('activate', self._refresh_acb)
        self.refresh_action.set_sensitive(self.widget.epatch.state != patch_db.PatchState.UNAPPLIED)
        refresh_button = gutils.ActionButton(self.refresh_action)
        self.action_area.pack_start(refresh_button)
        self._save_file = utils.convert_patchname_to_filename(patchname)
        self.save_action = gtk.Action('patch_view_save', _('_Export'), _('Export patch to text file.'), gtk.STOCK_SAVE_AS)
        self.save_action.connect('activate', self._save_as_acb)
        save_button = gutils.ActionButton(self.save_action)
        self.action_area.pack_start(save_button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._close_cb)
        self.add_notification_cb(ws_event.PATCH_CHANGES|ws_event.FILE_CHANGES, self._update_display_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()
    def _update_display_cb(self, _arg=None):
        self.show_busy()
        self.widget.update()
        self.refresh_action.set_sensitive(self.widget.epatch.state != patch_db.PatchState.UNAPPLIED)
        self.unshow_busy()
    def _refresh_acb(self, _action):
        self.show_busy()
        result = ifce.PM.do_refresh_patch(self.widget.patchname)
        self.unshow_busy()
        dialogue.report_any_problems(result)
    def _save_as_acb(self, _action):
        from . import patch_list
        patch_list.do_export_named_patch(self, self.widget.patchname, suggestion=self._save_file, busy_indicator=self)

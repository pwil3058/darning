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

'''Widget to display a complete patch'''

import os
import gtk

from darning import patch_db
from darning import utils

from darning.gui import textview
from darning.gui import dialogue
from darning.gui import icons
from darning.gui import diff
from darning.gui import ws_event

class DiffDisplay(diff.TextWidget):
    def __init__(self, diffplus):
        self.diffplus = diffplus
        diff.TextWidget.__init__(self)
    def _get_diff_text(self):
        return str(self.diffplus)
    def update(self, diffplus):
        self.diffplus = diffplus
        self.set_contents()

class Widget(gtk.VBox):
    status_icons = {
        patch_db.PatchState.UNAPPLIED : gtk.STOCK_DIALOG_QUESTION,
        patch_db.PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
        patch_db.PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
        patch_db.PatchState.APPLIED_UNREFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
    }
    class TWSDisplay(diff.TextWidget.TwsLineCountDisplay):
        LABEL = _('File(s) that add TWS: ')
    def __init__(self, patchname):
        gtk.VBox.__init__(self)
        self.patchname = patchname
        self.epatch = patch_db.get_extpatch(self.patchname)
        #
        self.status_icon = gtk.image_new_from_stock(self.status_icons[self.epatch.state], gtk.ICON_SIZE_BUTTON)
        self.status_box = gtk.HBox()
        self.status_box.add(self.status_icon)
        self.status_box.show_all()
        self.tws_display = self.TWSDisplay()
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        hbox = gtk.HBox()
        hbox.pack_start(self.status_box, expand=False)
        hbox.pack_start(gtk.Label(self.patchname), expand=False)
        hbox.pack_end(self.tws_display, expand=False)
        self.pack_start(hbox)
        #
        panes = [gtk.VPaned(), gtk.VPaned(), gtk.VPaned()]
        for index in [1, 2]:
            panes[index - 1].add2(panes[index])
        self.pack_start(panes[0], expand=True, fill=True)
        #
        self.comments = textview.Widget(aspect_ratio=0.1)
        self.comments.set_contents(self.epatch.get_comments())
        self.comments.view.set_editable(False)
        panes[0].add1(self._framed(_('Comments'), self.comments))
        #
        self.description = textview.Widget()
        self.description.set_contents(self.epatch.get_description())
        self.description.view.set_editable(False)
        panes[1].add1(self._framed(_('Description'), self.description))
        #
        self.diffstats = textview.Widget()
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self.diffstats.view.set_editable(False)
        panes[2].add1(self._framed(_('Diff Statistics'), self.diffstats))
        #
        self.diffs_nbook = gtk.Notebook()
        self.diffs_nbook.set_scrollable(True)
        self.diffs_nbook.popup_enable()
        panes[2].add2(self._framed(_('File Diffs'), self.diffs_nbook))
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
        self.epatch = patch_db.get_extpatch(self.patchname)
        self.status_box.remove(self.status_icon)
        self.status_icon = gtk.image_new_from_stock(self.status_icons[self.epatch.state], gtk.ICON_SIZE_BUTTON)
        self.status_box.add(self.status_icon)
        self.status_box.show_all()
        self.tws_display.set_value(len(self.epatch.report_trailing_whitespace()))
        self.comments.set_contents(self.epatch.get_comments())
        self.description.set_contents(self.epatch.get_description())
        self.diffstats.set_contents(self.epatch.get_header_diffstat())
        self._populate_pages()

class Dialogue(dialogue.AmodalDialog):
    def __init__(self, patchname):
        title = _('gdarn: Patch "{0}" : {1}').format(patchname, utils.path_rel_home(os.getcwd()))
        dialogue.AmodalDialog.__init__(self, title=title, parent=dialogue.main_window, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        self.widget = Widget(patchname)
        self.vbox.pack_start(self.widget, expand=True, fill=True)
        self.connect("response", self._close_cb)
        self.add_notification_cb(ws_event.PATCH_CHANGES|ws_event.FILE_CHANGES|ws_event.AUTO_UPDATE, self._update_display_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()
    def _update_display_cb(self, _arg=None):
        self.widget.update()

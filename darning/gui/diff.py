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

import re
import gtk
import pango
import os

from darning import options
from darning import runext
from darning import cmd_result

from darning.gui import textview
from darning.gui import dialogue
from darning.gui import ifce
from darning.gui import gutils

class TextWidget(gtk.VBox):
    class TwsLineCountDisplay(gtk.HBox):
        STATES = [gtk.STATE_NORMAL, gtk.STATE_ACTIVE, gtk.STATE_PRELIGHT, gtk.STATE_INSENSITIVE]
        def __init__(self):
            gtk.HBox.__init__(self)
            self.pack_start(gtk.Label(_('Added TWS lines:')), expand=False, fill=False)
            self._entry = gtk.Entry()
            self._entry.set_width_chars(1)
            self._entry.set_text(str(0))
            self._entry.set_editable(False)
            self.pack_start(self._entry, expand=False, fill=False)
            self.show_all()
        def set_value(self, val):
            sval = str(val)
            self._entry.set_width_chars(len(sval))
            self._entry.set_text(sval)
            if val:
                for state in self.STATES:
                    self._entry.modify_base(state, gtk.gdk.color_parse("#FF0000"))
            else:
                for state in self.STATES:
                    self._entry.modify_base(state, gtk.gdk.color_parse("#00FF00"))
    class View(textview.View):
        class Buffer(textview.Buffer):
            TWS_CHECK_CRE = re.compile('^(\+.*\S)(\s+\n)$')
            def __init__(self):
                textview.Buffer.__init__(self)
                self.index_tag = self.create_tag("INDEX", weight=pango.WEIGHT_BOLD, foreground="#0000AA", family="monospace")
                self.sep_tag = self.create_tag("SEP", weight=pango.WEIGHT_BOLD, foreground="#0000AA", family="monospace")
                self.minus_tag = self.create_tag("MINUS", foreground="#AA0000", family="monospace")
                self.lab_tag = self.create_tag("LAB", foreground="#AA0000", family="monospace")
                self.plus_tag = self.create_tag("PLUS", foreground="#006600", family="monospace")
                self.added_tws_tag = self.create_tag("ADDED_TWS", background="#006600", family="monospace")
                self.star_tag = self.create_tag("STAR", foreground="#006600", family="monospace")
                self.rab_tag = self.create_tag("RAB", foreground="#006600", family="monospace")
                self.change_tag = self.create_tag("CHANGED", foreground="#AA6600", family="monospace")
                self.stats_tag = self.create_tag("STATS", foreground="#AA00AA", family="monospace")
                self.func_tag = self.create_tag("FUNC", foreground="#00AAAA", family="monospace")
                self.unchanged_tag = self.create_tag("UNCHANGED", foreground="black", family="monospace")
            def _append_tagged_text(self, text, tag):
                self.insert_with_tags(self.get_end_iter(), text, tag)
            def _append_patch_line(self, line):
                first_char = line[0]
                if first_char == " ":
                    self._append_tagged_text(line, self.unchanged_tag)
                elif first_char == "+":
                    match = self.TWS_CHECK_CRE.match(line)
                    if match:
                        self._append_tagged_text(match.group(1), self.plus_tag)
                        self._append_tagged_text(match.group(2), self.added_tws_tag)
                        return len(match.group(1))
                    else:
                        self._append_tagged_text(line, self.plus_tag)
                elif first_char == "-":
                    self._append_tagged_text(line, self.minus_tag)
                elif first_char == "!":
                    self._append_tagged_text(line, self.change_tag)
                elif first_char == "@":
                    i = line.find("@@", 2)
                    if i == -1:
                        self._append_tagged_text(line, self.stats_tag)
                    else:
                        self._append_tagged_text(line[:i+2], self.stats_tag)
                        self._append_tagged_text(line[i+2:], self.func_tag)
                elif first_char == "=":
                    self._append_tagged_text(line, self.sep_tag)
                elif first_char == "*":
                    self._append_tagged_text(line, self.star_tag)
                elif first_char == "<":
                    self._append_tagged_text(line, self.lab_tag)
                elif first_char == ">":
                    self._append_tagged_text(line, self.rab_tag)
                else:
                    self._append_tagged_text(line, self.index_tag)
                return 0
        def __init__(self):
            textview.View.__init__(self, buffer=self.Buffer())
    def __init__(self):
        gtk.VBox.__init__(self)
        self.tws_list = []
        self.tws_index = 0
        self.view = TextWidget.View()
        self.pack_start(gutils.wrap_in_scrolled_window(self.view))
        self._action_group = gtk.ActionGroup("diff_text")
        self._action_group.add_actions(
            [
                ("diff_save", gtk.STOCK_SAVE, _('_Save'), None,
                 _('Save the diff to previously nominated file'), self._save_acb),
                ("diff_save_as", gtk.STOCK_SAVE_AS, _('Save _as'), None,
                 _('Save the diff to a nominated file'), self._save_as_acb),
                ("diff_refresh", gtk.STOCK_REFRESH, _('_Refresh'), None,
                 _('Refresh contents of the diff'), self._refresh_acb),
                ("tws_nav_first", gtk.STOCK_GOTO_TOP, _('_First'), None,
                 _('Scroll to first line with added trailing white space'),
                 self._tws_nav_first_acb),
                ("tws_nav_prev", gtk.STOCK_GO_UP, _('_Prev'), None,
                 _('Scroll to previous line with added trailing white space'),
                 self._tws_nav_prev_acb),
                ("tws_nav_next", gtk.STOCK_GO_DOWN, _('_Next'), None,
                 _('Scroll to next line with added trailing white space'),
                 self._tws_nav_next_acb),
                ("tws_nav_last", gtk.STOCK_GOTO_BOTTOM, _('_Last'), None,
                 _('Scroll to last line with added trailing white space'),
                 self._tws_nav_last_acb),
            ])
        self.tws_nav_buttonbox = gutils.ActionHButtonBox([self._action_group],
            ["tws_nav_first", "tws_nav_prev", "tws_nav_next", "tws_nav_last"])
        self._tws_nav_buttons_packed = False
        self._save_file = None
        self.check_set_save_sensitive()
        self.tws_display = self.TwsLineCountDisplay()
        self.set_contents()
        self.show_all()
    @property
    def bfr(self):
        return self.view.get_buffer()
    def _get_diff_text(self):
        return ""
    def set_contents(self):
        def update_for_tws_change(new_count):
            if self._tws_nav_buttons_packed and not new_count:
                self.remove(self.tws_nav_buttonbox)
                self.view.set_cursor_visible(False)
                self._tws_nav_buttons_packed = False
            elif not self._tws_nav_buttons_packed and new_count:
                self.pack_start(self.tws_nav_buttonbox, expand=False, fill=True)
                self.view.set_cursor_visible(True)
                self._tws_nav_buttons_packed = True
        text = self._get_diff_text()
        old_count = len(self.tws_list)
        self.bfr.begin_not_undoable_action()
        self.bfr.set_text("")
        self.tws_list = []
        line_no = 0
        for line in text.splitlines(True):
            offset = self.bfr._append_patch_line(line)
            if offset:
                self.tws_list.append((line_no, offset - 2))
            line_no += 1
        self.bfr.end_not_undoable_action()
        new_count = len(self.tws_list)
        self.tws_display.set_value(new_count)
        if not (new_count == old_count):
            update_for_tws_change(new_count)
    def _save_to_file(self):
        if not self._save_file:
            return
        try:
            fobj = open(self._save_file, 'w')
        except IOError as edata:
            strerror = edata[1]
            dialogue.report_any_problems(cmd_result.Result(cmd_result.ERROR, "", strerror))
            self.check_set_save_sensitive()
            return
        text = self.bfr.get_text(self.bfr.get_start_iter(), self.bfr.get_end_iter())
        fobj.write(text)
        fobj.close()
        self.check_set_save_sensitive()
    def _tws_index_iter(self):
        pos = self.tws_list[self.tws_index]
        model_iter = self.bfr.get_iter_at_line_offset(pos[0], pos[1])
        self.bfr.place_cursor(model_iter)
        return model_iter
    def get_tws_first_iter(self):
        self.tws_index = 0
        return self._tws_index_iter()
    def get_tws_prev_iter(self):
        if self.tws_index:
            self.tws_index -= 1
        return self._tws_index_iter()
    def get_tws_next_iter(self):
        self.tws_index += 1
        if self.tws_index >= len(self.tws_list):
            self.tws_index = len(self.tws_list) - 1
        return self._tws_index_iter()
    def get_tws_last_iter(self):
        self.tws_index = len(self.tws_list) - 1
        return self._tws_index_iter()
    def check_save_sensitive(self):
        return self._save_file is not None and os.path.exists(self._save_file)
    def check_set_save_sensitive(self):
        set_sensitive = self.check_save_sensitive()
        self._action_group.get_action("diff_save").set_sensitive(set_sensitive)
    def _refresh_acb(self, _action):
        self.set_contents()
    def _save_acb(self, _action):
        self._save_to_file()
    def _save_as_acb(self, _action):
        if self._save_file:
            suggestion = self._save_file
        else:
            suggestion = os.getcwd()
        self._save_file = dialogue.ask_file_name(_('Save as ...'), suggestion=suggestion, existing=False)
        self._save_to_file()
    def get_action_button_box(self, a_name_list):
        return gutils.ActionHButtonBox([self._action_group], action_name_list=a_name_list)
    def get_action_button_list(self, a_name_list):
        return gutils.ActionButtonList([self._action_group], action_name_list=a_name_list)
    def _tws_nav_first_acb(self, _action):
        self.view.scroll_to_iter(self.get_tws_first_iter(), 0.01, True)
    def _tws_nav_prev_acb(self, _action):
        self.view.scroll_to_iter(self.get_tws_prev_iter(), 0.01, True)
    def _tws_nav_next_acb(self, _action):
        self.view.scroll_to_iter(self.get_tws_next_iter(), 0.01, True)
    def _tws_nav_last_acb(self, _action):
        self.view.scroll_to_iter(self.get_tws_last_iter(), 0.01, True)
    def get_tws_nav_button_box(self):
        a_name_list = ["tws_nav_first", "tws_nav_prev", "tws_nav_next", "tws_nav_last"]
        return self.get_action_button_box(action_name_list=a_name_list)

class ForFileDialog(dialogue.AmodalDialog):
    class Widget(TextWidget):
        def __init__(self, filepath, patchname=None):
            self.filepath = filepath
            self.patchname = patchname
            TextWidget.__init__(self)
        def _get_diff_text(self):
            diff = ifce.PM.get_file_diff(self.filepath, self.patchname)
            return str(diff)
    def __init__(self, filepath, patchname):
        if patchname is None:
            patchname = ifce.PM.get_top_applied_patch_for_file(filepath)
        assert patchname is not None
        title = _('diff: "{0}" in "{1}": {2}').format(filepath, patchname, os.getcwd())
        flags = gtk.DIALOG_DESTROY_WITH_PARENT
        dialogue.AmodalDialog.__init__(self, title, None, flags, ())
        self.widget = self.Widget(filepath, patchname)
        self.vbox.pack_start(self.widget, expand=True, fill=True)
        self.action_area.pack_end(self.widget.tws_display, expand=False, fill=False)
        for button in self.widget.get_action_button_list(["diff_save", "diff_save_as", "diff_refresh"]).list:
            self.action_area.pack_start(button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._close_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()

class CombinedForFileDialog(dialogue.AmodalDialog):
    class Widget(TextWidget):
        def __init__(self, filepath):
            self.filepath = filepath
            TextWidget.__init__(self)
        def _get_diff_text(self):
            diff = ifce.PM.get_file_combined_diff(self.filepath)
            return str(diff)
    def __init__(self, filepath):
        title = _('combined diff: "{0}": {1}').format(filepath, os.getcwd())
        flags = gtk.DIALOG_DESTROY_WITH_PARENT
        dialogue.AmodalDialog.__init__(self, title, None, flags, ())
        self.widget = self.Widget(filepath)
        self.vbox.pack_start(self.widget, expand=True, fill=True)
        self.action_area.pack_end(self.widget.tws_display, expand=False, fill=False)
        for button in self.widget.get_action_button_list(["diff_save", "diff_save_as", "diff_refresh"]).list:
            self.action_area.pack_start(button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._close_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()

options.define('diff', 'extdiff', options.Defn(str, None, _('The name of external application for viewing diffs')))

def launch_external_diff(file_a, file_b):
    extdiff = options.get('diff', 'extdiff')
    if not extdiff:
        return cmd_result.Result(cmd_result.WARNING, '', _('No extenal diff viewer is defined.\n'))
    try:
        runext.run_cmd_in_bgnd([extdiff, file_a, file_b])
    except OSError as edata:
        return cmd_result.Result(cmd_result.ERROR, '', _('Error lanuching external viewer "{0}": {1}\n').format(extdiff, edata.strerror))
    return cmd_result.Result(cmd_result.OK, '', '')

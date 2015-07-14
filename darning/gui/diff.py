### Copyright (C) 2007-2015 Peter Williams <pwil3058@gmail.com>
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

import gtk
import pango

from ..cmd_result import CmdResult, CmdFailure

from .. import utils
from .. import options
from .. import runext
from .. import patchlib

from . import dialogue
from . import textview
from . import ifce
from . import gutils
from . import icons

class FileAndRefreshActions:
    def __init__(self):
        self._action_group = gtk.ActionGroup("diff_file_and_refresh")
        self._action_group.add_actions(
            [
                ("diff_save", gtk.STOCK_SAVE, _('_Save'), None,
                 _('Save the diff to previously nominated file'), self._save_acb),
                ("diff_save_as", gtk.STOCK_SAVE_AS, _('Save _as'), None,
                 _('Save the diff to a nominated file'), self._save_as_acb),
                ("diff_refresh", gtk.STOCK_REFRESH, _('_Refresh'), None,
                 _('Refresh contents of the diff'), self._refresh_acb),
            ])
        self._save_file = None
        self.check_set_save_sensitive()
    def check_save_sensitive(self):
        return self._save_file is not None and os.path.exists(self._save_file)
    def check_set_save_sensitive(self):
        set_sensitive = self.check_save_sensitive()
        self._action_group.get_action("diff_save").set_sensitive(set_sensitive)
    def _save_acb(self, _action):
        self._save_to_file()
    def _save_as_acb(self, _action):
        if self._save_file:
            suggestion = self._save_file
        else:
            suggestion = os.getcwd()
        self._save_file = dialogue.ask_file_name(_('Save as ...'), suggestion=suggestion, existing=False)
        self._save_to_file()
    def _save_to_file(self):
        if not self._save_file:
            return
        try:
            fobj = open(self._save_file, 'w')
        except IOError as edata:
            dialogue.report_any_problems(CmdResult.error(stderr=edata[1]))
            self.check_set_save_sensitive()
            return
        text = self._get_text_to_save()
        fobj.write(text)
        fobj.close()
        self.check_set_save_sensitive()

class TextWidget(gtk.VBox):
    class TwsLineCountDisplay(gtk.HBox):
        STATES = [gtk.STATE_NORMAL, gtk.STATE_ACTIVE, gtk.STATE_PRELIGHT, gtk.STATE_INSENSITIVE]
        LABEL = _("Added TWS lines:")
        def __init__(self):
            gtk.HBox.__init__(self)
            self.pack_start(gtk.Label(self.LABEL), expand=False, fill=False)
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
            TWS_CHECK_CRE = re.compile("^(\+.*\S)(\s+\n)$")
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
        def __init__(self, width_in_chars=81, aspect_ratio=0.33, fdesc=None):
            textview.View.__init__(self, buffer=self.Buffer(), width_in_chars=width_in_chars, aspect_ratio=aspect_ratio, fdesc=fdesc)
            self.set_editable(False)
            self.set_cursor_visible(False)
    def __init__(self, width_in_chars=81, aspect_ratio=0.33, fdesc=None):
        gtk.VBox.__init__(self)
        self.tws_list = []
        self.tws_index = 0
        self.view = self.View(width_in_chars=width_in_chars, aspect_ratio=aspect_ratio, fdesc=fdesc)
        self._sw = gutils.wrap_in_scrolled_window(self.view)
        self.pack_start(self._sw)
        self._action_group = gtk.ActionGroup("diff_text")
        self._action_group.add_actions(
            [
                ("diff_save", gtk.STOCK_SAVE, _("_Save"), None,
                 _("Save the diff to previously nominated file"), self._save_acb),
                ("diff_save_as", gtk.STOCK_SAVE_AS, _("Save _as"), None,
                 _("Save the diff to a nominated file"), self._save_as_acb),
                ("diff_refresh", gtk.STOCK_REFRESH, _("_Refresh"), None,
                 _("Refresh contents of the diff"), self._refresh_acb),
                ("tws_nav_first", gtk.STOCK_GOTO_TOP, _("_First"), None,
                 _("Scroll to first line with added trailing white space"),
                 self._tws_nav_first_acb),
                ("tws_nav_prev", gtk.STOCK_GO_UP, _("_Prev"), None,
                 _("Scroll to previous line with added trailing white space"),
                 self._tws_nav_prev_acb),
                ("tws_nav_next", gtk.STOCK_GO_DOWN, _("_Next"), None,
                 _("Scroll to next line with added trailing white space"),
                 self._tws_nav_next_acb),
                ("tws_nav_last", gtk.STOCK_GOTO_BOTTOM, _("_Last"), None,
                 _("Scroll to last line with added trailing white space"),
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
    @property
    def h_scrollbar(self):
        return self._sw.get_hscrollbar()
    @property
    def v_scrollbar(self):
        return self._sw.get_vscrollbar()
    def get_scrollbar_values(self):
        return (self.h_scrollbar.get_value(), self.h_scrollbar.get_value())
    def set_scrollbar_values(self, values):
        self.h_scrollbar.set_value(values[0])
        self.v_scrollbar.set_value(values[1])
    def _get_diff_text_iter(self):
        return []
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
            self.show_all()
        old_count = len(self.tws_list)
        self.bfr.begin_not_undoable_action()
        self.bfr.set_text("")
        self.tws_list = []
        line_no = 0
        for line in self._get_diff_text_iter():
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
            fobj = open(self._save_file, "w")
        except IOError as edata:
            strerror = edata[1]
            dialogue.report_any_problems(CmdResult.error(stderr=strerror))
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
        self._save_file = dialogue.ask_file_name(_("Save as ..."), suggestion=suggestion, existing=False)
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

class DiffPlusDisplay(TextWidget):
    def __init__(self, diffplus):
        self.diffplus = diffplus
        self._diff_digest = diffplus.get_hash_digest()
        TextWidget.__init__(self)
        self.tws_nav_buttonbox.pack_start(self.tws_display, expand=False)
        self.tws_nav_buttonbox.reorder_child(self.tws_display, 0)
    def _get_diff_text_iter(self):
        return self.diffplus.iter_lines()
    def update(self, diffplus):
        digest = diffplus.get_hash_digest()
        if digest != self._diff_digest:
            sbars = self.get_scrollbar_values()
            self.diffplus = diffplus
            self._diff_digest = digest
            self.set_contents()
            self.set_scrollbar_values(sbars)

class DiffPlusNotebook(gtk.Notebook):
    class TWSDisplay(TextWidget.TwsLineCountDisplay):
        LABEL = _("File(s) that add TWS: ")
    def __init__(self, diff_pluses=None, digest=None, num_strip_levels=1):
        gtk.Notebook.__init__(self)
        self.diff_pluses = [] if diff_pluses is None else diff_pluses
        self.digest = self.calc_diff_pluses_digest(diff_pluses) if (digest is None and diff_pluses) else digest
        self.num_strip_levels = num_strip_levels
        self.tws_display = self.TWSDisplay()
        self.tws_display.set_value(0)
        self.set_scrollable(True)
        self.popup_enable()
        self.diff_displays = {}
        self._populate_pages()
    @staticmethod
    def calc_diff_pluses_digest(diff_pluses):
        h = hashlib.sha1()
        for diff_plus in diff_pluses:
            for line in diff_plus.iter_lines():
                h.update(line)
        return h.digest()
    @staticmethod
    def _make_file_label(filepath, file_icon):
        hbox = gtk.HBox()
        icon = file_icon
        hbox.pack_start(gtk.image_new_from_stock(icon, gtk.ICON_SIZE_MENU), expand=False)
        label = gtk.Label(filepath)
        label.set_alignment(0, 0)
        label.set_padding(4, 0)
        hbox.pack_start(label, expand=True)
        hbox.show_all()
        return hbox
    @staticmethod
    def _file_icon_for_condition(condition):
        if not condition:
            return icons.STOCK_FILE_PROBLEM
        return gtk.STOCK_FILE
    def _populate_pages(self):
        num_tws_files = 0
        for diffplus in self.diff_pluses:
            filepath = diffplus.get_file_path(self.num_strip_levels)
            if diffplus.report_trailing_whitespace():
                file_icon = self._file_icon_for_condition(False)
                num_tws_files += 1
            else:
                file_icon = self._file_icon_for_condition(True)
            tab_label = self._make_file_label(filepath, file_icon)
            menu_label = self._make_file_label(filepath, file_icon)
            self.diff_displays[filepath] = DiffPlusDisplay(diffplus)
            self.append_page_menu(self.diff_displays[filepath], tab_label, menu_label)
        self.tws_display.set_value(num_tws_files)
    def _update_pages(self):
        existing = set([fpath for fpath in self.diff_displays])
        num_tws_files = 0
        for diffplus in self.diff_pluses:
            filepath = diffplus.get_file_path(self.num_strip_levels)
            if diffplus.report_trailing_whitespace():
                file_icon = self._file_icon_for_condition(False)
                num_tws_files += 1
            else:
                file_icon = self._file_icon_for_condition(True)
            tab_label = self._make_file_label(filepath, file_icon)
            menu_label = self._make_file_label(filepath, file_icon)
            if filepath in existing:
                self.diff_displays[filepath].update(diffplus)
                self.set_tab_label(self.diff_displays[filepath], tab_label)
                self.set_menu_label(self.diff_displays[filepath], menu_label)
                existing.remove(filepath)
            else:
                self.diff_displays[filepath] = DiffPlusDisplay(diffplus)
                self.append_page_menu(self.diff_displays[filepath], tab_label, menu_label)
        for gone in existing:
            gonedd = self.diff_displays.pop(gone)
            pnum = self.page_num(gonedd)
            self.remove_page(pnum)
        self.tws_display.set_value(num_tws_files)
    def set_diff_pluses(self, diff_pluses, digest=None):
        if digest is None:
            digest = self.calc_diff_pluses_digest(diff_pluses)
        if digest != self.digest:
            self.diff_pluses = diff_pluses
            self.digest = digest
            self._update_pages()
    def __str__(self):
        return "".join((str(diff_plus) for diff_plus in self.diff_pluses))

class DiffPlusesWidget(DiffPlusNotebook, FileAndRefreshActions):
    A_NAME_LIST = ["diff_save", "diff_save_as", "diff_refresh"]
    def __init__(self, num_strip_levels=1, **kwargs):
        DiffPlusNotebook.__init__(self, diff_pluses=self._get_diff_pluses(), num_strip_levels=num_strip_levels)
        FileAndRefreshActions.__init__(self)
        self.diff_buttons = gutils.ActionButtonList([self._action_group], self.A_NAME_LIST)
    def _get_diff_pluses(self):
        assert False, _("_get_diff_pluses() must be defined in children")
    def _refresh_acb(self, _action):
        self.update()
    def update(self):
        diff_pluses = self._get_diff_pluses()
        digest = self.calc_diff_pluses_digest(diff_pluses)
        if digest != self.digest:
            self.diff_pluses = diff_pluses
            self.digest = digest
            self._update_pages()
    def _get_text_to_save(self):
        return str(self)
    def window_title(self):
        return ""

class TopPatchDiffPlusesWidget(DiffPlusesWidget):
    def __init__(self, file_paths=None, num_strip_levels=1):
        self._file_paths = file_paths
        DiffPlusesWidget.__init__(self)
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

class NamedPatchDiffPlusesWidget(DiffPlusesWidget):
    A_NAME_LIST = ["diff_save", "diff_save_as"]
    def __init__(self, patch_name=None, file_paths=None, num_strip_levels=1):
        self._patch_name = patch_name
        self._file_paths = file_paths
        DiffPlusesWidget.__init__(self)
    def _get_diff_pluses(self):
        return ifce.PM.get_named_patch_diff_pluses(self._patch_name, self._file_paths)
    @property
    def window_title(self):
        return _("Patch \"{0}\" diff: {1}").format(self._patch_name, utils.cwd_rel_home())

class _DiffDialog(dialogue.AmodalDialog):
    DIFFS_WIDGET = None
    def __init__(self, parent=None, **kwargs):
        flags = gtk.DIALOG_DESTROY_WITH_PARENT
        dialogue.AmodalDialog.__init__(self, None, parent if parent else dialogue.main_window, flags, ())
        dtw = self.DIFFS_WIDGET(**kwargs)
        self.set_title(dtw.window_title)
        self.vbox.pack_start(dtw)
        tws_display = dtw.tws_display
        self.action_area.pack_end(tws_display, expand=False, fill=False)
        for button in dtw.diff_buttons.list:
            self.action_area.pack_start(button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
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

class DiffTextWidget(DiffPlusNotebook, FileAndRefreshActions):
    A_NAME_LIST = ["diff_save", "diff_save_as", "diff_refresh"]
    def __init__(self, num_strip_levels=1, **kwargs):
        diff_text = self._get_diff_text()
        digest = hashlib.sha1(diff_text).digest()
        diff_pluses = patchlib.Patch.parse_text(diff_text).diff_pluses
        DiffPlusNotebook.__init__(self, diff_pluses=diff_pluses, digest=digest, num_strip_levels=num_strip_levels)
        FileAndRefreshActions.__init__(self)
        self.diff_buttons = gutils.ActionButtonList([self._action_group], self.A_NAME_LIST)
    def _get_diff_text(self):
        assert False, _("_get_diff_text() must be defined in children")
    def _refresh_acb(self, _action):
        self.update()
    def update(self):
        diff_text = self._get_diff_text()
        digest = hashlib.sha1(diff_text).digest()
        if digest != self.digest:
            self.diff_pluses = patchlib.Patch.parse_text(diff_text).diff_pluses
            self.digest = digest
            self._update_pages()
    def _get_text_to_save(self):
        return str(self)
    def window_title(self):
        return ""

class TopPatchDiffTextWidget(DiffTextWidget):
    def __init__(self, file_paths=None, num_strip_levels=1):
        self._file_paths = file_paths
        DiffTextWidget.__init__(self)
    def _get_diff_text(self):
        return ifce.PM.get_top_patch_diff_text(self._file_paths)
    @property
    def window_title(self):
        return _("Top Patch: diff: {0}").format(utils.cwd_rel_home())

class TopPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = TopPatchDiffTextWidget

class CombinedPatchDiffTextWidget(DiffTextWidget):
    def __init__(self, file_paths=None, num_strip_levels=1):
        self._file_paths = file_paths
        DiffTextWidget.__init__(self)
    def _get_diff_text(self):
        return ifce.PM.get_combined_patch_diff_text(self._file_paths)
    @property
    def window_title(self):
        return _("Combined Patches diff: {0}").format(utils.cwd_rel_home())

class CombinedPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = CombinedPatchDiffTextWidget

class NamedPatchDiffTextWidget(DiffTextWidget):
    A_NAME_LIST = ["diff_save", "diff_save_as"]
    def __init__(self, patch_name=None, file_paths=None, num_strip_levels=1):
        self._patch_name = patch_name
        self._file_paths = file_paths
        DiffTextWidget.__init__(self)
    def _get_diff_text(self):
        return ifce.PM.get_named_patch_diff_text(self._patch_name, self._file_paths)
    @property
    def window_title(self):
        return _("Patch \"{0}\" diff: {1}").format(self._patch_name, utils.cwd_rel_home())

class NamedPatchDiffTextDialog(_DiffDialog):
    DIFFS_WIDGET = NamedPatchDiffTextWidget

def launch_external_diff(file_a, file_b):
    extdiff = options.get("diff", "extdiff")
    if not extdiff:
        return CmdResult.warning(_("No external diff viewer is defined.\n"))
    try:
        runext.run_cmd_in_bgnd([extdiff, file_a, file_b])
    except OSError as edata:
        return CmdResult.error(stderr=_("Error launching external viewer \"{0}\": {1}\n").format(extdiff, edata.strerror))
    return CmdResult.ok()

class WdDiffTextWidget(DiffTextWidget, FileAndRefreshActions):
    DIFF_MODES = ['git diff', 'git diff --staged', 'git diff HEAD']
    def __init__(self):
        self.mode_button = {}
        button = None
        for mode in self.DIFF_MODES:
            self.mode_button[mode] = button = gtk.RadioButton(button, mode)
            button.connect('toggled', self._diff_mode_toggled_cb)
        DiffTextWidget.__init__(self)
        FileAndRefreshActions.__init__(self)
        self.a_name_list = ["diff_save", "diff_save_as", "diff_refresh"]
        self.diff_buttons = gutils.ActionButtonList([self._action_group], self.a_name_list)
    def _get_diff_text(self):
        # TODO: think about making -M a selectable option
        try:
            if self.mode_button['git diff --staged'].get_active():
                return ifce.SCM.get_diff('-M', '--staged')
            elif self.mode_button['git diff HEAD'].get_active():
                return ifce.SCM.get_diff('-M', 'HEAD')
            if self.mode_button['git diff'].get_active():
                return ifce.SCM.get_diff('-M')
        except CmdFailure as failure:
            dialogue.report_failure(failure)
            return failure.result.stdout
    def _diff_mode_toggled_cb(self, _data=None):
        self.update()
    def _refresh_acb(self, _action):
        self.update()
    def _get_text_to_save(self):
        return str(self)

class WdDiffTextDialog(dialogue.AmodalDialog):
    def __init__(self, parent=None):
        flags = gtk.DIALOG_DESTROY_WITH_PARENT
        dialogue.AmodalDialog.__init__(self, None, parent, flags, ())
        title = "diff: %s" % utils.cwd_rel_home()
        self.set_title(title)
        dtw = WdDiffTextWidget()
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_('Mode:')), expand=False)
        for key in dtw.DIFF_MODES:
            hbox.pack_start(dtw.mode_button[key], expand= False)
        self.vbox.pack_start(hbox, expand=False)
        self.vbox.pack_start(dtw)
        tws_display = dtw.tws_display
        self.action_area.pack_end(tws_display, expand=False, fill=False)
        for button in dtw.diff_buttons.list:
            self.action_area.pack_start(button)
        self.add_buttons(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._close_cb)
        self.show_all()
    def _close_cb(self, dialog, response_id):
        dialog.destroy()

class ForFileDialog(dialogue.AmodalDialog):
    class Widget(TextWidget):
        def __init__(self, filepath, patchname=None):
            self.filepath = filepath
            self.patchname = patchname
            TextWidget.__init__(self)
        def _get_diff_text_iter(self):
            diff = ifce.PM.get_file_diff(self.filepath, self.patchname)
            return diff.iter_lines()
    def __init__(self, filepath, patchname):
        if patchname is None:
            patchname = ifce.PM.get_top_patch_for_file(filepath)
        assert patchname is not None
        title = _("diff: \"{0}\" in \"{1}\": {2}").format(filepath, patchname, os.getcwd())
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
        def _get_diff_text_iter(self):
            diff = ifce.PM.get_file_combined_diff(self.filepath)
            return diff.iter_lines()
    def __init__(self, filepath):
        title = _("combined diff: \"{0}\": {1}").format(filepath, os.getcwd())
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

#GLOBAL ACTIONS
from . import actions
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

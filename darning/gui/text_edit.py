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

import gtk
import pango

from darning import cmd_result

from darning.gui import textview
from darning.gui import gutils
from darning.gui import dialogue
from darning.gui import ifce

class Widget(textview.Widget):
    UI_DESCR = ''
    def get_text_fm_db(self):
        raise NotImplentedError('Must be defined in child')
    def set_text_in_db(self, text):
        raise NotImplentedError('Must be defined in child')
    def __init__(self, save_file_name=None, auto_save=False):
        textview.Widget.__init__(self)
        self.view.set_right_margin_position(72)
        self.view.set_show_right_margin(True)
        self.view.set_cursor_visible(True)
        self.view.set_editable(True)
        # Set up file stuff
        self._save_interval = 1000 # milliseconds
        self._save_file_name = save_file_name
        self._save_file_digest = None
        # Set up action groups
        self.action_group = gtk.ActionGroup("always on")
        self.conditional_action_group = gtk.ActionGroup("save file dependent")
        self.action_group.add_actions(
            [
                ("text_edit_ack", None, "_Ack", None,
                 "Insert Acked-by tag at cursor position", self._insert_ack_acb),
                ("text_edit_sign_off", None, "_Sign Off", None,
                 "Insert Signed-off-by tag at cursor position", self._insert_sign_off_acb),
                ("text_edit_author", None, "A_uthor", None,
                 "Insert Author tag at cursor position", self._insert_author_acb),
                ("text_edit_save", gtk.STOCK_SAVE, "_Save", "",
                 "Save summary to database", self._save_text_acb),
                ("text_edit_load", gtk.STOCK_REVERT_TO_SAVED, "_Reload", "",
                 "Reload summary from database", self._reload_text_acb),
                ("text_edit_save_as", gtk.STOCK_SAVE_AS, "S_ave as", "",
                 "Save summary to a file", self._save_text_as_acb),
                ("text_edit_load_from", gtk.STOCK_REVERT_TO_SAVED, "_Load from", "",
                 "Load summary from a file", self._load_text_from_acb),
                ("text_edit_insert_from", gtk.STOCK_PASTE, "_Insert from", "",
                 "Insert the contents of a file at cursor position", self._insert_text_from_acb),
            ])
        self.conditional_action_group.add_actions(
            [
                ("text_edit_save_to_file", gtk.STOCK_SAVE, "_Save", "",
                 "Save summary to file", self._save_text_to_file_acb),
                ("text_edit_load_fm_file", gtk.STOCK_REVERT_TO_SAVED, "_Revert", "",
                 "Load summary from saved file", self._load_text_fm_file_acb),
            ])
        self.save_toggle_action = gtk.ToggleAction(
                "text_edit_toggle_auto_save", "Auto Sa_ve",
                "Automatically/periodically save summary to file", gtk.STOCK_SAVE
            )
        self.save_toggle_action.connect("toggled", self._toggle_auto_save_acb)
        self.save_toggle_action.set_active(auto_save)
        self.conditional_action_group.add_action(self.save_toggle_action)
        self._update_action_sensitivities()
        # Make some buttons
        self.save_button = gutils.ActionButton(self.action_group.get_action("text_edit_save"), use_underline=False)
        self.reload_button = gutils.ActionButton(self.action_group.get_action("text_edit_load"), use_underline=False)
        # Set up UI manager
        self.ui_manager = gutils.UIManager()
        self.ui_manager.insert_action_group(self.action_group)
        self.ui_manager.insert_action_group(self.conditional_action_group)
        self.ui_manager.add_ui_from_string(self.UI_DESCR)
    def _update_action_sensitivities(self):
        self.conditional_action_group.set_sensitive(self._save_file_name is not None)
    def _insert_sign_off_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        self.bfr.insert_at_cursor("Signed-off-by: %s\n" % data)
    def _insert_ack_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        self.bfr.insert_at_cursor("Acked-by: %s\n" % data)
    def _insert_author_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        self.bfr.insert_at_cursor("Author: %s\n" % data)
    def _save_text_acb(self, _action=None):
        text = self.bfr.get_text(self.bfr.get_start_iter(), self.bfr.get_end_iter())
        result = self.set_text_in_db(text)
        if result.eflags:
            dialogue.report_any_problems(result)
        else:
            self.bfr.set_modified(False)
    def load_text_fm_db(self):
        try:
            self.set_contents(self.get_text_fm_db())
            self.bfr.set_modified(False)
            self._save_file_digest = None
        except cmd_result.Failure as failure:
            dialogue.report_failure(failure)
    def _ok_to_overwrite_summary(self):
        if self.bfr.get_char_count():
            return dialogue.ask_ok_cancel("Buffer contents will be destroyed. Continue?")
        return True
    def _reload_text_acb(self, _action=None):
        if self._ok_to_overwrite_summary():
            self.load_text_fm_db()
    def save_text_to_file(self, file_name=None):
        if not file_name:
            file_name = self._save_file_name
        try:
            open(file_name, 'w').write(self.get_contents())
            self._save_file_name = file_name
            self._save_file_digest = self.digest
        except IOError:
            dialogue.alert_user('Save failed!')
    def _save_text_to_file_acb(self, _action=None):
        self.save_text_to_file()
    def _save_text_as_acb(self, _action=None):
        fname = dialogue.ask_file_name("Enter file name", existing=False, suggestion=self._save_file_name)
        if fname and os.path.exists(fname) and not utils.samefile(fname, self._save_file_name):
            if not utils.samefile(fname, ifce.SCM.get_default_commit_save_file()):
                if not dialogue.ask_ok_cancel(os.linesep.join([fname, "\nFile exists. Overwrite?"])):
                    return
        self.save_text_to_file(file_name=fname)
    def load_text_fm_file(self, file_name=None, already_checked=False):
        if not already_checked and not self._ok_to_overwrite_summary():
            return
        if not file_name:
            file_name = self._save_file_name
        try:
            self.set_contents(open(file_name, 'rb').read())
            self._save_file_name = file_name
            self._save_file_digest = self.digest
        except IOError:
            dialogue.alert_user('Load from file failed!')
    def _load_text_fm_file_acb(self, _action=None):
        self.load_text_fm_file()
    def _load_text_from_acb(self, _action=None):
        if not self._ok_to_overwrite_summary():
            return
        fname = dialogue.ask_file_name("Enter file name", existing=True)
        self.load_text_fm_file(file_name=fname, already_checked=True)
    def _insert_text_from_acb(self, _action=None):
        file_name = dialogue.ask_file_name("Enter file name", existing=True)
        if file_name is not None:
            try:
                text = open(file_name, 'rb').read()
                self.bfr.insert_at_cursor(text)
                self.bfr.set_modified(True)
            except IOError:
                dialogue.alert_user('Insert at cursor from file failed!')
    def get_auto_save(self):
        return self.save_toggle_action.get_active()
    def set_auto_save(self, active=True):
        self.save_toggle_action.set_active(active)
    def get_auto_save_interval(self):
        return self._save_interval
    def set_auto_save_inerval(self, interval):
        self._save_interval = interval
    def do_auto_save(self):
        if self._save_file_name:
            if not self._save_file_digest or self._save_file_digest != self.digest:
                self.save_text_to_file()
        return self.get_auto_save()
    def _toggle_auto_save_acb(self, _action=None):
        if self.get_auto_save():
            gobject.timeout_add(self._save_interval, self.do_auto_save)
    def finish_up(self, clear_save=False):
        if self.get_auto_save():
            self.set_auto_save(False)
            self.do_auto_save()
        if clear_save and self._save_file_name:
            self.save_text_to_file(content="")
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

import shlex
import os
try:
    import gtkspell
    GTKSPELL_AVAILABLE = True
except ImportError:
    GTKSPELL_AVAILABLE = False

from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import GObject

from aipoed import CmdFailure

from aipoed.gui import actions
from aipoed.gui import dialogue
from aipoed.gui import gutils

from .. import utils

from . import textview
from . import ifce
from . import config

class MessageWidget(textview.Widget, actions.CAGandUIManager):
    UI_DESCR = ''
    AC_SAVE_OK = actions.ActionCondns.new_flag()
    def __init__(self, save_file_name=None, auto_save=False, parent=None):
        self._parent = parent
        textview.Widget.__init__(self)
        actions.CAGandUIManager.__init__(self)
        self.view.set_cursor_visible(True)
        self.view.set_editable(True)
        if GTKSPELL_AVAILABLE:
            gtkspell.Spell(self.view)
        # Set up file stuff
        self._save_interval = 1000 # milliseconds
        self._save_file_name = save_file_name
        self._save_file_digest = None
        self.save_toggle_action.set_active(auto_save)
        self._update_action_sensitivities()
    def populate_action_groups(self):
        # Set up action groups
        # TODO: self.conditional_action_group = Gtk.ActionGroup("save file dependent")
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("text_edit_ack", None, _('_Ack'), None,
                 _('Insert Acked-by tag at cursor position'), self._insert_ack_acb),
                ("text_edit_sign_off", None, _('_Sign Off'), None,
                 _('Insert Signed-off-by tag at cursor position'), self._insert_sign_off_acb),
                ("text_edit_author", None, _('A_uthor'), None,
                 _('Insert Author tag at cursor position'), self._insert_author_acb),
                ("text_edit_save_as", Gtk.STOCK_SAVE_AS, _('S_ave as'), "",
                 _('Save summary to a file'), self._save_text_as_acb),
                ("text_edit_load_from", Gtk.STOCK_REVERT_TO_SAVED, _('_Load from'), "",
                 _('Load summary from a file'), self._load_text_from_acb),
                ("text_edit_insert_from", Gtk.STOCK_PASTE, _('_Insert from'), '',
                 _('Insert the contents of a file at cursor position'), self._insert_text_from_acb),
            ])
        self.action_groups[self.AC_SAVE_OK].add_actions(
            [
                ("text_edit_save_to_file", Gtk.STOCK_SAVE, _('_Save'), "",
                 _('Save summary to file'), self._save_text_to_file_acb),
                ("text_edit_load_fm_file", Gtk.STOCK_REVERT_TO_SAVED, _('_Revert'), "",
                 _('Load summary from saved file'), self._load_text_fm_file_acb),
            ])
        self.save_toggle_action = Gtk.ToggleAction(
                "text_edit_toggle_auto_save", _('Auto Sa_ve'),
                _('Automatically/periodically save summary to file'), Gtk.STOCK_SAVE
            )
        self.save_toggle_action.connect("toggled", self._toggle_auto_save_acb)
        self.action_groups[self.AC_SAVE_OK].add_action(self.save_toggle_action)
    def _update_action_sensitivities(self):
        mcondn = actions.MaskedCondns(0 if self._save_file_name is not None else self.AC_SAVE_OK, self.AC_SAVE_OK)
        self.action_groups.update_condns(mcondn)
    @staticmethod
    def _inform_user_data_problem():
        dialogue.main_window.inform_user(_('Unable to determine user\'s data'), parent=self._parent)
    def _insert_sign_off_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        if data:
            self.bfr.insert_at_cursor("Signed-off-by: %s\n" % data)
        else:
            self._inform_user_data_problem()
    def _insert_ack_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        if data:
            self.bfr.insert_at_cursor("Acked-by: %s\n" % data)
        else:
            self._inform_user_data_problem()
    def _insert_author_acb(self, _action=None):
        data = ifce.get_author_name_and_email()
        if data:
            self.bfr.insert_at_cursor("Author: %s\n" % data)
        else:
            self._inform_user_data_problem()
    def _ok_to_overwrite_summary(self):
        if self.bfr.get_char_count():
            return dialogue.main_window.ask_ok_cancel(_('Buffer contents will be destroyed. Continue?'))
        return True
    def save_text_to_file(self, file_name=None):
        if not file_name:
            if not self._save_file_name:
                return
            file_name = self._save_file_name
        try:
            open(file_name, 'w').write(self.get_contents())
            self._save_file_name = file_name
            self._save_file_digest = self.digest
        except IOError:
            dialogue.main_window.alert_user(_('Save failed!'))
    def _save_text_to_file_acb(self, _action=None):
        self.save_text_to_file()
    def _save_text_as_acb(self, _action=None):
        fname = dialogue.main_window.ask_file_path(_('Enter file name'), existing=False, suggestion=self._save_file_name)
        if fname and os.path.exists(fname) and not utils.samefile(fname, self._save_file_name):
            if not utils.samefile(fname, ifce.SCM.get_default_commit_save_file()):
                if not dialogue.main_window.ask_ok_cancel(os.linesep.join([fname, _('\nFile exists. Overwrite?')])):
                    return
        self.save_text_to_file(file_name=fname)
    def load_text_fm_file(self, file_name=None, already_checked=False):
        if not already_checked and not self._ok_to_overwrite_summary():
            return
        if not file_name:
            if not self._save_file_name:
                return
            file_name = self._save_file_name
        try:
            self.set_contents(open(file_name, 'rb').read())
            self._save_file_name = file_name
            self._save_file_digest = self.digest
        except IOError:
            dialogue.main_window.alert_user(_('Load from file failed!'))
    def _load_text_fm_file_acb(self, _action=None):
        self.load_text_fm_file()
    def _load_text_from_acb(self, _action=None):
        if not self._ok_to_overwrite_summary():
            return
        fname = dialogue.main_window.ask_file_path(_('Enter file name'), existing=True)
        self.load_text_fm_file(file_name=fname, already_checked=True)
    def _insert_text_from_acb(self, _action=None):
        file_name = dialogue.main_window.ask_file_path(_('Enter file name'), existing=True)
        if file_name is not None:
            try:
                text = open(file_name, 'rb').read()
                self.bfr.insert_at_cursor(text)
                self.bfr.set_modified(True)
            except IOError:
                dialogue.main_window.alert_user(_('Insert at cursor from file failed!'))
    def get_auto_save(self):
        return self.save_toggle_action.get_active()
    def set_auto_save(self, active=True):
        self.save_toggle_action.set_active(active)
    def get_auto_save_interval(self):
        return self._save_interval
    def set_auto_save_inerval(self, interval):
        self._save_interval = interval
    def do_auto_save(self):
        if self.get_auto_save() and self._save_file_name:
            if not self._save_file_digest or self._save_file_digest != self.digest:
                self.save_text_to_file()
        return self.get_auto_save()
    def _toggle_auto_save_acb(self, _action=None):
        if self.get_auto_save():
            GObject.timeout_add(self._save_interval, self.do_auto_save)
    def finish_up(self, clear_save=False):
        #TODO: fix finish_up()
        if self.get_auto_save():
            self.set_auto_save(False)
            self.save_text_to_file()
        if clear_save and self._save_file_name:
            self.save_text_to_file("")

class DbMessageWidget(MessageWidget):
    UI_DESCR = ''
    def get_text_fm_db(self):
        raise NotImplentedError('Must be defined in child')
    def set_text_in_db(self, text):
        raise NotImplentedError('Must be defined in child')
    def __init__(self, save_file_name=None, auto_save=False, parent=None):
        MessageWidget.__init__(self, parent=parent)
        self.view.set_cursor_visible(True)
        self.view.set_editable(True)
        # Set up file stuff
        self._save_interval = 1000 # milliseconds
        self._save_file_name = save_file_name
        self._save_file_digest = None
        # Make some buttons
        self.save_button = gutils.creat_button_from_action(self.action_groups.get_action("text_edit_save"), use_underline=False)
        self.reload_button = gutils.creat_button_from_action(self.action_groups.get_action("text_edit_load"), use_underline=False)
    def populate_action_groups(self):
        MessageWidget.populate_action_groups(self)
        self.action_groups[actions.AC_DONT_CARE].add_actions(
            [
                ("text_edit_save", Gtk.STOCK_SAVE, _('_Save'), "",
                 _('Save summary to database'), self._save_text_acb),
                ("text_edit_load", Gtk.STOCK_REVERT_TO_SAVED, _('_Reload'), "",
                 _('Reload summary from database'), self._reload_text_acb),
            ])
    def _save_text_acb(self, *args):
        text = self.bfr.get_text(self.bfr.get_start_iter(), self.bfr.get_end_iter())
        result = self.set_text_in_db(text)
        if not result.is_ok:
            dialogue.main_window.report_any_problems(result)
        else:
            # get the tidied up version of the text
            self.load_text_fm_db(False)
    def load_text_fm_db(self, clear_digest=True):
        try:
            self.set_contents(self.get_text_fm_db())
            self.bfr.set_modified(False)
            if clear_digest:
                self._save_file_digest = None
        except CmdFailure as failure:
            dialogue.main_window.report_failure(failure)
    def _reload_text_acb(self, *args):
        if self._ok_to_overwrite_summary():
            self.load_text_fm_db()

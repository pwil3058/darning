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

import os
import time

from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import GObject

from .. import runext
from ..utils import singleton

from . import dialogue
from . import gutils
from . import textview
from . import terminal

@singleton
class ConsoleLog(textview.Widget):
    def __init__(self, width_in_chars=81, fdesc=None):
        textview.Widget.__init__(self, width_in_chars=width_in_chars, fdesc=fdesc)
        self.action_group = Gtk.ActionGroup("console_log")
        self.action_group.add_actions(
            [
                ("console_log_clear", Gtk.STOCK_CLEAR, _('_Clear'), None,
                 _('Clear the console log'), self.clear),
            ])
        self.view.connect("populate-popup", self._populate_popup_cb)
        self.view.set_editable(False)
        self.bold_tag = self.bfr.create_tag("BOLD", weight=Pango.Weight.BOLD, foreground="black", family="monospace")
        self.cmd_tag = self.bfr.create_tag("CMD", foreground="black", family="monospace")
        self.stdout_tag = self.bfr.create_tag("STDOUT", foreground="black", family="monospace")
        self.stderr_tag = self.bfr.create_tag("STDERR", foreground="#AA0000", family="monospace")
        self.stdin_tag = self.bfr.create_tag("STDIN", foreground="#00AA00", family="monospace")
        self._eobuf = self.bfr.create_mark("eobuf", self.bfr.get_end_iter(), False)
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.bfr.begin_user_action()
        self.bfr.set_text("")
        self._append_tagged_text("% ", self.bold_tag)
    def _populate_popup_cb(self, tview, menu):
        menu.prepend(self.action_group.get_action("console_log_clear").create_menu_item())
    def _append_tagged_text(self, text, tag):
        model_iter = self.bfr.get_end_iter()
        assert model_iter is not None, "ConsoleLogBuffer"
        self.bfr.insert_with_tags(model_iter, text, tag)
        self.view and self.view.scroll_to_mark(self._eobuf, 0.001, False, 0.0, 0.0)
    def clear(self, _action=None):
        self.bfr.end_user_action()
        self.bfr.set_text("")
        self._append_tagged_text("% ", self.bold_tag)
        self.bfr.begin_user_action()
        gutils.yield_to_pending_events()
    def start_cmd(self, cmd):
        self._append_tagged_text("%s: " % time.strftime("%Y-%m-%d %H:%M:%S"), self.bold_tag)
        self._append_tagged_text(cmd, self.cmd_tag)
        gutils.yield_to_pending_events()
    def append_stdin(self, msg):
        self._append_tagged_text(msg, self.stdin_tag)
        gutils.yield_to_pending_events()
    def append_stdout(self, msg):
        self._append_tagged_text(msg, self.stdout_tag)
        gutils.yield_to_pending_events()
    def append_stderr(self, msg):
        self._append_tagged_text(msg, self.stderr_tag)
        gutils.yield_to_pending_events()
    def end_cmd(self, result=None):
        if result:
            self.append_stdout(result.stdout)
            self.append_stderr(result.stderr)
        self._append_tagged_text("% ", self.bold_tag)
        gutils.yield_to_pending_events()
    def append_entry(self, msg):
        self._append_tagged_text("%s: " % time.strftime("%Y-%m-%d %H:%M:%S"), self.bold_tag)
        self._append_tagged_text(msg, self.cmd_tag)
        self._append_tagged_text("% ", self.bold_tag)
        gutils.yield_to_pending_events()

@singleton
class ConsoleLogWidget(Gtk.VBox, dialogue.BusyIndicatorUser):
    def __init__(self, busy_indicator=None):
        Gtk.VBox.__init__(self)
        dialogue.BusyIndicatorUser.__init__(self, busy_indicator)
        self._text_widget = ConsoleLog()
        if not terminal.AVAILABLE:
            hbox = Gtk.HBox()
            hbox.pack_start(Gtk.Label(_('Run: ')), expand=False, fill=True, padding=0)
            cmd_entry = gutils.EntryWithHistory()
            cmd_entry.connect("activate", self._cmd_entry_cb)
            hbox.pack_start(cmd_entry, expand=True, fill=True, padding=0)
            self.pack_start(hbox, expand=False, fill=True, padding=0)
        self.pack_start(self._text_widget, expand=True, fill=True, padding=0)
        self.show_all()
    def get_action(self, action_name):
        for action_group in self.ui_manager.get_action_groups():
            action = action_group.get_action(action_name)
            if action:
                return action
        return None
    def _clear_acb(self, _action):
        self._text_widget.clear()
    def start_cmd(self, cmd):
        return self._text_widget.start_cmd(cmd)
    def append_stdin(self, msg):
        return self._text_widget.append_stdin(msg)
    def append_stdout(self, msg):
        return self._text_widget.append_stdout(msg)
    def append_stderr(self, msg):
        return self._text_widget.append_stderr(msg)
    def end_cmd(self, result=None):
        return self._text_widget.end_cmd(result)
    def append_entry(self, msg):
        return self._text_widget.append_entry(msg)
    def _cmd_entry_cb(self, entry):
        from . import auto_update
        text = entry.get_text_and_clear_to_history()
        if not text:
            return
        with self.showing_busy():
            result = runext.run_cmd_in_console(self, text)
        dialogue.report_any_problems(result)
        auto_update.trigger_auto_update()

LOG = ConsoleLogWidget()

class ReportContext:
    class OutFile:
        def __init__(self):
            self.text = ''
        def write(self, text):
            self.text += text
            LOG.append_stdout(text)
    class ErrFile:
        def __init__(self):
            self.text = ''
        def write(self, text):
            self.text += text
            LOG.append_stderr(text)
    def __init__(self):
        self.stdout = self.OutFile()
        self.stderr = self.ErrFile()
    @property
    def message(self):
        return "\n".join([self.stdout.text, self.stderr.text])
    def reset(self):
        self.stdout.text = ''
        self.stderr.text = ''

RCTX = ReportContext()

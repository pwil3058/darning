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

import os, gtk, pango, time

from darning import utils
from darning import cmd_result

from darning.gui import dialogue
from darning.gui import gutils
from darning.gui import ws_event
from darning.gui import textview

class ConsoleLog(textview.Widget):
    def __init__(self, width_in_chars=81, fdesc=None):
        textview.Widget.__init__(self, width_in_chars=width_in_chars, fdesc=fdesc)
        self.bold_tag = self.bfr.create_tag("BOLD", weight=pango.WEIGHT_BOLD, foreground="black", family="monospace")
        self.cmd_tag = self.bfr.create_tag("CMD", foreground="black", family="monospace")
        self.stdout_tag = self.bfr.create_tag("STDOUT", foreground="black", family="monospace")
        self.stderr_tag = self.bfr.create_tag("STDERR", foreground="#AA0000", family="monospace")
        self.stdin_tag = self.bfr.create_tag("STDIN", foreground="#00AA00", family="monospace")
        self._eobuf = self.bfr.create_mark("eobuf", self.bfr.get_end_iter(), False)
    def _append_tagged_text(self, text, tag):
        model_iter = self.bfr.get_end_iter()
        assert model_iter is not None, "ConsoleLogBuffer"
        self.bfr.insert_with_tags(model_iter, text, tag)
        self.view and self.view.scroll_to_mark(self._eobuf, 0.001)
    def start_cmd(self, cmd):
        self._append_tagged_text("%s: " % time.strftime("%Y-%m-%d %H:%M:%S"), self.bold_tag)
        self._append_tagged_text(cmd + os.linesep, self.cmd_tag)
    def append_stdin(self, msg):
        self._append_tagged_text(msg, self.stdin_tag)
    def append_stdout(self, msg):
        self._append_tagged_text(msg, self.stdout_tag)
    def append_stderr(self, msg):
        self._append_tagged_text(msg, self.stderr_tag)
    def end_cmd(self):
        self._append_tagged_text("% ", self.bold_tag)
    def append_entry(self, msg):
        self._append_tagged_text("%s: " % time.strftime("%Y-%m-%d %H:%M:%S"), self.bold_tag)
        self._append_tagged_text(msg, self.cmd_tag)
        self._append_tagged_text(os.linesep + "% ", self.bold_tag)

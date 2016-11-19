### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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

"""
Library functions that are ony of interest GUI programs
"""

from .. import APP_NAME, CONFIG_DIR_PATH

from ..gtx import auto_update
from ..gtx.console import LOG
from .. import rctx

class ReportContext:
    class OutFile:
        def __init__(self):
            self.text = ""
        def write(self, text):
            self.text += text
            LOG.append_stdout(text)
    class ErrFile:
        def __init__(self):
            self.text = ""
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
        self.stdout.text = ""
        self.stderr.text = ""

RCTX = ReportContext()

rctx.reset(RCTX.stdout, RCTX.stderr)


# Import SCM back ends that we're interested in
from ..git.gui import git_gui_ifce
from ..hg.gui import hg_gui_ifce

# import PM backend  GUI interfaces here
from . import pm_ifce_darning

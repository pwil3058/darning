### Copyright (C) 2005-2016 Peter Williams <pwil3058@gmail.com>
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
import fnmatch
import collections
import urllib.parse

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

from ..wsm.gtx import dialogue
from ..wsm.gtx import gutils
from ..wsm.gtx import tlview
from ..wsm.gtx import table
from ..wsm.gtx import actions
from ..wsm.gtx import apath

from .. import CONFIG_DIR_PATH
from .. import utils

from . import ifce
from . import icons

SAVED_PGND_FILE_NAME = os.sep.join([CONFIG_DIR_PATH, "playgrounds"])

class PgndPathView(apath.AliasPathView):
    SAVED_FILE_NAME = SAVED_PGND_FILE_NAME

class PgndPathTable(apath.AliasPathTable):
    VIEW = PgndPathView

class PgndOpenDialog(apath.PathSelectDialog):
    PATH_TABLE = PgndPathTable
    def __init__(self, suggestion=None, parent=None):
        apath.PathSelectDialog.__init__(self, label=_("Playground/Directory"), suggestion=suggestion, parent=parent)

def ask_working_directory_path(parent=None):
    open_dialog = PgndOpenDialog(parent=parent)
    if open_dialog.run() != Gtk.ResponseType.OK:
        open_dialog.destroy()
        return None
    wd_path = open_dialog.get_path()
    open_dialog.destroy()
    return wd_path if wd_path else None


def generate_local_playground_menu():
    return PgndPathView.generate_alias_path_menu(_("Local Repositories"), lambda newtgnd: ifce.chdir(newtgnd))

def change_pgnd_cb(_widget, repo):
    with dialogue.main_window.showing_busy():
        result = ifce.chdir(repo)
    dialogue.main_window.report_any_problems(result)

def change_wd_acb(_arg):
    open_dialog = WorkspaceOpenDialog()
    if open_dialog.run() == Gtk.ResponseType.OK:
        newpg = open_dialog.get_path()
        if newpg:
            with open_dialog.showing_busy():
                result = ifce.chdir(newpg)
            open_dialog.report_any_problems(result)
    open_dialog.destroy()

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("config_menu", None, _("_Configuration")),
        ("config_change_wd", Gtk.STOCK_OPEN, _("_Open"), "",
         _("Change current working directory"), change_wd_acb),
    ])

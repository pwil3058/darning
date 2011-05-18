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
import os

from darning import utils

from darning.gui import dialogue
from darning.gui import ifce
from darning.gui import icons
from darning.gui import actions

class Darning(gtk.Window, dialogue.BusyIndicator, actions.AGandUIManager):
    def __init__(self, dir_specified=False):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_icon_from_file(icons.APP_ICON_FILE)
        self.connect("destroy", self._quit)
        self._update_title()
        dialogue.BusyIndicator.__init__(self)
        actions.AGandUIManager.__init__(self)
        dialogue.init(self)
        print ifce.in_valid_pgnd, ifce.in_valid_repo
    def _quit(self, _widget):
        gtk.main_quit()
    def _update_title(self):
        self.set_title("gdarn: %s" % utils.path_rel_home(os.getcwd()))

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
from darning.gui import console
from darning.gui import ifce
from darning.gui import icons
from darning.gui import actions
from darning.gui import ws_event
from darning.gui import patch_list

class Darning(gtk.Window, dialogue.BusyIndicator, actions.AGandUIManager):
    count = 0
    UI_DESCR = '''
    <ui>
        <menubar name="gdarn_left_menubar">
            <menu name="gdarn_pgnd" action="actions_playground_menu">
              <menuitem action="config_change_playground"/>
              <menuitem action="config_new_playground"/>
              <menuitem action="config_init_cwd"/>
              <menuitem action="actions_quit"/>
            </menu>
        </menubar>
        <menubar name="gdarn_right_menubar">
            <menu name="gdarn_config" action="config_menu">
              <menuitem action="config_allocate_editors"/>
            </menu>
        </menubar>
        <toolbar name="gdarn_patches_toolbar">
            <separator/>
            <toolitem name="Refresh" action="patch_list_refresh_top_patch"/>
            <toolitem name="Push" action="patch_list_push"/>
            <toolitem name="Pop" action="patch_list_pop"/>
            <separator/>
            <toolitem name="New" action="patch_list_new_patch"/>
        </toolbar>
    </ui>
    '''
    def __init__(self, dir_specified=False):
        assert Darning.count == 0
        Darning.count += 1
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_icon_from_file(icons.APP_ICON_FILE)
        self.connect("destroy", gtk.main_quit)
        self._update_title()
        dialogue.init(self)
        dialogue.BusyIndicator.__init__(self)
        actions.AGandUIManager.__init__(self)
        self.ui_manager.add_ui_from_string(Darning.UI_DESCR)
        vbox = gtk.VBox()
        self.add(vbox)
        mbar_box = gtk.HBox()
        mbar_box.pack_start(self.ui_manager.get_widget("/gdarn_left_menubar"), expand=False)
        mbar_box.pack_end(self.ui_manager.get_widget("/gdarn_right_menubar"), expand=False)
        vbox.pack_start(mbar_box, expand=False)
        vbox.pack_start(self.ui_manager.get_widget("/gdarn_patches_toolbar"), expand=False)
        vpane = gtk.VPaned()
        vbox.pack_start(vpane, expand=True)
        hpane = gtk.HPaned()
        vpane.add1(hpane)
        hpane.add1(gtk.Label('SCM view of files goes here'))
        hpane.add2(patch_list.List())
        if ifce.TERM:
            nbook = gtk.Notebook()
            nbook.append_page(console.LOG, gtk.Label("Transaction Log"))
            nbook.append_page(ifce.TERM, gtk.Label("Terminal"))
            vpane.add2(nbook)
        else:
            vpane.add2(console.LOG, gtk.Label("Transaction Log"))
        self.add_notification_cb(ws_event.CHANGE_WD, self._change_pgnd_ncb)
        self.show_all()
    def _update_title(self):
        self.set_title("gdarn: %s" % utils.path_rel_home(os.getcwd()))
    def _change_pgnd_ncb(self, _arg=None):
        self._update_title()

        

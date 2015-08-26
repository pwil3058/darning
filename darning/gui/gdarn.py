### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
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

import gtk
import os

from .. import utils

from . import gutils
from . import dialogue
from . import console
from . import ifce
from . import icons
from . import ws_actions
from . import ws_event
from . import patch_list
from . import file_tree_managed
from . import file_tree_cs
from . import terminal
from . import config

class Darning(gtk.Window, dialogue.BusyIndicator, ws_actions.AGandUIManager):
    count = 0
    UI_DESCR = '''
    <ui>
        <menubar name="gdarn_left_menubar">
            <menu name="gdarn_pgnd" action="actions_wd_menu">
              <menuitem action="config_change_playground"/>
              <menuitem action="pm_create_new_pgnd"/>
              <menuitem action="pm_init_cwd"/>
              <menuitem action='pm_edit_series_descr'/>
              <menuitem action="actions_quit"/>
            </menu>
        </menubar>
        <menubar name="gdarn_right_menubar">
            <menu name="gdarn_config" action="config_menu">
              <menuitem action="config_allocate_editors"/>
              <menuitem action='config_auto_update'/>
            </menu>
        </menubar>
        <toolbar name="gdarn_patches_toolbar">
           <separator/>
            <toolitem name="New" action="pm_new_patch"/>
            <toolitem name="Import" action="pm_import_patch"/>
            <toolitem name="Fold" action="pm_fold_external_patch"/>
           <separator/>
            <toolitem name="Refresh" action="pm_refresh_top_patch"/>
            <toolitem name="Push" action="pm_push"/>
            <toolitem name="Pop" action="pm_pop"/>
           <separator/>
            <toolitem name="Select" action="pm_select_guards"/>
           <separator/>
            <toolitem name="Diff" action="pm_top_patch_diff_pluses"/>
            <toolitem name="CombinedDiff" action="pm_combined_patch_diff_pluses"/>
           <separator/>
            <toolitem action="pm_add_new_file"/>
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
        ws_actions.AGandUIManager.__init__(self)
        self.ui_manager.add_ui_from_string(Darning.UI_DESCR)
        vbox = gtk.VBox()
        self.add(vbox)
        mbar_box = gtk.HBox()
        menubar = self.ui_manager.get_widget("/gdarn_left_menubar")
        menubar.insert(config.PlaygroundsMenu(), 1)
        mbar_box.pack_start(menubar, expand=True)
        mbar_box.pack_end(self.ui_manager.get_widget("/gdarn_right_menubar"), expand=False)
        vbox.pack_start(mbar_box, expand=False)
        toolbar = self.ui_manager.get_widget("/gdarn_patches_toolbar")
        toolbar.set_style(gtk.TOOLBAR_BOTH)
        vbox.pack_start(toolbar, expand=False)
        vpane = gtk.VPaned()
        vbox.pack_start(vpane, expand=True)
        hpane = gtk.HPaned()
        vpane.add1(hpane)
        stree = file_tree_managed.WSFilesWidget()
        stree.set_size_request(280, 280)
        hpane.add1(stree)
        phpane = gtk.HPaned()
        nbook = gtk.Notebook()
        nbook.set_size_request(280, 280)
        nbook.append_page(file_tree_cs.TopPatchFileTreeWidget(), gtk.Label(_('Top Patch Files')))
        nbook.append_page(file_tree_cs.CombinedPatchFileTreeWidget(), gtk.Label(_('Combined Patch Files')))
        phpane.add1(nbook)
        plist = patch_list.List()
        plist.set_size_request(280, 280)
        phpane.add2(plist)
        hpane.add2(phpane)
        if terminal.AVAILABLE:
            nbook = gtk.Notebook()
            nbook.append_page(console.LOG, gtk.Label(_('Transaction Log')))
            nbook.append_page(terminal.Terminal(), gtk.Label(_('Terminal')))
            vpane.add2(nbook)
        else:
            vpane.add2(console.LOG)
        self.add_notification_cb(ifce.E_CHANGE_WD, self._change_pgnd_ncb)
        self.show_all()
    def populate_action_groups(self):
        pass
    def _update_title(self):
        self.set_title("gdarn: %s" % utils.path_rel_home(os.getcwd()))
    def _change_pgnd_ncb(self, *args,**kwargs):
        self._update_title()

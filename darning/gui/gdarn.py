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

import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from aipoed import enotify

from aipoed.decorators import singleton

from aipoed.gui import gutils
from aipoed.gui import dialogue
from aipoed.gui import actions
from aipoed.gui import terminal
from aipoed.gui import console

from .. import utils

from . import ifce
from . import icons
from . import ws_actions
from . import patch_list
from . import file_tree_managed
from . import file_tree_cs
from . import config

@singleton
class Darning(dialogue.MainWindow, actions.CAGandUIManager, enotify.Listener, ws_actions.WSListenerMixin):
    UI_DESCR = '''
    <ui>
        <menubar name="gdarn_left_menubar">
            <menu name="gdarn_pgnd" action="actions_wd_menu">
              <menuitem action="pm_change_working_directory"/>
              <menuitem action="pm_create_new_pgnd"/>
              <menuitem action="pm_init_cwd"/>
              <menuitem action='pm_edit_series_descr'/>
              <menuitem action="actions_quit"/>
            </menu>
        </menubar>
        <menubar name="gdarn_right_menubar">
            <menu name="gdarn_config" action="config_menu">
              <menuitem action="allocate_xtnl_editors"/>
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
        dialogue.MainWindow.__init__(self, Gtk.WindowType.TOPLEVEL)
        self.set_icon_from_file(icons.APP_ICON_FILE)
        self.connect("destroy", Gtk.main_quit)
        self._update_title()
        actions.CAGandUIManager.__init__(self)
        enotify.Listener.__init__(self)
        ws_actions.WSListenerMixin.__init__(self)
        self.ui_manager.add_ui_from_string(Darning.UI_DESCR)
        vbox = Gtk.VBox()
        self.add(vbox)
        mbar_box = Gtk.HBox()
        menubar = self.ui_manager.get_widget("/gdarn_left_menubar")
        menubar.insert(config.generate_local_playground_menu(), 1)
        mbar_box.pack_start(menubar, expand=True, fill=True, padding=0)
        mbar_box.pack_end(self.ui_manager.get_widget("/gdarn_right_menubar"), expand=False, fill=True, padding=0)
        vbox.pack_start(mbar_box, expand=False, fill=True, padding=0)
        toolbar = self.ui_manager.get_widget("/gdarn_patches_toolbar")
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)
        vbox.pack_start(toolbar, expand=False, fill=True, padding=0)
        vpane = Gtk.VPaned()
        vbox.pack_start(vpane, expand=True, fill=True, padding=0)
        hpane = Gtk.HPaned()
        vpane.add1(hpane)
        stree = file_tree_managed.WSFilesWidget()
        stree.set_size_request(280, 280)
        hpane.add1(stree)
        phpane = Gtk.HPaned()
        nbook = Gtk.Notebook()
        nbook.set_size_request(280, 280)
        nbook.append_page(file_tree_cs.TopPatchFileTreeWidget(), Gtk.Label(_('Top Patch Files')))
        nbook.append_page(file_tree_cs.CombinedPatchFileTreeWidget(), Gtk.Label(_('Combined Patch Files')))
        phpane.add1(nbook)
        plist = patch_list.List()
        plist.set_size_request(280, 280)
        phpane.add2(plist)
        hpane.add2(phpane)
        if terminal.AVAILABLE:
            nbook = Gtk.Notebook()
            nbook.append_page(console.LOG, Gtk.Label(_('Transaction Log')))
            nbook.append_page(terminal.Terminal(), Gtk.Label(_('Terminal')))
            vpane.add2(nbook)
        else:
            vpane.add2(console.LOG)
        self.add_notification_cb(enotify.E_CHANGE_WD, self._change_pgnd_ncb)
        self.show_all()
    def populate_action_groups(self):
        pass
    def _update_title(self):
        self.set_title("gdarn: %s" % utils.path_rel_home(os.getcwd()))
    def _change_pgnd_ncb(self, *args,**kwargs):
        self._update_title()

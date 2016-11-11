# Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License only.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software; if not, write to:
#  The Free Software Foundation, Inc., 51 Franklin Street,
#  Fifth Floor, Boston, MA 02110-1301 USA

"""<DOCSTRING GOES HERE>"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"

import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ..wsm.bab import enotify
from ..wsm.bab import utils


from ..wsm.bab.decorators import singleton

from ..wsm.gtx import gutils
from ..wsm.gtx import dialogue
from ..wsm.gtx import actions
from ..wsm.gtx import recollect
from ..wsm.gtx import terminal
from ..wsm.gtx import console

from ..wsm.pm_gui import pm_wspce
from ..wsm.pm_gui import pm_actions
from ..wsm.pm_gui import pm_file_tree_cs
from ..wsm.pm_gui import pm_file_tree_pgnd
from ..wsm.pm_gui import pm_gui_ifce
from ..wsm.pm_gui import pm_patch_list

from ..wsm.scm_gui import scm_actions

from ..wsm.gtx import icons

recollect.define("main_window", "last_geometry", recollect.Defn(str, "900x600+100+100"))
recollect.define("main_window", "vpane_position", recollect.Defn(int, 270))
recollect.define("main_window", "hpane_position", recollect.Defn(int, 270))
recollect.define("main_window", "phpane_position", recollect.Defn(int, 330))

@singleton
class MainWindow(dialogue.MainWindow, actions.CAGandUIManager, enotify.Listener, scm_actions.WDListenerMixin, pm_actions.WDListenerMixin):
    UI_DESCR = '''
    <ui>
        <menubar name="gdarn_left_menubar">
            <menu name="gdarn_pgnd" action="actions_wd_menu">
              <menuitem action="pm_change_wd"/>
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
        </toolbar>
    </ui>
    '''
    def __init__(self, dir_specified=False):
        pm_gui_ifce.init()
        dialogue.MainWindow.__init__(self, Gtk.WindowType.TOPLEVEL)
        self.parse_geometry(recollect.get("main_window", "last_geometry"))
        self.set_icon_from_file(icons.APP_ICON_FILE)
        self.connect("destroy", Gtk.main_quit)
        self.connect("configure-event", self._configure_event_cb)
        self._update_title()
        actions.CAGandUIManager.__init__(self)
        enotify.Listener.__init__(self)
        scm_actions.WDListenerMixin.__init__(self)
        pm_actions.WDListenerMixin.__init__(self)
        self.ui_manager.add_ui_from_string(MainWindow.UI_DESCR)
        vbox = Gtk.VBox()
        self.add(vbox)
        mbar_box = Gtk.HBox()
        menubar = self.ui_manager.get_widget("/gdarn_left_menubar")
        menubar.insert(pm_wspce.generate_local_playground_menu(), 1)
        mbar_box.pack_start(menubar, expand=True, fill=True, padding=0)
        mbar_box.pack_end(self.ui_manager.get_widget("/gdarn_right_menubar"), expand=False, fill=True, padding=0)
        vbox.pack_start(mbar_box, expand=False, fill=True, padding=0)
        toolbar = self.ui_manager.get_widget("/gdarn_patches_toolbar")
        toolbar.set_style(Gtk.ToolbarStyle.BOTH)
        vbox.pack_start(toolbar, expand=False, fill=True, padding=0)
        vpane = Gtk.VPaned()
        vpane.set_position(recollect.get("main_window", "vpane_position"))
        vbox.pack_start(vpane, expand=True, fill=True, padding=0)
        hpane = Gtk.HPaned()
        hpane.set_position(recollect.get("main_window", "hpane_position"))
        vpane.add1(hpane)
        stree = pm_file_tree_pgnd.WSFilesWidget()
        hpane.add1(stree)
        phpane = Gtk.HPaned()
        phpane.set_position(recollect.get("main_window", "phpane_position"))
        vpane.connect("notify", self._paned_notify_cb, "vpane_position")
        hpane.connect("notify", self._paned_notify_cb, "hpane_position")
        phpane.connect("notify", self._paned_notify_cb, "phpane_position")
        nbook = Gtk.Notebook()
        nbook.append_page(pm_file_tree_cs.TopPatchFileTreeWidget(), Gtk.Label(_('Top Patch Files')))
        nbook.append_page(pm_file_tree_cs.CombinedPatchFileTreeWidget(), Gtk.Label(_('Combined Patch Files')))
        phpane.add1(nbook)
        plist = pm_patch_list.List()
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
    def _configure_event_cb(self, widget, event):
        recollect.set("main_window", "last_geometry", "{0.width}x{0.height}+{0.x}+{0.y}".format(event))
    def _paned_notify_cb(self, widget, parameter, oname=None):
        if parameter.name == "position":
            recollect.set("main_window", oname, str(widget.get_position()))

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("config_menu", None, _("Configuration")),
        ("actions_wd_menu", None, _('_Working Directory')),
        ("actions_quit", Gtk.STOCK_QUIT, _('_Quit'), "",
         _('Quit'), Gtk.main_quit),
    ])

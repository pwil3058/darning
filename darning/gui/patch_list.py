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

import collections
import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GObject

from ..wsm.bab import enotify

from ..wsm.gtx import dialogue
from ..wsm.gtx import gutils
from ..wsm.gtx import tlview
from ..wsm.gtx import actions
from ..wsm.gtx import table
from ..wsm.gtx import auto_update

from ..wsm import pm

from ..pm_ifce import PatchState

from .. import utils
from .. import scm_ifce
from .. import pm_ifce

from . import icons
from . import ifce
from . import ws_actions
from . import patch_view
from . import dooph_pm

from .dooph_pm import AC_POP_POSSIBLE, AC_PUSH_POSSIBLE

def patch_markup(patch_data, selected_guards):
    markup = patch_data.name
    for guard in patch_data.pos_guards:
        fmt_str = " <b>+{0}</b>" if guard in selected_guards else " +{0}"
        markup += fmt_str.format(guard)
    for guard in patch_data.neg_guards:
        fmt_str = " <b>-{0}</b>" if guard in selected_guards else " -{0}"
        markup += fmt_str.format(guard)
    if patch_data.state == PatchState.NOT_APPLIED:
        return "<span foreground=\"darkgrey\" style=\"italic\">" + markup + "</span>"
    else:
        return markup

STATUS_ICONS = {
    PatchState.NOT_APPLIED : None,
    PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
    PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
    PatchState.APPLIED_UNREFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
}

AC_APPLIED, AC_UNAPPLIED, AC_APPLIED_FLAG, AC_APPLIED_NOT_FLAG, AC_APPLIED_MASK = actions.ActionCondns.new_flags_and_mask(4)
AC_APPLIED_TOP = AC_APPLIED | AC_APPLIED_FLAG
AC_APPLIED_NOT_TOP = AC_APPLIED | AC_APPLIED_NOT_FLAG
AC_UNAPPLIED_BLOCKED = AC_UNAPPLIED | AC_APPLIED_FLAG
AC_UNAPPLIED_NOT_BLOCKED = AC_UNAPPLIED | AC_APPLIED_NOT_FLAG

def get_applied_condns(seln):
    model, model_iter = seln.get_selected()
    if model_iter is None:
        return actions.MaskedCondns(actions.AC_DONT_CARE, AC_APPLIED_MASK)
    patchname = model.get_patch_name(model_iter)
    if model.get_patch_is_applied(model_iter):
        cond = AC_APPLIED_TOP if ifce.PM.is_top_patch(patchname) else AC_APPLIED_NOT_TOP
    elif ifce.PM.is_blocked_by_guard(patchname):
        cond = AC_UNAPPLIED_BLOCKED
    else:
        cond = AC_UNAPPLIED_NOT_BLOCKED
    return actions.MaskedCondns(cond, AC_APPLIED_MASK)

class ListView(table.MapManagedTableView, auto_update.AutoUpdater):
    REPOPULATE_EVENTS = enotify.E_CHANGE_WD|pm.E_NEW_PM
    UPDATE_EVENTS = pm.E_PATCH_LIST_CHANGES|pm.E_PATCH_REFRESH
    PopUp = "/patches_popup"
    class MODEL(table.MapManagedTableView.MODEL):
        ROW = collections.namedtuple("ROW",    ["name", "icon", "markup"])
        TYPES = ROW(name=GObject.TYPE_STRING, icon=GObject.TYPE_STRING, markup=GObject.TYPE_STRING,)
        def get_patch_name(self, plist_iter):
            return self.get_value_named(plist_iter, "name")
        def get_patch_is_applied(self, plist_iter):
            return self.get_value_named(plist_iter, "icon") is not None
    SPECIFICATION = tlview.ViewSpec(
        properties={
            "enable-grid-lines" : False,
            "reorderable" : False,
            "rules_hint" : False,
            "headers-visible" : False,
        },
        selection_mode=Gtk.SelectionMode.SINGLE,
        columns=[
            tlview.ColumnSpec(
                title=_("Patch List"),
                properties={"expand": False, "resizable" : True},
                cells=[
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=Gtk.CellRendererPixbuf,
                            expand=False,
                            start=True,
                            properties={},
                        ),
                        cell_data_function_spec=None,
                        attributes = {"stock_id" : MODEL.col_index("icon")}
                    ),
                    tlview.CellSpec(
                        cell_renderer_spec=tlview.CellRendererSpec(
                            cell_renderer=Gtk.CellRendererText,
                            expand=False,
                            start=True,
                            properties={"editable" : False},
                        ),
                        cell_data_function_spec=None,
                        attributes = {"markup" : MODEL.col_index("markup")}
                    ),
                ],
            ),
        ]
    )
    UI_DESCR = \
    """
    <ui>
      <menubar name="patch_list_menubar">
        <menu name="patch_list_menu" action="menu_patch_list">
          <menuitem action="pm_push_all"/>
          <menuitem action="pm_pop_all"/>
          <menuitem action="pm_restore_patch"/>
          <menuitem action="pm_scm_absorb_applied_patches"/>
          <separator/>
          <menuitem action="pm_refresh_patch_list"/>
        </menu>
      </menubar>
      <popup name="patches_popup">
        <placeholder name="applied">
          <menuitem action="patch_list_pop_to"/>
          <menuitem action="patch_list_refresh_selected"/>
        </placeholder>
        <separator/>
        <placeholder name="applied_indifferent">
          <menuitem action="pm_edit_patch_descr"/>
          <menuitem action="patch_list_patch_view"/>
          <menuitem action="patch_list_export_patch"/>
          <menuitem action="pm_set_patch_guards"/>
          <menuitem action="patch_list_rename"/>
          <menuitem action="patch_list_duplicate"/>
        </placeholder>
        <separator/>
        <placeholder name="unapplied">
          <menuitem action="patch_list_remove"/>
          <menuitem action="patch_list_fold_selected"/>
          <menuitem action="patch_list_push_to"/>
        </placeholder>
      </popup>
    </ui>
    """
    def __init__(self, size_req=None):
        self.last_import_dir = None
        self._hash_data = None
        self._applied_count = 0
        table.MapManagedTableView.__init__(self, size_req=size_req)
        auto_update.AutoUpdater.__init__(self)
        self.get_selection().connect("changed", self._selection_changed_cb)
        self.add_notification_cb(self.REPOPULATE_EVENTS, self.repopulate_list)
        self.add_notification_cb(self.UPDATE_EVENTS, self.refresh_contents)
        self.register_auto_update_cb(self._auto_update_list_cb)
        self.repopulate_list()
    def populate_action_groups(self):
        self.action_groups[actions.AC_DONT_CARE].add_action(Gtk.Action("menu_patch_list", _("Patch _List"), None, None))
        self.action_groups[ws_actions.AC_IN_PM_PGND].add_actions(
            [
                ("pm_refresh_patch_list", Gtk.STOCK_REFRESH, _("Update Patch List"), None,
                 _("Refresh/update the patch list display"),
                 lambda _action=False: self.refresh_contents()
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | ws_actions.AC_IN_PM_PGND].add_actions(
            [
                ("pm_edit_patch_descr", Gtk.STOCK_EDIT, _("Description"), None,
                 _("Edit the selected patch's description"),
                 lambda _action=None: dooph_pm.PatchDescrEditDialog(self.get_selected_patch(), parent=None).show()
                ),
                ("patch_list_patch_view", icons.STOCK_DIFF, _("Details"), None,
                 _("View the selected patch's details"),
                 lambda _action=None: patch_view.Dialogue(self.get_selected_patch()).show()
                ),
                ("patch_list_export_patch", Gtk.STOCK_SAVE_AS, _("Export"), None,
                 _("Export the selected patch to a text file"),
                 lambda _action=None: dooph_pm.pm_do_export_named_patch(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | ws_actions.AC_IN_PM_PGND].add_actions(
            [
                ("pm_set_patch_guards", icons.STOCK_PATCH_GUARD, None, None,
                 _("Set guards on the selected patch"),
                 lambda _action=None: dooph_pm.pm_do_set_guards_on_patch(self.get_selected_patch())
                ),
                ("patch_list_rename", icons.STOCK_RENAME, _("Rename"), None,
                 _("Rename the selected patch"),
                 lambda _action=None: dooph_pm.pm_do_rename_patch(self.get_selected_patch())
                ),
                ("patch_list_duplicate", Gtk.STOCK_COPY, _("Duplicate"), None,
                 _("Duplicate the selected patch after the top applied patch"),
                 lambda _action=None: dooph_pm.pm_do_duplicate_patch(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | AC_PUSH_POSSIBLE | ws_actions.AC_IN_PM_PGND | AC_UNAPPLIED_NOT_BLOCKED].add_actions(
            [
                ("patch_list_push_to", icons.STOCK_PUSH_PATCH, _("Push To"), None,
                 _("Apply all unguarded unapplied patches up to the selected patch."),
                 lambda _action=None: dooph_pm.pm_do_push_to(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | ws_actions.AC_IN_PM_PGND | AC_UNAPPLIED].add_actions(
            [
                ("patch_list_remove", Gtk.STOCK_DELETE, _("Remove"), None,
                 _("Remove the selected patch from the series."),
                 lambda _action=None: dooph_pm.pm_do_remove_patch(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | AC_POP_POSSIBLE | ws_actions.AC_IN_PM_PGND | AC_APPLIED_NOT_TOP].add_actions(
            [
                ("patch_list_pop_to", icons.STOCK_POP_PATCH, _("Pop To"), None,
                 _("Apply all applied patches down to the selected patch."),
                 lambda _action=None: dooph_pm.pm_do_pop_to(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | AC_POP_POSSIBLE | ws_actions.AC_IN_PM_PGND | AC_APPLIED].add_actions(
            [
                ("patch_list_refresh_selected", icons.STOCK_PUSH_PATCH, _("Refresh"), None,
                 _("Refresh the selected patch."),
                 lambda _action=None: dooph_pm.pm_do_refresh_named_patch(self.get_selected_patch())
                ),
            ])
        self.action_groups[actions.AC_SELN_UNIQUE | AC_POP_POSSIBLE | ws_actions.AC_IN_PM_PGND | AC_UNAPPLIED].add_actions(
            [
                ("patch_list_fold_selected", icons.STOCK_FOLD_PATCH, _("Fold"), None,
                 _("Fold the selected patch into the top applied patch."),
                 lambda _action=None: dooph_pm.pm_do_fold_patch(self.get_selected_patch())
                ),
            ])
    def _selection_changed_cb(self, selection):
        # This callback is needed to process applied/unapplied state
        # self.action_groups' callback handles the other selection conditions
        self.action_groups.update_condns(get_applied_condns(selection))
    def get_selected_patch(self):
        store, store_iter = self.seln.get_selected()
        return None if store_iter is None else store.get_patch_name(store_iter)
    def _auto_update_list_cb(self, events_so_far, args):
        if (events_so_far & (self.REPOPULATE_EVENTS|self.UPDATE_EVENTS)):
            return 0
        napplied = ifce.PM.get_applied_patch_count()
        if napplied < self._applied_count:
            return pm.E_POP
        elif napplied > self._applied_count:
            return pm.E_PUSH
        elif napplied != 0 and not self._table_db.is_current:
            args["pld_reset_only"] = True
            return pm.E_PATCH_LIST_CHANGES
        return 0
    def _get_table_db(self):
        return ifce.PM.get_patch_list_data()
    def _fetch_contents(self, pld_reset_only=False, **kwargs):
        self.action_groups.update_condns(dooph_pm.get_pushable_condns())
        self._applied_count = 0
        for patch_data in table.MapManagedTableView._fetch_contents(self, pld_reset_only=pld_reset_only, **kwargs):
            icon = STATUS_ICONS[patch_data.state]
            markup = patch_markup(patch_data, self._table_db.selected_guards)
            if patch_data.state != PatchState.NOT_APPLIED:
                self._applied_count += 1
            yield [patch_data.name, icon, markup]
    def repopulate_list(self, **kwargs):
        with dialogue.main_window.showing_busy():
            self.set_contents()
            condns = get_applied_condns(self.seln)
            condns |= ws_actions.get_in_pm_pgnd_condns()
            self.action_groups.update_condns(condns)

class List(table.TableWidget):
    VIEW = ListView
    def __init__(self):
        table.TableWidget.__init__(self, scroll_bar=True, size_req=None)
        self.header.lhs.pack_start(self.view.ui_manager.get_widget("/patch_list_menubar"), expand=True, fill=True, padding=0)

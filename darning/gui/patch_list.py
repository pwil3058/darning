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
import gobject
import collections

from darning.patch_db import PatchState

from darning.gui import ifce
from darning.gui import actions
from darning.gui import ws_event
from darning.gui import table
from darning.gui import icons

class Condns(actions.Condns):
    _NEXTRACONDS = 3
    POP_POSSIBLE = actions.Condns.PMIC
    APPLIED, \
    UNAPPLIED, \
    PUSH_POSSIBLE = [2 ** (n + actions.Condns.NCONDS) for n in range(_NEXTRACONDS)]
    APPLIED_CONDNS = APPLIED | UNAPPLIED

class MaskedCondns(actions.MaskedCondns):
    @staticmethod
    def get_applied_condns(seln):
        model, model_iter = seln.get_selected()
        if model_iter is None:
            return actions.MaskedCondns(Condns.DONT_CARE, Condns.APPLIED_CONDNS)
        cond = Condns.APPLIED if model.get_patch_is_applied(model_iter) else Condns.UNAPPLIED
        return actions.MaskedCondns(cond, Condns.APPLIED_CONDNS)
    @staticmethod
    def get_pushable_condns():
        return actions.MaskedCondns(Condns.PUSH_POSSIBLE if ifce.PM.is_pushable() else 0, Condns.PUSH_POSSIBLE)

class List(table.MapManagedTable):
    class View(table.MapManagedTable.View):
        class Model(table.MapManagedTable.View.Model):
            Row = collections.namedtuple('Row',    ['name', 'icon', 'markup'])
            types = Row(name=gobject.TYPE_STRING, icon=gobject.TYPE_STRING, markup=gobject.TYPE_STRING,)
            def get_patch_name(self, plist_iter):
                return self.get_labelled_value(plist_iter, 'name')
            def get_patch_is_applied(self, plist_iter):
                return self.get_labelled_value(plist_iter, 'icon') is not None
        template = table.MapManagedTable.View.Template(
            properties={
                'enable-grid-lines' : False,
                'reorderable' : False,
                'rules_hint' : False,
                'headers-visible' : False,
            },
            selection_mode=gtk.SELECTION_SINGLE,
            columns=[
                table.MapManagedTable.View.Column(
                    title='Patch List',
                    properties={'expand': False, 'resizable' : True},
                    cells=[
                        table.MapManagedTable.View.Cell(
                            creator=table.MapManagedTable.View.CellCreator(
                                function=gtk.CellRendererPixbuf,
                                expand=False,
                                start=True
                            ),
                            properties={},
                            renderer=None,
                            attributes = {'stock_id' : Model.col_index('icon')}
                        ),
                        table.MapManagedTable.View.Cell(
                            creator=table.MapManagedTable.View.CellCreator(
                                function=gtk.CellRendererText,
                                expand=False,
                                start=True
                            ),
                            properties={'editable' : False},
                            renderer=None,
                            attributes = {'markup' : Model.col_index('markup')}
                        ),
                    ],
                ),
            ]
        )
    UI_DESCR = '''
    <ui>
      <menubar name="patch_list_menubar">
        <menu name="patch_list_menu" action="menu_patch_list">
        </menu>
      </menubar>
    </ui>
    '''
    status_icons = {
        PatchState.UNAPPLIED : None,
        PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
        PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
        PatchState.APPLIED_UNFEFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
    }
    @staticmethod
    def patch_markup(patch_data, selected_guards):
        markup = patch_data.name
        for guard in patch_data.pos_guards:
            fmt_str = ' <b>+{0}</b>' if guard in selected_guards else '+{0}'
            markup += fmt_str.format(guard)
        for guard in patch_data.neg_guards:
            fmt_str = ' <b>-{0}</b>' if guard in selected_guards else '-{0}'
            markup += fmt_str.format(guard)
        if patch_data.state == PatchState.UNAPPLIED:
            return '<span foreground="darkgrey" style="italic">' + markup + '</span>'
        else:
            return markup
    def __init__(self, busy_indicator=None):
        self.last_import_dir = None
        table.MapManagedTable.__init__(self, popup='/patches_popup',
                                       scroll_bar=True,
                                       busy_indicator=busy_indicator,
                                       size_req=None)
        self.add_conditional_action(Condns.DONT_CARE, gtk.Action("menu_patch_list", "Patch _List", None, None))
        self.ui_manager.add_ui_from_string(self.UI_DESCR)
        self.header.lhs.pack_start(self.ui_manager.get_widget('/patch_list_menubar'), expand=True, fill=True)
        self.seln.connect("changed", self._selection_changed_cb)
        self.add_notification_cb(ws_event.CHANGE_WD, self._repopulate_list_cb)
        self.add_notification_cb(ws_event.PATCH_CHANGES, self._update_list_cb)
        self.repopulate_list()
    def _selection_changed_cb(self, selection):
        self.set_sensitivity_for_condns(MaskedCondns.get_applied_condns(self.seln))
    def get_selected_patch(self):
        store, store_iter = self.seln.get_selected()
        return None if store_iter is None else store.get_patch_name(store_iter)
    def _update_list_cb(self, _arg=None):
        self.refresh_contents()
    def _fetch_contents(self):
        patch_data_list = ifce.PM.get_all_patches_data()
        selected = ifce.PM.get_selected_guards()
        contents = []
        for patch_data in patch_data_list:
            icon = self.status_icons[patch_data.state]
            markup = self.patch_markup(patch_data, selected)
            contents.append([patch_data.name, icon, markup])
        condns = MaskedCondns.get_pushable_condns()
        self.set_sensitivity_for_condns(condns)
        return contents
    def repopulate_list(self):
        self.set_contents()
        condns = MaskedCondns.get_applied_condns(self.seln)
        condns |= MaskedCondns.get_in_pgnd_condns()
        self.set_sensitivity_for_condns(condns)
    def _repopulate_list_cb(self, _arg=None):
        self.show_busy()
        self.repopulate_list()
        self.unshow_busy()

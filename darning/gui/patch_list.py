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
import os

from darning import utils
from darning import cmd_result
from darning.patch_db import PatchState

from darning.gui import ifce
from darning.gui import actions
from darning.gui import ws_event
from darning.gui import table
from darning.gui import icons
from darning.gui import dialogue
from darning.gui import text_edit

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
      <popup name="patches_popup">
        <placeholder name="applied">
        </placeholder>
        <separator/>
        <placeholder name="applied_indifferent">
          <menuitem action="pm_edit_patch_descr"/>
        </placeholder>
        <separator/>
        <placeholder name="unapplied">
        </placeholder>
      </popup>
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
        self.add_conditional_actions(Condns.SELN,
            [
                ("pm_edit_patch_descr", gtk.STOCK_EDIT, "Description", None,
                 "Edit the selected patch's description", self.do_edit_description),
            ])
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
    def do_edit_description(self, _action=None):
        patch = self.get_selected_patch()
        PatchDescrEditDialog(patch, parent=None).show()

class PatchDescrEditDialog(dialogue.Dialog):
    class Widget(text_edit.Widget):
        UI_DESCR = '''
            <ui>
              <menubar name="menubar">
                <menu name="ndd_menu" action="load_menu">
                  <separator/>
                  <menuitem action="text_edit_insert_from"/>
                </menu>
              </menubar>
              <toolbar name="toolbar">
                <toolitem action="text_edit_ack"/>
                <toolitem action="text_edit_sign_off"/>
                <toolitem action="text_edit_author"/>
              </toolbar>
            </ui>
        '''
        def __init__(self, patch):
            text_edit.Widget.__init__(self)
            self._patch = patch
            self.load_text_fm_db()
            self.action_group.add_actions(
                [
                    ("load_menu", None, "_File"),
                ])
        def get_text_fm_db(self):
            return ifce.PM.get_patch_description(self._patch)
        def set_text_in_db(self, text):
            return ifce.PM.do_set_patch_description(self._patch, text)
    def __init__(self, patch, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = 'Patch: {0} : {1} -- gdarn'.format(patch, utils.path_rel_home(os.getcwd()))
        dialogue.Dialog.__init__(self, title, parent, flags, None)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.edit_descr_widget = self.Widget(patch)
        hbox = gtk.HBox()
        menubar = self.edit_descr_widget.ui_manager.get_widget("/menubar")
        hbox.pack_start(menubar, fill=True, expand=False)
        toolbar = self.edit_descr_widget.ui_manager.get_widget("/toolbar")
        toolbar.set_style(gtk.TOOLBAR_BOTH)
        toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        hbox.pack_end(toolbar, fill=False, expand=False)
        hbox.show_all()
        self.vbox.pack_start(hbox, expand=False)
        self.vbox.pack_start(self.edit_descr_widget)
        self.set_focus_child(self.edit_descr_widget)
        self.action_area.pack_start(self.edit_descr_widget.reload_button)
        self.action_area.pack_start(self.edit_descr_widget.save_button)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._handle_response_cb)
        self.set_focus_child(self.edit_descr_widget.view)
        self.edit_descr_widget.show_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == gtk.RESPONSE_CLOSE:
            if self.edit_descr_widget.view.get_buffer().get_modified():
                qtn = '\n'.join(["Unsaved changes to summary will be lost.", "Close anyway?"])
                if dialogue.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class NewSeriesDescrDialog(dialogue.Dialog):
    class Widget(text_edit.Widget):
        UI_DESCR = '''
            <ui>
              <menubar name="menubar">
                <menu name="ndd_menu" action="load_menu">
                  <separator/>
                  <menuitem action="text_edit_insert_from"/>
                </menu>
              </menubar>
              <toolbar name="toolbar">
                <toolitem action="text_edit_ack"/>
                <toolitem action="text_edit_sign_off"/>
                <toolitem action="text_edit_author"/>
              </toolbar>
            </ui>
        '''
        def __init__(self):
            text_edit.Widget.__init__(self)
            self.action_group.add_actions(
                [
                    ("load_menu", None, "_File"),
                ])
    def __init__(self, parent=None):
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = 'Patch Series Description: %s -- gdarn' % utils.path_rel_home(os.getcwd())
        dialogue.Dialog.__init__(self, title, parent, flags,
                                 (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                  gtk.STOCK_OK, gtk.RESPONSE_OK))
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.edit_descr_widget = self.Widget()
        hbox = gtk.HBox()
        menubar = self.edit_descr_widget.ui_manager.get_widget("/menubar")
        hbox.pack_start(menubar, fill=True, expand=False)
        toolbar = self.edit_descr_widget.ui_manager.get_widget("/toolbar")
        toolbar.set_style(gtk.TOOLBAR_BOTH)
        toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
        hbox.pack_end(toolbar, fill=False, expand=False)
        hbox.show_all()
        self.vbox.pack_start(hbox, expand=False)
        self.vbox.pack_start(self.edit_descr_widget)
        self.set_focus_child(self.edit_descr_widget)
        self.edit_descr_widget.show_all()
    def get_descr(self):
        return self.edit_descr_widget.get_contents()

class NewPatchDescrDialog(NewSeriesDescrDialog):
    def __init__(self, parent=None):
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title('New Patch Description: %s -- gdarn' % utils.path_rel_home(os.getcwd()))
        self.hbox = gtk.HBox()
        self.hbox.pack_start(gtk.Label('New Patch Name:'), fill=False, expand=False)
        self.new_name_entry = gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.hbox.pack_start(self.new_name_entry)
        self.hbox.show_all()
        self.vbox.pack_start(self.hbox)
        self.vbox.reorder_child(self.hbox, 0)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()

def _update_class_indep_pushable_cb(_arg=None):
    condns = MaskedCondns.get_pushable_condns()
    actions.set_class_indep_sensitivity_for_condns(condns)

ws_event.add_notification_cb(ws_event.CHANGE_WD|ws_event.PATCH_CHANGES, _update_class_indep_pushable_cb)

def new_playground_acb(_arg):
    newpg = dialogue.ask_dir_name("Select/create playground ..")
    if newpg is not None:
        dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
        if dlg.run() == gtk.RESPONSE_OK:
            dlg.show_busy()
            result = ifce.new_playground(dlg.get_descr(), newpg)
            dlg.unshow_busy()
            dialogue.report_any_problems(result)
        dlg.destroy()

def init_cwd_acb(_arg):
    dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
    if dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.new_playground(dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
    dlg.destroy()

def new_patch_acb(_arg):
    dlg = NewPatchDescrDialog(parent=dialogue.main_window)
    while dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.do_create_new_patch(dlg.get_new_patch_name(), dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
        if not (result.eflags & cmd_result.SUGGEST_RENAME):
            break
    dlg.destroy()

def push_next_patch_acb(_arg):
    force = False
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_push_next_patch(force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
        if not force and result.eflags & cmd_result.SUGGEST_FORCE_OR_REFRESH != 0:
            resp = dialogue.ask_force_refresh_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                break
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                file_list = ifce.PM.get_filenames_in_next_patch()
                result = ifce.PM.do_refresh_overlapped_files(file_list)
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break

def pop_top_patch_acb(_arg):
    dialogue.show_busy()
    result = ifce.PM.do_pop_top_patch()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

def refresh_top_patch_acb(_arg):
    dialogue.show_busy()
    result = ifce.PM.do_refresh_patch()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

actions.add_class_indep_actions(actions.Condns.DONT_CARE,
    [
        ("config_new_playground", icons.STOCK_NEW_PLAYGROUND, "_New", "",
         "Create a new intitialized playground", new_playground_acb),
    ])

actions.add_class_indep_actions(actions.Condns.NOT_IN_PGND,
    [
        ("config_init_cwd", icons.STOCK_INIT, "_Initialize", "",
         "Create a patch series in the current directory", init_cwd_acb),
    ])

actions.add_class_indep_actions(Condns.IN_PGND,
    [
        ("patch_list_new_patch", icons.STOCK_NEW_PATCH, None, None,
         "Create a new patch", new_patch_acb),
    ])

actions.add_class_indep_actions(Condns.PUSH_POSSIBLE,
    [
        ("patch_list_push", icons.STOCK_PUSH_PATCH, "Push", None,
         "Apply the next unapplied patch", push_next_patch_acb),
    ])

actions.add_class_indep_actions(Condns.POP_POSSIBLE,
    [
        ("patch_list_pop", icons.STOCK_POP_PATCH, "Pop", None,
         "Pop the top applied patch", pop_top_patch_acb),
    ])

actions.add_class_indep_actions(Condns.PMIC,
    [
        ("patch_list_refresh_top_patch", icons.STOCK_REFRESH_PATCH, None, None,
         "Refresh the top patch", refresh_top_patch_acb),
    ])

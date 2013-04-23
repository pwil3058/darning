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
import gobject
import collections
import os

from darning import utils
from darning import cmd_result
from darning import patchlib
from darning.patch_db import PatchState

from darning.gui import ifce
from darning.gui import actions
from darning.gui import ws_event
from darning.gui import table
from darning.gui import icons
from darning.gui import dialogue
from darning.gui import text_edit
from darning.gui import textview
from darning.gui import gutils
from darning.gui import patch_view

class Condns(actions.Condns):
    _NEXTRACONDS = 6
    POP_POSSIBLE = actions.Condns.PMIC
    APPLIED, \
    UNAPPLIED, \
    APPLIED_FLAG, \
    APPLIED_NOT_FLAG, \
    PUSH_POSSIBLE, \
    ALL_APPLIED_REFRESHED = [2 ** (n + actions.Condns.NCONDS) for n in range(_NEXTRACONDS)]
    APPLIED_TOP = APPLIED | APPLIED_FLAG
    APPLIED_NOT_TOP = APPLIED | APPLIED_NOT_FLAG
    UNAPPLIED_BLOCKED = UNAPPLIED | APPLIED_FLAG
    UNAPPLIED_NOT_BLOCKED = UNAPPLIED | APPLIED_NOT_FLAG
    APPLIED_CONDNS = APPLIED | UNAPPLIED | APPLIED_FLAG | APPLIED_NOT_FLAG

class MaskedCondns(actions.MaskedCondns):
    @staticmethod
    def get_applied_condns(seln):
        model, model_iter = seln.get_selected()
        if model_iter is None:
            return actions.MaskedCondns(Condns.DONT_CARE, Condns.APPLIED_CONDNS)
        patchname = model.get_patch_name(model_iter)
        if model.get_patch_is_applied(model_iter):
            cond = Condns.APPLIED_TOP if ifce.PM.is_top_patch(patchname) else Condns.APPLIED_NOT_TOP
        elif ifce.PM.is_blocked_by_guard(patchname):
            cond = Condns.UNAPPLIED_BLOCKED
        else:
            cond = Condns.UNAPPLIED_NOT_BLOCKED
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
                    title=_('Patch List'),
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
          <menuitem action="patch_list_push_all"/>
          <menuitem action="patch_list_pop_all"/>
          <menuitem action="patch_list_restore_patch"/>
          <menuitem action="patch_list_scm_absorb_applied_patches"/>
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
    '''
    status_icons = {
        PatchState.UNAPPLIED : None,
        PatchState.APPLIED_REFRESHED : icons.STOCK_APPLIED,
        PatchState.APPLIED_NEEDS_REFRESH : icons.STOCK_APPLIED_NEEDS_REFRESH,
        PatchState.APPLIED_UNREFRESHABLE : icons.STOCK_APPLIED_UNREFRESHABLE,
    }
    @staticmethod
    def patch_markup(patch_data, selected_guards):
        markup = patch_data.name
        for guard in patch_data.pos_guards:
            fmt_str = ' <b>+{0}</b>' if guard in selected_guards else ' +{0}'
            markup += fmt_str.format(guard)
        for guard in patch_data.neg_guards:
            fmt_str = ' <b>-{0}</b>' if guard in selected_guards else ' -{0}'
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
        self.add_conditional_action(Condns.DONT_CARE, gtk.Action("menu_patch_list", _('Patch _List'), None, None))
        self.add_conditional_actions(Condns.IN_PGND,
            [
                ("pm_refresh_patch_list", gtk.STOCK_REFRESH, _('Update Patch List'), None,
                 _('Refresh/update the patch list display'), self._update_list_cb),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.IN_PGND,
            [
                ("pm_edit_patch_descr", gtk.STOCK_EDIT, _('Description'), None,
                 _('Edit the selected patch\'s description'), self.do_edit_description),
                ("patch_list_patch_view", icons.STOCK_DIFF, _('Details'), None,
                 _('View the selected patch\'s details'), self.do_view_selected_patch),
                ("patch_list_export_patch", gtk.STOCK_SAVE_AS, _('Export'), None,
                 _('Export the selected patch to a text file'), self.do_export),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.IN_PGND_MUTABLE,
            [
                ("pm_set_patch_guards", icons.STOCK_PATCH_GUARD, None, None,
                 _('Set guards on the selected patch'), self.do_set_guards),
                ("patch_list_rename", icons.STOCK_RENAME, _('Rename'), None,
                 _('Rename the selected patch'), self.do_rename),
                ("patch_list_duplicate", gtk.STOCK_COPY, _('Duplicate'), None,
                 _('Duplicate the selected patch after the top applied patch'), self.do_duplicate),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.PUSH_POSSIBLE | Condns.IN_PGND_MUTABLE | Condns.UNAPPLIED_NOT_BLOCKED,
            [
                ("patch_list_push_to", icons.STOCK_PUSH_PATCH, _('Push To'), None,
                 _('Apply all unguarded unapplied patches up to the selected patch.'), self.do_push_patches_to),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.IN_PGND_MUTABLE | Condns.UNAPPLIED,
            [
                ("patch_list_remove", gtk.STOCK_DELETE, _('Remove'), None,
                 _('Remove the selected patch from the series.'), self.do_remove),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.POP_POSSIBLE | Condns.IN_PGND_MUTABLE | Condns.APPLIED_NOT_TOP,
            [
                ("patch_list_pop_to", icons.STOCK_POP_PATCH, _('Pop To'), None,
                 _('Apply all applied patches down to the selected patch.'), self.do_pop_patches_to),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.POP_POSSIBLE | Condns.IN_PGND_MUTABLE | Condns.APPLIED,
            [
                ("patch_list_refresh_selected", icons.STOCK_PUSH_PATCH, _('Refresh'), None,
                 _('Refresh the selected patch.'), self.do_refresh_selected_patch_acb),
            ])
        self.add_conditional_actions(Condns.UNIQUE_SELN | Condns.POP_POSSIBLE | Condns.IN_PGND_MUTABLE | Condns.UNAPPLIED,
            [
                ("patch_list_fold_selected", icons.STOCK_FOLD_PATCH, _('Fold'), None,
                 _('Fold the selected patch into the top applied patch.'), self.do_fold_patch_acb),
            ])
        self.ui_manager.add_ui_from_string(self.UI_DESCR)
        self.header.lhs.pack_start(self.ui_manager.get_widget('/patch_list_menubar'), expand=True, fill=True)
        self.seln.connect("changed", self._selection_changed_cb)
        self.add_notification_cb(ws_event.CHANGE_WD, self._repopulate_list_cb)
        self.add_notification_cb(ws_event.PATCH_CHANGES|ws_event.AUTO_UPDATE, self._update_list_cb)
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
    def do_set_guards(self, _action=None):
        patch = self.get_selected_patch()
        cguards = ' '.join(ifce.PM.get_patch_guards(patch))
        dialog = dialogue.ReadTextDialog(_('Set Guards: {0}').format(patch), _('Guards:'), cguards)
        while True:
            response = dialog.run()
            if response == gtk.RESPONSE_OK:
                guards = dialog.entry.get_text()
                self.show_busy()
                result = ifce.PM.do_set_patch_guards(patch, guards)
                self.unshow_busy()
                dialogue.report_any_problems(result)
                if result.eflags & cmd_result.SUGGEST_EDIT:
                    continue
                dialog.destroy()
            else:
                dialog.destroy()
            break
    def do_push_patches_to(self, action=None):
        patchname = self.get_selected_patch()
        while ifce.PM.is_pushable() and not ifce.PM.is_top_patch(patchname):
            if not push_next_patch_acb(None):
                break
    def do_pop_patches_to(self, action=None):
        patchname = self.get_selected_patch()
        while ifce.PM.is_poppable() and not ifce.PM.is_top_patch(patchname):
            if not pop_top_patch_acb(None):
                break
    def do_remove(self, action=None):
        patchname = self.get_selected_patch()
        result = ifce.PM.do_remove_patch(patchname)
        dialogue.report_any_problems(result)
    def do_view_selected_patch(self, action=None):
        patchname = self.get_selected_patch()
        patch_view.Dialogue(patchname).show()
    def do_duplicate(self, action=None):
        patchname = self.get_selected_patch()
        description = ifce.PM.get_patch_description(patchname)
        dialog = DuplicatePatchDialog(patchname, description, parent=dialogue.main_window)
        refresh_tried = False
        while True:
            response = dialog.run()
            if response == gtk.RESPONSE_OK:
                as_patchname = dialog.get_new_patch_name()
                newdescription = dialog.get_descr()
                dialog.show_busy()
                result = ifce.PM.do_duplicate_patch(patchname, as_patchname, newdescription)
                dialog.unshow_busy()
                if not refresh_tried and result.eflags & cmd_result.SUGGEST_REFRESH != 0:
                    resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
                    if resp == gtk.RESPONSE_CANCEL:
                        break
                    elif resp == dialogue.Response.REFRESH:
                        refresh_tried = True
                        dialogue.show_busy()
                        result = ifce.PM.do_refresh_patch()
                        dialogue.unshow_busy()
                        dialogue.report_any_problems(result)
                    continue
                dialogue.report_any_problems(result)
                if result.eflags & cmd_result.SUGGEST_RENAME:
                    continue
            break
        dialog.destroy()
    def do_fold_patch_acb(self, action=None):
        patchname = self.get_selected_patch()
        refresh_tried = False
        force = False
        absorb = False
        while True:
            dialogue.show_busy()
            result = ifce.PM.do_fold_named_patch(patchname, absorb=absorb, force=force)
            dialogue.unshow_busy()
            if refresh_tried:
                result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
            if not (absorb or force) and result.eflags & cmd_result.SUGGEST_FORCE_ABSORB_OR_REFRESH != 0:
                resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
                if resp == gtk.RESPONSE_CANCEL:
                    break
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.ABSORB:
                    absorb = True
                elif resp == dialogue.Response.REFRESH:
                    refresh_tried = True
                    dialogue.show_busy()
                    patch_file_list = ifce.PM.get_filepaths_in_named_patch(patchname)
                    top_patch_file_list = ifce.PM.get_filepaths_in_top_patch(patch_file_list)
                    file_list = [filepath for filepath in patch_file_list if filepath not in top_patch_file_list]
                    result = ifce.PM.do_refresh_overlapped_files(file_list)
                    dialogue.unshow_busy()
                    dialogue.report_any_problems(result)
                continue
            dialogue.report_any_problems(result)
            break
    def do_export(self, action=None):
        patchname = self.get_selected_patch()
        do_export_named_patch(self, patchname)
    def do_refresh_selected_patch_acb(self, _arg):
        patchname = self.get_selected_patch()
        dialogue.show_busy()
        result = ifce.PM.do_refresh_patch(patchname)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
    def do_rename(self, _action=None):
        patchname = self.get_selected_patch()
        dialog = dialogue.ReadTextDialog("Rename Patch: %s" % patchname, "New Name:", patchname)
        while dialog.run() == gtk.RESPONSE_OK:
            new_name = dialog.entry.get_text()
            if patchname == new_name:
                break
            self.show_busy()
            result = ifce.PM.do_rename_patch(patchname, new_name)
            self.unshow_busy()
            dialogue.report_any_problems(result)
            if not (result.eflags & cmd_result.ERROR_SUGGEST_RENAME):
                break
        dialog.destroy()

def do_export_named_patch(parent, patchname, suggestion=None, busy_indicator=None):
    if not suggestion:
        suggestion = utils.convert_patchname_to_filename(patchname)
    if busy_indicator is None:
        busy_indicator = dialogue.main_window
    PROMPT = _('Export as ...')
    export_filename = dialogue.ask_file_name(PROMPT, suggestion=suggestion, existing=False)
    if export_filename is None:
        return
    force = False
    overwrite = False
    refresh_tried = False
    while True:
        busy_indicator.show_busy()
        result = ifce.PM.do_export_patch_as(patchname, export_filename, force=force, overwrite=overwrite)
        busy_indicator.unshow_busy()
        if refresh_tried:
            result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
        if result.eflags & cmd_result.SUGGEST_FORCE_OR_REFRESH != 0:
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                dialogue.show_busy()
                result = ifce.PM.do_refresh_patch()
                dialogue.unshow_busy()
                dialogue.report_any_problems(result)
            continue
        elif result.eflags & cmd_result.SUGGEST_RENAME != 0:
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            elif resp == dialogue.Response.RENAME:
                export_filename = dialogue.ask_file_name(PROMPT, suggestion=export_filename, existing=False)
                if export_filename is None:
                    return
            continue
        dialogue.report_any_problems(result)
        break

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
            self.view.set_editable(ifce.PM.is_writable())
            self._patch = patch
            self.load_text_fm_db()
            self.action_group.add_actions(
                [
                    ("load_menu", None, _('_File')),
                ])
        def get_text_fm_db(self):
            return ifce.PM.get_patch_description(self._patch)
        def set_text_in_db(self, text):
            return ifce.PM.do_set_patch_description(self._patch, text)
    def __init__(self, patch, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _('Patch: {0} : {1} -- gdarn').format(patch, utils.path_rel_home(os.getcwd()))
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
                qtn = '\n'.join([_('Unsaved changes to summary will be lost.'), _('Close anyway?')])
                if dialogue.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class SeriesDescrEditDialog(dialogue.Dialog):
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
            self.view.set_editable(ifce.PM.is_writable())
            self.load_text_fm_db()
            self.action_group.add_actions(
                [
                    ("load_menu", None, _('_File')),
                ])
        def get_text_fm_db(self):
            return ifce.PM.get_series_description()
        def set_text_in_db(self, text):
            return ifce.PM.do_set_series_description(text)
    def __init__(self, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _('Series Description: {0} -- gdarn').format(utils.path_rel_home(os.getcwd()))
        dialogue.Dialog.__init__(self, title, parent, flags, None)
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
        self.action_area.pack_start(self.edit_descr_widget.reload_button)
        self.action_area.pack_start(self.edit_descr_widget.save_button)
        self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        self.connect("response", self._handle_response_cb)
        self.set_focus_child(self.edit_descr_widget.view)
        self.edit_descr_widget.show_all()
    def _handle_response_cb(self, dialog, response_id):
        if response_id == gtk.RESPONSE_CLOSE:
            if self.edit_descr_widget.view.get_buffer().get_modified():
                qtn = '\n'.join([_('Unsaved changes to summary will be lost.'), _('Close anyway?')])
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
                    ("load_menu", None, _('_File')),
                ])
    def __init__(self, parent=None):
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _('Patch Series Description: %s -- gdarn') % utils.path_rel_home(os.getcwd())
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

class NewPatchDialog(NewSeriesDescrDialog):
    def __init__(self, parent=None):
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title(_('New Patch: {0} -- gdarn').format(utils.path_rel_home(os.getcwd())))
        self.hbox = gtk.HBox()
        self.hbox.pack_start(gtk.Label(_('New Patch Name:')), fill=False, expand=False)
        self.new_name_entry = gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.hbox.pack_start(self.new_name_entry)
        self.hbox.show_all()
        self.vbox.pack_start(self.hbox)
        self.vbox.reorder_child(self.hbox, 0)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()

class DuplicatePatchDialog(NewSeriesDescrDialog):
    def __init__(self, patchname, olddescr, parent=None):
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title(_('Duplicate Patch: {0}: {1} -- gdarn').format(patchname, utils.path_rel_home(os.getcwd())))
        self.hbox = gtk.HBox()
        self.hbox.pack_start(gtk.Label(_('Duplicate Patch Name:')), fill=False, expand=False)
        self.new_name_entry = gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.new_name_entry.set_text(patchname + '.duplicate')
        self.hbox.pack_start(self.new_name_entry)
        self.edit_descr_widget.set_contents(olddescr)
        self.hbox.show_all()
        self.vbox.pack_start(self.hbox)
        self.vbox.reorder_child(self.hbox, 0)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()

class ImportPatchDialog(dialogue.Dialog):
    def __init__(self, epatch, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _('Import Patch: {0} : {1} -- gdarn').format(epatch.source_name, utils.path_rel_home(os.getcwd()))
        dialogue.Dialog.__init__(self, title, parent, flags, None)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        self.epatch = epatch
        #
        patch_file_name = os.path.basename(epatch.source_name)
        self.namebox = gtk.HBox()
        self.namebox.pack_start(gtk.Label(_("As Patch:")), expand=False)
        self.as_name = gutils.MutableComboBoxEntry()
        self.as_name.child.set_width_chars(32)
        self.as_name.set_text(patch_file_name)
        self.namebox.pack_start(self.as_name, expand=True, fill=True)
        self.vbox.pack_start(self.namebox, expand=False, fill=False)
        #
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_("Files: Strip Level:")), expand=False)
        est_strip_level = self.epatch.estimate_strip_level()
        self.strip_level_buttons = [gtk.RadioButton(group=None, label='0')]
        self.strip_level_buttons.append(gtk.RadioButton(group=self.strip_level_buttons[0], label='1'))
        for strip_level_button in self.strip_level_buttons:
            strip_level_button.connect("toggled", self._strip_level_toggle_cb)
            hbox.pack_start(strip_level_button, expand=False, fill=False)
            strip_level_button.set_active(False)
        self.vbox.pack_start(hbox, expand=False, fill=False)
        #
        self.file_list_widget = textview.Widget()
        self.strip_level_buttons[1 if est_strip_level is None else est_strip_level].set_active(True)
        self.update_file_list()
        self.vbox.pack_start(self.file_list_widget, expand=True, fill=True)
        self.show_all()
        self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
        self.set_focus_child(self.as_name)
    def get_strip_level(self):
        for strip_level in [0, 1]:
            if self.strip_level_buttons[strip_level].get_active():
                return strip_level
        return None
    def get_as_name(self):
        return self.as_name.get_text()
    def update_file_list(self):
        strip_level = self.get_strip_level()
        try:
            filepaths = self.epatch.get_file_paths(strip_level)
            self.file_list_widget.set_contents('\n'.join(filepaths))
        except:
            if strip_level == 0:
                return
            self.strip_level_buttons[0].set_active(True)
    def _strip_level_toggle_cb(self, _widget, _arg=None):
        self.update_file_list()

class FoldPatchDialog(ImportPatchDialog):
    def __init__(self, epatch, parent=None):
        ImportPatchDialog.__init__(self, epatch, parent)
        self.set_title( _('Fold Patch: {0} : {1} -- gdarn').format(epatch.source_name, utils.path_rel_home(os.getcwd())))
        self.namebox.hide()

class RestorePatchDialog(dialogue.Dialog):
    _KEYVAL_ESCAPE = gtk.gdk.keyval_from_name('Escape')
    class Table(table.Table):
        class View(table.Table.View):
            class Model(table.Table.View.Model):
                Row = collections.namedtuple('Row', ['PatchName'])
                types = Row(PatchName=gobject.TYPE_STRING)
            template = table.Table.View.Template(
                properties={
                    'enable-grid-lines' : False,
                    'reorderable' : False,
                    'rules_hint' : False,
                    'headers-visible' : False,
                },
                selection_mode=gtk.SELECTION_SINGLE,
                columns=[
                    table.Table.View.Column(
                        title=_('Patch Name'),
                        properties={'expand': False, 'resizable' : True},
                        cells=[
                            table.Table.View.Cell(
                                creator=table.Table.View.CellCreator(
                                    function=gtk.CellRendererText,
                                    expand=False,
                                    start=True
                                ),
                                properties={'editable' : False},
                                renderer=None,
                                attributes = {'text' : Model.col_index('PatchName')}
                            ),
                        ],
                    ),
                ]
            )
        def __init__(self):
            table.Table.__init__(self, size_req=(480, 160))
            self.connect("key_press_event", self._key_press_cb)
            self.connect('button_press_event', self._handle_button_press_cb)
            self.set_contents()
        def get_selected_patch(self):
            data = self.get_selected_data_by_label(['PatchName'])
            if not data:
                return False
            return data[0]
        def _handle_button_press_cb(self, widget, event):
            if event.type == gtk.gdk.BUTTON_PRESS:
                if event.button == 2:
                    self.seln.unselect_all()
                    return True
            return False
        def _key_press_cb(self, widget, event):
            if event.keyval == _KEYVAL_ESCAPE:
                self.seln.unselect_all()
                return True
            return False
        @staticmethod
        def _fetch_contents():
            return [[name] for name in ifce.PM.get_kept_patch_names()]
    def __init__(self, parent):
        dialogue.Dialog.__init__(self, title=_('gdarn: Restore Patch'), parent=parent,
                                 flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
                                 buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                          gtk.STOCK_OK, gtk.RESPONSE_OK)
                                )
        self.kept_patch_table = self.Table()
        self.vbox.pack_start(self.kept_patch_table)
        #
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_("Restore Patch:")), expand=False)
        self.rpatch_name = gtk.Entry()
        self.rpatch_name.set_editable(False)
        self.rpatch_name.set_width_chars(32)
        hbox.pack_start(self.rpatch_name, expand=True, fill=True)
        self.vbox.pack_start(hbox, expand=False, fill=False)
        #
        hbox = gtk.HBox()
        hbox.pack_start(gtk.Label(_("As Patch:")), expand=False)
        self.as_name = gutils.MutableComboBoxEntry()
        self.as_name.child.set_width_chars(32)
        self.as_name.child.connect("activate", self._as_name_cb)
        hbox.pack_start(self.as_name, expand=True, fill=True)
        self.vbox.pack_start(hbox, expand=False, fill=False)
        #
        self.show_all()
        self.kept_patch_table.seln.unselect_all()
        self.kept_patch_table.seln.connect("changed", self._selection_cb)
    def _selection_cb(self, _selection=None):
        rpatch = self.kept_patch_table.get_selected_patch()
        if rpatch:
            self.rpatch_name.set_text(rpatch[0])
    def _as_name_cb(self, entry=None):
        self.response(gtk.RESPONSE_OK)
    def get_restore_patch_name(self):
        return self.rpatch_name.get_text()
    def get_as_name(self):
        return self.as_name.get_text()

def _update_class_indep_pushable_cb(_arg=None):
    condns = MaskedCondns.get_pushable_condns()
    actions.set_class_indep_sensitivity_for_condns(condns)

ws_event.add_notification_cb(ws_event.CHANGE_WD|ws_event.PATCH_CHANGES, _update_class_indep_pushable_cb)

def _update_class_indep_absorbable_cb(_arg=None):
    condns = actions.MaskedCondns(Condns.ALL_APPLIED_REFRESHED if ifce.PM.all_applied_patches_refreshed() else 0, Condns.ALL_APPLIED_REFRESHED)
    actions.set_class_indep_sensitivity_for_condns(condns)

ws_event.add_notification_cb(ws_event.CHANGE_WD|ws_event.FILE_CHANGES|ws_event.PATCH_CHANGES|ws_event.AUTO_UPDATE, _update_class_indep_absorbable_cb)

def new_playground_acb(_arg):
    newpg = dialogue.ask_dir_name(_('Select/create playground ..'))
    if newpg is not None:
        dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
        if dlg.run() == gtk.RESPONSE_OK:
            dlg.show_busy()
            result = ifce.new_playground(dlg.get_descr(), newpg)
            dlg.unshow_busy()
            dialogue.report_any_problems(result)
        dlg.destroy()

def edit_series_description_acb(_arg):
    SeriesDescrEditDialog(parent=dialogue.main_window).show()

def init_cwd_acb(_arg):
    dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
    if dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.new_playground(dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
    dlg.destroy()

def new_patch_acb(_arg):
    dlg = NewPatchDialog(parent=dialogue.main_window)
    while dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.do_create_new_patch(dlg.get_new_patch_name(), dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
        if not (result.eflags & cmd_result.SUGGEST_RENAME):
            break
    dlg.destroy()

def restore_patch_acb(_arg):
    dlg = RestorePatchDialog(parent=dialogue.main_window)
    while dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.do_restore_patch(dlg.get_restore_patch_name(), dlg.get_as_name())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
        if not (result.eflags & cmd_result.SUGGEST_RENAME):
            break
    dlg.destroy()

def import_patch_acb(_arg):
    patch_file = dialogue.ask_file_name(_('Select patch file to be imported'))
    if patch_file is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file)
    except patchlib.ParseError as edata:
        result = cmd_result.Result(cmd_result.ERROR, '{0}: {1}: {2}\n'.format(patch_file, edata.lineno, edata.message))
        dialogue.report_any_problems(result)
        return
    overwrite = False
    dlg = ImportPatchDialog(epatch, parent=dialogue.main_window)
    resp = dlg.run()
    while resp != gtk.RESPONSE_CANCEL:
        epatch.set_strip_level(dlg.get_strip_level())
        dlg.show_busy()
        result = ifce.PM.do_import_patch(epatch, dlg.get_as_name(), overwrite=overwrite)
        dlg.unshow_busy()
        if not overwrite and result.eflags & cmd_result.SUGGEST_FORCE != 0:
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                break
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            else:
                resp = dlg.run()
            continue
        dialogue.report_any_problems(result)
        if result.eflags & cmd_result.SUGGEST_RENAME != 0:
            resp = dlg.run()
        else:
            break
    dlg.destroy()

def fold_patch_acb(_arg):
    patch_file = dialogue.ask_file_name(_('Select patch file to be folded'))
    if patch_file is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file)
    except patchlib.ParseError as edata:
        result = cmd_result.Result(cmd_result.ERROR, '{0}: {1}: {2}\n'.format(patch_file, edata.lineno, edata.message))
        dialogue.report_any_problems(result)
        return
    force = False
    absorb = False
    refresh_tried = False
    dlg = FoldPatchDialog(epatch, parent=dialogue.main_window)
    resp = dlg.run()
    while resp != gtk.RESPONSE_CANCEL:
        epatch.set_strip_level(dlg.get_strip_level())
        dlg.show_busy()
        result = ifce.PM.do_fold_epatch(epatch, absorb=absorb, force=force)
        dlg.unshow_busy()
        if refresh_tried:
            result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
        if not (absorb or force) and result.eflags & cmd_result.SUGGEST_FORCE_ABSORB_OR_REFRESH != 0:
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                break
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                dialogue.show_busy()
                top_patch_file_list = ifce.PM.get_filepaths_in_top_patch()
                file_list = [filepath for filepath in epatch.get_file_paths(epatch.num_strip_levels) if filepath not in top_patch_file_list]
                result = ifce.PM.do_refresh_overlapped_files(file_list)
                dialogue.unshow_busy()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break
    dlg.destroy()

def push_next_patch_acb(_arg):
    force = False
    absorb = True
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_push_next_patch(absorb=absorb, force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = cmd_result.turn_off_flags(result, cmd_result.SUGGEST_REFRESH)
        if not (absorb or force) and result.eflags & cmd_result.SUGGEST_FORCE_ABSORB_OR_REFRESH != 0:
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return False
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                dialogue.show_busy()
                file_list = ifce.PM.get_filepaths_in_next_patch()
                result = ifce.PM.do_refresh_overlapped_files(file_list)
                dialogue.unshow_busy()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break
    return cmd_result.is_ok(result)

def pop_top_patch_acb(_arg):
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_pop_top_patch()
        dialogue.unshow_busy()
        if not refresh_tried and result.eflags & cmd_result.SUGGEST_REFRESH != 0:
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return False
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                dialogue.show_busy()
                result = ifce.PM.do_refresh_patch()
                dialogue.unshow_busy()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break
    return cmd_result.is_ok(result)

def pop_all_patches_acb(_arg=None):
    while ifce.PM.is_poppable():
        if not pop_top_patch_acb(None):
            break

def push_all_patches_acb(_arg=None):
    while ifce.PM.is_pushable():
        if not push_next_patch_acb(None):
            break

def refresh_top_patch_acb(_arg):
    dialogue.show_busy()
    result = ifce.PM.do_refresh_patch()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

def select_guards_acb(_arg):
    cselected_guards = ' '.join(ifce.PM.get_selected_guards())
    dialog = dialogue.ReadTextDialog(_('Select Guards: {0}').format(os.getcwd()), _('Guards:'), cselected_guards)
    while True:
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            selected_guards = dialog.entry.get_text()
            dialogue.show_busy()
            result = ifce.PM.do_select_guards(selected_guards)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
            if result.eflags & cmd_result.SUGGEST_EDIT:
                continue
            dialog.destroy()
        else:
            dialog.destroy()
        break

def scm_absorb_applied_patches_acb(_arg):
    dialogue.show_busy()
    result = ifce.PM.do_scm_absorb_applied_patches()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)
    return cmd_result.is_ok(result)

actions.add_class_indep_actions(actions.Condns.DONT_CARE,
    [
        ("config_new_playground", icons.STOCK_NEW_PLAYGROUND, _('_New'), "",
         _('Create a new intitialized playground'), new_playground_acb),
    ])

actions.add_class_indep_actions(actions.Condns.NOT_IN_PGND,
    [
        ("config_init_cwd", icons.STOCK_INIT, _('_Initialize'), "",
         _('Create a patch series in the current directory'), init_cwd_acb),
    ])

actions.add_class_indep_actions(Condns.IN_PGND_MUTABLE,
    [
        ("patch_list_new_patch", icons.STOCK_NEW_PATCH, None, None,
         _('Create a new patch'), new_patch_acb),
        ("patch_list_restore_patch", icons.STOCK_IMPORT_PATCH, _('Restore Patch'), None,
         _('Restore a previously removed patch behind the top applied patch'), restore_patch_acb),
        ("patch_list_import_patch", icons.STOCK_IMPORT_PATCH, None, None,
         _('Import an external patch behind the top applied patch'), import_patch_acb),
        ("patch_list_select_guards", icons.STOCK_PATCH_GUARD_SELECT, None, None,
         _('Select which guards are in force'), select_guards_acb),
    ])

actions.add_class_indep_actions(Condns.IN_PGND,
    [
        ("patch_list_edit_series_descr", gtk.STOCK_EDIT, _('Description'), None,
         _('Edit the series\' description'), edit_series_description_acb),
    ])

actions.add_class_indep_actions(Condns.PUSH_POSSIBLE | Condns.IN_PGND_MUTABLE,
    [
        ("patch_list_push", icons.STOCK_PUSH_PATCH, _('Push'), None,
         _('Apply the next unapplied patch'), push_next_patch_acb),
        ("patch_list_push_all", icons.STOCK_PUSH_PATCH, _('Push All'), None,
         _('Apply all unguarded unapplied patches.'), push_all_patches_acb),
    ])

actions.add_class_indep_actions(Condns.POP_POSSIBLE | Condns.IN_PGND_MUTABLE,
    [
        ("patch_list_fold_external_patch", icons.STOCK_FOLD_PATCH, None, None,
         _('Fold an external patch into the top applied patch'), fold_patch_acb),
        ("patch_list_pop", icons.STOCK_POP_PATCH, _('Pop'), None,
         _('Pop the top applied patch'), pop_top_patch_acb),
        ("patch_list_pop_all", icons.STOCK_POP_PATCH, _('Pop All'), None,
         _('Pop all applied patches'), pop_all_patches_acb),
    ])

actions.add_class_indep_actions(Condns.PMIC | Condns.IN_PGND_MUTABLE,
    [
        ("patch_list_refresh_top_patch", icons.STOCK_REFRESH_PATCH, None, None,
         _('Refresh the top patch'), refresh_top_patch_acb),
    ])

actions.add_class_indep_actions(Condns.ALL_APPLIED_REFRESHED | Condns.IN_REPO | Condns.IN_PGND_MUTABLE,
    [
        ("patch_list_scm_absorb_applied_patches", icons.STOCK_FINISH_PATCH, _('Absorb All'), None,
         _('Absorb all applied patches into underlying SCM repository'), scm_absorb_applied_patches_acb),
    ])

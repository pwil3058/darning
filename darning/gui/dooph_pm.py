### Copyright (C) 2015 Peter Williams <pwil3058@gmail.com>
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
import collections

import gtk
import gobject


from .. import utils
from .. import pm_ifce
from .. import scm_ifce

from . import ifce
from . import dialogue
from . import dooph
from . import actions
from . import ws_actions
from . import ws_event
from . import icons
from . import text_edit
from . import recollect
from . import tlview
from . import table

AC_POP_POSSIBLE = ws_actions.AC_PMIC
AC_PUSH_POSSIBLE, AC_PUSH_POSSIBLE_MASK = actions.ActionCondns.new_flags_and_mask(1)
AC_ALL_APPLIED_REFRESHED, AC_ALL_APPLIED_REFRESHED_MASK = actions.ActionCondns.new_flags_and_mask(1)

def get_pushable_condns():
    return actions.MaskedCondns(AC_PUSH_POSSIBLE if ifce.PM.is_pushable() else 0, AC_PUSH_POSSIBLE)

def _update_class_indep_pushable_cb(**kwargs):
    actions.CLASS_INDEP_AGS.update_condns(get_pushable_condns())

ws_event.add_notification_cb(ifce.E_CHANGE_WD|pm_ifce.E_PATCH_LIST_CHANGES, _update_class_indep_pushable_cb)

def _update_class_indep_absorbable_cb(**kwargs):
    condns = actions.MaskedCondns(AC_ALL_APPLIED_REFRESHED if ifce.PM.all_applied_patches_refreshed() else 0, AC_ALL_APPLIED_REFRESHED)
    actions.CLASS_INDEP_AGS.update_condns(condns)

ws_event.add_notification_cb(ifce.E_CHANGE_WD|scm_ifce.E_FILE_CHANGES|pm_ifce.E_FILE_CHANGES|pm_ifce.E_PATCH_LIST_CHANGES, _update_class_indep_absorbable_cb)

def pm_initialize_curdir():
    dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
    if dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.new_playground(dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
    dlg.destroy()

def pm_do_create_new_pgnd():
    newpg = dialogue.ask_dir_name(_("Select/create playground .."), existing=False, suggestion=".")
    if newpg is not None:
        dlg = NewSeriesDescrDialog(parent=dialogue.main_window)
        if dlg.run() == gtk.RESPONSE_OK:
            dlg.show_busy()
            result = ifce.PM.new_playground(dlg.get_descr(), newpg)
            dlg.unshow_busy()
            dialogue.report_any_problems(result)
        dlg.destroy()

def pm_delete_files(file_paths):
    if len(file_paths) == 0:
        return
    dialogue.show_busy()
    result = ifce.PM.do_delete_files_in_top_patch(file_paths)
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)
    return result

def pm_add_files(file_paths):
    do_op = lambda absorb=False, force=False : ifce.PM.do_add_files_to_top_patch(file_paths, absorb=absorb, force=force)
    refresh_op = lambda : ifce.PM.do_refresh_overlapped_files(file_paths)
    result = dooph.do_force_refresh_or_absorb(do_op, refresh_op)
    dialogue.report_any_problems(result)
    return result

def pm_copy_files(file_paths):
    destn = dooph.ask_destination(file_paths)
    if not destn:
        return
    do_op = lambda destn, overwrite=False : ifce.PM.do_copy_files(file_paths, destn, overwrite=overwrite)
    result = dooph.do_overwrite_or_rename(destn, do_op)
    dialogue.report_any_problems(result)
    return result

def pm_do_edit_files(file_paths):
    if len(file_paths) == 0:
        return
    if pm_add_files(file_paths).is_ok:
        text_edit.edit_files_extern(file_paths)

def pm_move_files(file_paths):
    destn = dooph.ask_destination(file_paths)
    if not destn:
        return
    do_op = lambda destn, force=False, overwrite=False : ifce.PM.do_move_files(file_paths, destn, force=force, overwrite=overwrite)
    refresh_op = lambda : ifce.PM.do_refresh_overlapped_files(file_paths)
    result = dooph.do_force_refresh_overwrite_or_rename(destn, do_op, refresh_op)
    dialogue.report_any_problems(result)
    return result

def pm_copy_file(file_path):
    destn = dooph.ask_destination([file_path])
    if not destn:
        return
    do_op = lambda destn, overwrite=False : ifce.PM.do_copy_file_to_top_patch(file_path, destn, overwrite=overwrite)
    result = dooph.do_overwrite_or_rename(destn, do_op)
    dialogue.report_any_problems(result)
    return result

def pm_rename_file(file_path):
    destn = dooph.ask_destination([file_path])
    if not destn:
        return
    do_op = lambda destn, force=False, overwrite=False : ifce.PM.do_rename_file_in_top_patch(file_path, destn, force=force, overwrite=overwrite)
    refresh_op = lambda : ifce.PM.do_refresh_overlapped_files([file_path])
    result = dooph.do_force_refresh_overwrite_or_rename(destn, do_op, refresh_op)
    dialogue.report_any_problems(result)
    return result

def pm_do_refresh_top_patch():
    dialogue.show_busy()
    result = ifce.PM.do_refresh_patch()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

def pm_do_refresh_named_patch(patch_name):
    dialogue.show_busy()
    result = ifce.PM.do_refresh_patch(patch_name)
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)

def pm_do_pop():
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_pop_top_patch()
        dialogue.unshow_busy()
        if not refresh_tried and result.suggests_refresh:
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
    return result.is_ok

def pm_do_pop_all():
    while ifce.PM.is_poppable():
        if not pm_do_pop():
            break

def pm_do_pop_to(patch_name):
    while ifce.PM.is_poppable() and not ifce.PM.is_top_patch(patch_name):
        if not pm_do_pop():
            break

def pm_do_push():
    force = False
    absorb = True
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_push_next_patch(absorb=absorb, force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not (absorb or force) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
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
    return result.is_ok

def pm_do_push_all():
    while ifce.PM.is_pushable():
        if not pm_do_push():
            break

def pm_do_push_to(patch_name):
    while ifce.PM.is_pushable() and not ifce.PM.is_top_patch(patch_name):
        if not pm_do_push():
            break

def pm_do_remove_patch(patch_name):
    if dialogue.ask_ok_cancel(_("Confirm remove \"{0}\" patch?").format(patch_name)):
        dialogue.show_busy()
        result = ifce.PM.do_remove_patch(patch_name)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)

def pm_do_duplicate_patch(patch_name):
    description = ifce.PM.get_patch_description(patch_name)
    dialog = DuplicatePatchDialog(patch_name, description, parent=dialogue.main_window)
    refresh_tried = False
    while True:
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            as_patch_name = dialog.get_new_patch_name()
            newdescription = dialog.get_descr()
            dialog.show_busy()
            result = ifce.PM.do_duplicate_patch(patch_name, as_patch_name, newdescription)
            dialog.unshow_busy()
            if not refresh_tried and result.suggests_refresh:
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
            if result.suggests_rename:
                continue
        break
    dialog.destroy()

def pm_do_fold_patch(patch_name):
    refresh_tried = False
    force = False
    absorb = False
    while True:
        dialogue.show_busy()
        result = ifce.PM.do_fold_named_patch(patch_name, absorb=absorb, force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not (absorb or force) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
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
                patch_file_list = ifce.PM.get_filepaths_in_named_patch(patch_name)
                top_patch_file_list = ifce.PM.get_filepaths_in_top_patch(patch_file_list)
                file_list = [filepath for filepath in patch_file_list if filepath not in top_patch_file_list]
                result = ifce.PM.do_refresh_overlapped_files(file_list)
                dialogue.unshow_busy()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break

def pm_do_fold_external_patch():
    patch_file = dialogue.ask_file_name(_("Select patch file to be folded"))
    if patch_file is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file)
    except patchlib.ParseError as edata:
        result = CmdResult.error(stderr="{0}: {1}: {2}\n".format(patch_file, edata.lineno, edata.message))
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
            result = result - result.SUGGEST_REFRESH
        if not (absorb or force) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
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

def pm_do_import_patch():
    patch_file = dialogue.ask_file_name(_("Select patch file to be imported"))
    if patch_file is None:
        return
    try:
        epatch = patchlib.Patch.parse_text_file(patch_file)
    except patchlib.ParseError as edata:
        result = CmdResult.error(stderr="{0}: {1}: {2}\n".format(patch_file, edata.lineno, edata.message))
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
        if not overwrite and result.suggests(result.SUGGEST_OVERWRITE_OR_RENAME):
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                break
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            else:
                resp = dlg.run()
            continue
        dialogue.report_any_problems(result)
        if result.suggests_rename:
            resp = dlg.run()
        else:
            break
    dlg.destroy()

def pm_do_export_named_patch(patch_name, suggestion=None, busy_indicator=None):
    if busy_indicator is None:
        busy_indicator = dialogue.main_window
    if not suggestion:
        suggestion = os.path.basename(utils.convert_patchname_to_filename(patch_name))
    if not os.path.dirname(suggestion):
        suggestion = os.path.join(recollect.get("export", "last_directory"), suggestion)
    PROMPT = _("Export as ...")
    export_filename = dialogue.ask_file_name(PROMPT, suggestion=suggestion, existing=False)
    if export_filename is None:
        return
    force = False
    overwrite = False
    refresh_tried = False
    while True:
        busy_indicator.show_busy()
        result = ifce.PM.do_export_patch_as(patch_name, export_filename, force=force, overwrite=overwrite)
        busy_indicator.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if result.suggests(result.SUGGEST_FORCE_OR_REFRESH):
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
        elif result.suggests_rename:
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
        recollect.set("export", "last_directory", os.path.dirname(export_filename))
        break

def pm_do_new_patch():
    dlg = NewPatchDialog(parent=dialogue.main_window)
    while dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.do_create_new_patch(dlg.get_new_patch_name(), dlg.get_descr())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
        if not result.suggests_rename:
            break
    dlg.destroy()

def pm_do_rename_patch(patch_name):
    dialog = dialogue.ReadTextDialog(_("Rename Patch: {0}").format(patch_name), _("New Name:"), patch_name)
    while dialog.run() == gtk.RESPONSE_OK:
        new_name = dialog.entry.get_text()
        if patch_name == new_name:
            break
        dialogue.show_busy()
        result = ifce.PM.do_rename_patch(patch_name, new_name)
        dialogue.unshow_busy()
        dialogue.report_any_problems(result)
        if not result.suggests_rename:
            break
    dialog.destroy()

def pm_do_restore_patch():
    dlg = RestorePatchDialog(parent=dialogue.main_window)
    while dlg.run() == gtk.RESPONSE_OK:
        dlg.show_busy()
        result = ifce.PM.do_restore_patch(dlg.get_restore_patch_name(), dlg.get_as_name())
        dlg.unshow_busy()
        dialogue.report_any_problems(result)
        if not result.suggests_rename:
            break
    dlg.destroy()

def pm_do_select_guards():
    cselected_guards = " ".join(ifce.PM.get_selected_guards())
    dialog = dialogue.ReadTextDialog(_("Select Guards: {0}").format(os.getcwd()), _("Guards:"), cselected_guards)
    while True:
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            selected_guards = dialog.entry.get_text()
            dialogue.show_busy()
            result = ifce.PM.do_select_guards(selected_guards)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
            if result.suggests_edit:
                continue
            dialog.destroy()
        else:
            dialog.destroy()
        break

def pm_do_set_guards_on_patch(patch_name):
    cguards = " ".join(ifce.PM.get_patch_guards(patch_name))
    dialog = dialogue.ReadTextDialog(_("Set Guards: {0}").format(patch_name), _("Guards:"), cguards)
    while True:
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            guards = dialog.entry.get_text()
            dialogue.show_busy()
            result = ifce.PM.do_set_patch_guards(patch_name, guards)
            dialogue.unshow_busy()
            dialogue.report_any_problems(result)
            if result.suggests_edit:
                continue
            dialog.destroy()
        else:
            dialog.destroy()
        break

def pm_add_new_file_to_top_patch():
    filepath = dialogue.ask_file_name(_("Enter path for new file"), existing=False)
    if not filepath:
        return
    pm_add_files([filepath])

def scm_do_absorb_applied_patches():
    dialogue.show_busy()
    result = ifce.PM.do_scm_absorb_applied_patches()
    dialogue.unshow_busy()
    dialogue.report_any_problems(result)
    return result.is_ok

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("pm_create_new_pgnd", icons.STOCK_NEW_PLAYGROUND, _("_New"), "",
         _("Create a new intitialized playground"),
         lambda _action=None: pm_do_create_new_pgnd()
        ),
    ]
)

actions.CLASS_INDEP_AGS[ws_actions.AC_NOT_IN_PM_PGND].add_actions(
    [
        ("pm_init_cwd", icons.STOCK_INIT, _("_Initialize"), "",
         _("Create a patch series in the current directory"),
         lambda _action=None: pm_initialize_curdir()
        ),
    ]
)

actions.CLASS_INDEP_AGS[ws_actions.AC_PMIC | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_add_new_file", gtk.STOCK_NEW, _("New"), None,
         _("Add a new file to the top applied patch"),
         lambda _action=None: pm_add_new_file_to_top_patch()
        ),
        ("pm_refresh_top_patch", icons.STOCK_REFRESH_PATCH, None, None,
         _("Refresh the top patch"),
         lambda _action=None: pm_do_refresh_top_patch()
        ),
    ]
)

actions.CLASS_INDEP_AGS[AC_POP_POSSIBLE | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_pop", icons.STOCK_POP_PATCH, _("Pop"), None,
         _("Pop the top applied patch"),
         lambda _action=None: pm_do_pop()
        ),
        ("pm_pop_all", icons.STOCK_POP_PATCH, _("Pop All"), None,
         _("Pop all applied patches"),
         lambda _action=None: pm_do_pop_all()
        ),
        ("pm_fold_external_patch", icons.STOCK_FOLD_PATCH, None, None,
         _("Fold an external patch into the top applied patch"),
         lambda _action=None: pm_do_fold_external_patch()
        ),
    ]
)

actions.CLASS_INDEP_AGS[AC_PUSH_POSSIBLE | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_push", icons.STOCK_PUSH_PATCH, _("Push"), None,
         _("Apply the next unapplied patch"),
         lambda _action=None: pm_do_push()
        ),
        ("pm_push_all", icons.STOCK_PUSH_PATCH, _("Push All"), None,
         _("Apply all unguarded unapplied patches."),
         lambda _action=None: pm_do_push_all()
        ),
    ]
)

actions.CLASS_INDEP_AGS[ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_new_patch", icons.STOCK_NEW_PATCH, None, None,
         _("Create a new patch"),
         lambda _action=None: pm_do_new_patch()
        ),
        ("pm_restore_patch", icons.STOCK_IMPORT_PATCH, _("Restore Patch"), None,
         _("Restore a previously removed patch behind the top applied patch"),
         lambda _action=None: pm_do_restore_patch()
        ),
        ("pm_import_patch", icons.STOCK_IMPORT_PATCH, None, None,
         _("Import an external patch behind the top applied patch"),
         lambda _action=None: pm_do_import_patch()
        ),
        ("pm_select_guards", icons.STOCK_PATCH_GUARD_SELECT, None, None,
         _("Select which guards are in force"),
         lambda _action=None: pm_do_select_guards()
        ),
        ("pm_edit_series_descr", gtk.STOCK_EDIT, _("Description"), None,
         _("Edit the series' description"),
         lambda _action=None: SeriesDescrEditDialog(parent=dialogue.main_window).show()
        ),
    ]
)

actions.CLASS_INDEP_AGS[AC_ALL_APPLIED_REFRESHED | ws_actions.AC_IN_SCM_PGND | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_scm_absorb_applied_patches", icons.STOCK_FINISH_PATCH, _("Absorb All"), None,
         _("Absorb all applied patches into underlying SCM repository"),
         lambda _action=None: scm_do_absorb_applied_patches()
        ),
    ]
)

class NewSeriesDescrDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = \
        """
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
        """
        def __init__(self):
            text_edit.DbMessageWidget.__init__(self)
        def populate_action_groups(self):
            text_edit.DbMessageWidget.populate_action_groups(self)
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
    def __init__(self, parent=None):
        flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _("Patch Series Description: %s -- gdarn") % utils.path_rel_home(os.getcwd())
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
        self.set_title(_("New Patch: {0} -- gdarn").format(utils.path_rel_home(os.getcwd())))
        self.hbox = gtk.HBox()
        self.hbox.pack_start(gtk.Label(_("New Patch Name:")), fill=False, expand=False)
        self.new_name_entry = gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.hbox.pack_start(self.new_name_entry)
        self.hbox.show_all()
        self.vbox.pack_start(self.hbox)
        self.vbox.reorder_child(self.hbox, 0)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()

class DuplicatePatchDialog(NewSeriesDescrDialog):
    def __init__(self, patch_name, olddescr, parent=None):
        NewSeriesDescrDialog.__init__(self, parent=parent)
        self.set_title(_("Duplicate Patch: {0}: {1} -- gdarn").format(patch_name, utils.path_rel_home(os.getcwd())))
        self.hbox = gtk.HBox()
        self.hbox.pack_start(gtk.Label(_("Duplicate Patch Name:")), fill=False, expand=False)
        self.new_name_entry = gtk.Entry()
        self.new_name_entry.set_width_chars(32)
        self.new_name_entry.set_text(patch_name + ".duplicate")
        self.hbox.pack_start(self.new_name_entry)
        self.edit_descr_widget.set_contents(olddescr)
        self.hbox.show_all()
        self.vbox.pack_start(self.hbox)
        self.vbox.reorder_child(self.hbox, 0)
    def get_new_patch_name(self):
        return self.new_name_entry.get_text()

class SeriesDescrEditDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = \
        """
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
        """
        def __init__(self):
            text_edit.DbMessageWidget.__init__(self)
            self.view.set_editable(ifce.PM.is_writable())
            self.load_text_fm_db()
        def populate_action_groups(self):
            text_edit.DbMessageWidget.populate_action_groups(self)
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
        def get_text_fm_db(self):
            return ifce.PM.get_series_description()
        def set_text_in_db(self, text):
            return ifce.PM.do_set_series_description(text)
    def __init__(self, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _("Series Description: {0} -- gdarn").format(utils.path_rel_home(os.getcwd()))
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
                qtn = "\n".join([_("Unsaved changes to summary will be lost."), _("Close anyway?")])
                if dialogue.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class PatchDescrEditDialog(dialogue.Dialog):
    class Widget(text_edit.DbMessageWidget):
        UI_DESCR = """
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
        """
        def __init__(self, patch):
            text_edit.DbMessageWidget.__init__(self)
            self.view.set_editable(ifce.PM.is_writable())
            self._patch = patch
            self.load_text_fm_db()
        def populate_action_groups(self):
            text_edit.DbMessageWidget.populate_action_groups(self)
            self.action_groups[0].add_actions(
                [
                    ("load_menu", None, _("_File")),
                ])
        def get_text_fm_db(self):
            return ifce.PM.get_patch_description(self._patch)
        def set_text_in_db(self, text):
            return ifce.PM.do_set_patch_description(self._patch, text)
    def __init__(self, patch, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _("Patch: {0} : {1} -- gdarn").format(patch, utils.path_rel_home(os.getcwd()))
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
                qtn = "\n".join([_("Unsaved changes to summary will be lost."), _("Close anyway?")])
                if dialogue.ask_yes_no(qtn):
                    self.destroy()
            else:
                self.destroy()

class ImportPatchDialog(dialogue.Dialog):
    def __init__(self, epatch, parent=None):
        flags = ~gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
        title = _("Import Patch: {0} : {1} -- gdarn").format(epatch.source_name, utils.path_rel_home(os.getcwd()))
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
        self.strip_level_buttons = [gtk.RadioButton(group=None, label="0")]
        self.strip_level_buttons.append(gtk.RadioButton(group=self.strip_level_buttons[0], label="1"))
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
            self.file_list_widget.set_contents("\n".join(filepaths))
        except:
            if strip_level == 0:
                return
            self.strip_level_buttons[0].set_active(True)
    def _strip_level_toggle_cb(self, _widget, *args,**kwargs):
        self.update_file_list()

class FoldPatchDialog(ImportPatchDialog):
    def __init__(self, epatch, parent=None):
        ImportPatchDialog.__init__(self, epatch, parent)
        self.set_title( _("Fold Patch: {0} : {1} -- gdarn").format(epatch.source_name, utils.path_rel_home(os.getcwd())))
        self.namebox.hide()

class RestorePatchDialog(dialogue.Dialog):
    _KEYVAL_ESCAPE = gtk.gdk.keyval_from_name("Escape")
    class Table(table.Table):
        class View(table.Table.View):
            class Model(table.Table.View.Model):
                Row = collections.namedtuple("Row", ["PatchName"])
                types = Row(PatchName=gobject.TYPE_STRING)
            specification = tlview.ViewSpec(
                properties={
                    "enable-grid-lines" : False,
                    "reorderable" : False,
                    "rules_hint" : False,
                    "headers-visible" : False,
                },
                selection_mode=gtk.SELECTION_SINGLE,
                columns=[
                    tlview.ColumnSpec(
                        title=_("Patch Name"),
                        properties={"expand": False, "resizable" : True},
                        cells=[
                            tlview.CellSpec(
                                cell_renderer_spec=tlview.CellRendererSpec(
                                    cell_renderer=gtk.CellRendererText,
                                    expand=False,
                                    start=True
                                ),
                                properties={"editable" : False},
                                cell_data_function_spec=None,
                                attributes = {"text" : Model.col_index("PatchName")}
                            ),
                        ],
                    ),
                ]
            )
        def __init__(self):
            table.Table.__init__(self, size_req=(480, 160))
            self.connect("key_press_event", self._key_press_cb)
            self.connect("button_press_event", self._handle_button_press_cb)
            self.set_contents()
        def get_selected_patch(self):
            data = self.get_selected_data_by_label(["PatchName"])
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
        dialogue.Dialog.__init__(self, title=_("gdarn: Restore Patch"), parent=parent,
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
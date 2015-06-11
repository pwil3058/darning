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

from . import ifce
from . import dialogue
from . import dooph

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

import gtk

from . import actions
from . import ws_actions

def pm_add_new_file_to_top_patch():
    filepath = dialogue.ask_file_name(_('Enter path for new file'), existing=False)
    if not filepath:
        return
    pm_add_files([filepath])


actions.CLASS_INDEP_AGS[ws_actions.AC_PMIC | ws_actions.AC_IN_PM_PGND_MUTABLE].add_actions(
    [
        ("pm_add_new_file", gtk.STOCK_NEW, _('New'), None,
         _('Add a new file to the top applied patch'), lambda _action=None: pm_add_new_file_to_top_patch()),
    ])

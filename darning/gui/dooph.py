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

"""
Helpers for "do" operations
"""

import os

import gtk

from ..cmd_result import CmdResult

from .. import utils

from . import dialogue

def ask_destination(file_paths):
    prompt = _("Enter destination path:")
    if len(file_paths) > 1:
        return dialogue.ask_dir_name(prompt, suggestion=os.path.relpath(os.getcwd()), existing=False)
    else:
        return dialogue.ask_file_name(prompt, suggestion=file_paths[0], existing=False)

def get_renamed_destn(destn):
    prompt = _("Enter new destination path:")
    if os.path.isdir(destn):
        return dialogue.ask_dir_name(prompt, suggestion=destn, existing=False)
    else:
        return dialogue.ask_file_name(prompt, suggestion=destn, existing=False)

def expand_destination(destn, file_paths):
    return [os.path.join(destn, os.path.basename(file_path)) for file_path in file_paths]

def confirm_copy_or_move_opn(opn, file_paths, destn):
    if os.path.isdir(destn):
        opns = []
        for file_path in file_paths:
            destn_file_path = os.path.join(destn, os.path.basename(file_path))
            tmpl = _("{0} {1} {2}: overwriting {2}") if os.path.exists(destn_file_path) else "{0} {1} {2}"
            opns.append(tmpl.format(utlis.quote_if_needed(file_path), opn, utlis.quote_if_needed(destn_file_path)))
        return dialogue.confirm_list_action(opns, _("Operation about to be executed. Continue?"))
    else:
        assert len(file_paths) == 1
        tmpl = _("{0} {1} {2}: overwriting {2}. OK?") if os.path.exists(destn_file_path) else _("{0} {1} {2}. OK?")
        return dialogue.ask_ok_cancel(tmpltmpl.format(utlis.quote_if_needed(file_path), opn, utlis.quote_if_needed(destn_file_path)))

def do_overwrite_or_rename(destn, do_op):
    overwrite = False
    while True:
        dialogue.show_busy()
        result = do_op(destn, overwrite=overwrite)
        dialogue.unshow_busy()
        if result.suggests(CmdResult.SUGGEST_OVERWRITE_OR_RENAME):
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            elif resp == dialogue.Response.RENAME:
                destn = get_renamed_destn(destn)
                if destn is None:
                    break
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_absorb_force_refresh_overwrite_or_rename(destn, do_op, refresh_op):
    force = False
    overwrite = False
    absorb = False
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = do_op(destn, absorb=absorb, force=force, overwrite=overwrite)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not (force or absorb) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                result = refresh_op()
                dialogue.report_any_problems(result)
            continue
        elif not overwrite and result.suggests(CmdResult.SUGGEST_OVERWRITE_OR_RENAME):
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            elif resp == dialogue.Response.RENAME:
                destn = get_renamed_destn(destn)
                if destn is None:
                    break
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_force_refresh_overwrite_or_rename(destn, do_op, refresh_op):
    force = False
    overwrite = False
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = do_op(destn, force=force, overwrite=overwrite)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not force and result.suggests(result.SUGGEST_FORCE_OR_REFRESH):
            resp = dialogue.ask_force_refresh_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                result = refresh_op()
                dialogue.report_any_problems(result)
            continue
        elif not overwrite and result.suggests(CmdResult.SUGGEST_OVERWRITE_OR_RENAME):
            resp = dialogue.ask_rename_overwrite_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.OVERWRITE:
                overwrite = True
            elif resp == dialogue.Response.RENAME:
                destn = get_renamed_destn(destn)
                if destn is None:
                    break
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_force_or_recover(do_op, recover_op):
    force = False
    recovery_tried = False
    while True:
        dialogue.show_busy()
        result = do_op(force=force)
        dialogue.unshow_busy()
        if not force and result.suggests_force:
            if dialogue.ask_force_or_cancel(result) == dialogue.Response.FORCE:
                force = True
            else:
                return CmdResult.ok()
            continue
        elif not recovery_tried and result.suggests_recover:
            if dialogue.ask_recover_or_cancel(result) == dialogue.Response.RECOVER:
                dialogue.show_busy()
                result = recover_op()
                dialogue.unshow_busy()
                if not result.is_ok:
                    return result
            else:
                return CmdResult.ok()
            continue
        dialogue.report_any_problems(result)
        return result

def do_force_or_refresh(do_op, refresh_op):
    force = False
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = do_op(force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not force and result.suggests(result.SUGGEST_FORCE_OR_REFRESH):
            resp = dialogue.ask_force_refresh_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                result = refresh_op()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_force_refresh_or_absorb(do_op, refresh_op):
    absorb = False
    force = False
    refresh_tried = False
    while True:
        dialogue.show_busy()
        result = do_op(absorb=absorb, force=force)
        dialogue.unshow_busy()
        if refresh_tried:
            result = result - result.SUGGEST_REFRESH
        if not (absorb or force) and result.suggests(result.SUGGEST_FORCE_ABSORB_OR_REFRESH):
            resp = dialogue.ask_force_refresh_absorb_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.FORCE:
                force = True
            elif resp == dialogue.Response.ABSORB:
                absorb = True
            elif resp == dialogue.Response.REFRESH:
                refresh_tried = True
                result = refresh_op()
                dialogue.report_any_problems(result)
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_or_discard(do_op):
    discard = False
    while True:
        dialogue.show_busy()
        result = do_op(discard=discard)
        dialogue.unshow_busy()
        if not discard and result.suggests_discard:
            resp = dialogue.ask_discard_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.DISCARD:
                discard = True
            continue
        dialogue.report_any_problems(result)
        break
    return result

def do_or_force(do_op):
    force = False
    while True:
        dialogue.show_busy()
        result = do_op(force=force)
        dialogue.unshow_busy()
        if not force and result.suggests_force:
            resp = dialogue.ask_force_or_cancel(result, clarification=None)
            if resp == gtk.RESPONSE_CANCEL:
                return CmdResult.ok() # we don't want to be a nag
            elif resp == dialogue.Response.FORCE:
                force = True
            continue
        dialogue.report_any_problems(result)
        break
    return result

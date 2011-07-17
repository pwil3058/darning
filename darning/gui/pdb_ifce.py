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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

'''GUI interface to patch_db'''
import os
import pango

from darning import patch_db
from darning import cmd_result
from darning import fsdb
from darning import utils

# patch_db commands that don't need wrapping
from darning.patch_db import find_base_dir

from darning.gui import ws_event
from darning.gui import console

def open_db():
    result = patch_db.load_db(lock=True)
    if result is True:
        return cmd_result.Result(cmd_result.OK, '')
    return cmd_result.Result(cmd_result.ERROR, str(result) + '\n')

def close_db():
    '''Close the patch database if it is open'''
    if patch_db.is_readable():
        patch_db.release_db()

def do_initialization(description):
    '''Create a patch database in the current directory'''
    console.LOG.start_cmd(_('initialize {0}\n"{1}"\n').format(os.getcwd(), description))
    result = patch_db.create_db(description)
    if not result:
        console.LOG.append_stderr(str(result))
    console.LOG.end_cmd()
    return result

def get_in_progress():
    return patch_db.is_readable() and patch_db.get_top_patch_name() is not None

def get_all_patches_data():
    if not patch_db.is_readable():
        return []
    return patch_db.get_patch_table_data()

def get_selected_guards():
    if not patch_db.is_readable():
        return set()
    return patch_db.get_selected_guards()

def get_patch_description(patch):
    if not patch_db.is_readable():
        raise cmd_result.Failure(_('Database is unreadable'))
    return patch_db.get_patch_description(patch)

def get_series_description():
    if not patch_db.is_readable():
        raise cmd_result.Failure(_('Database is unreadable'))
    return patch_db.get_series_description()

DECO_MAP = {
    None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
    patch_db.FileData.Presence.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
    patch_db.FileData.Presence.REMOVED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
    patch_db.FileData.Presence.EXTANT: fsdb.Deco(pango.STYLE_NORMAL, "black"),
}

def get_status_deco(status):
    return DECO_MAP[status.presence]

class FileDb(fsdb.GenFileDb):
    class Dir(fsdb.GenDir):
        def __init__(self):
            fsdb.GenDir.__init__(self)
            self.status = patch_db.FileData.Status(None, None)
        def _new_dir(self):
            return FileDb.Dir()
        def _update_own_status(self):
            if len(self.status_set) == 1:
                self.status = list(self.status_set)[0]
            else:
                self.status = patch_db.FileData.Status(None, None)
    def __init__(self, file_list):
        fsdb.GenFileDb.__init__(self, FileDb.Dir)
        for item in file_list:
            parts = fsdb.split_path(item.name)
            self.base_dir.add_file(parts, item.status, item.origin)
        self.decorate_dirs()

def get_file_db(patch=None):
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    if patch is None:
        patch = patch_db.get_top_patch_name()
    return fsdb.NullFileDb() if patch is None else FileDb(patch_db.get_patch_file_table(patch))

def get_combined_patch_file_db():
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    return FileDb(patch_db.get_combined_patch_file_table())

def get_filepaths_in_next_patch(filepaths=None):
    '''
    Return the names of the files in the next patch (to be applied).
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    if not patch_db.is_readable():
        return []
    return patch_db.get_filepaths_in_next_patch(filepaths=filepaths)

def get_file_diff(filepath, patchname):
    if not patch_db.is_readable():
        return None
    return patch_db.get_file_diff(filepath, patchname)

def get_file_combined_diff(filepath):
    if not patch_db.is_readable():
        return None
    return patch_db.get_file_combined_diff(filepath)

def get_patch_guards(patch):
    if not patch_db.is_readable():
        return ''
    guards = patch_db.get_patch_guards(patch)
    return ['+' + grd for grd in guards.positive] + ['-' + grd for grd in guards.negative]

def get_top_applied_patch_for_file(filepath):
    if not patch_db.is_readable():
        return None
    return patch_db.get_top_applied_patch_for_file(filepath)

def get_kept_patch_names():
    if not patch_db.is_readable():
        return []
    return patch_db.get_kept_patch_names()

def get_extdiff_files_for(filepath, patchname):
    if not patch_db.is_readable():
        return None
    if patchname is None:
        patchname = patch_db.get_top_applied_patch_for_file(filepath)
    return patch_db.get_extdiff_files_for(filepath, patchname)

def do_create_new_patch(patchname, descr):
    if patch_db.patch_is_in_series(patchname):
        return cmd_result.Result(cmd_result.ERROR|cmd_result.SUGGEST_RENAME, _('{0}: Already exists in database').format(patchname))
    patch_db.do_create_new_patch(patchname, descr)
    console.LOG.append_entry(_('new patch "{0}"\n"{1}"\n').format(patchname, descr))
    patch_db.apply_patch()
    ws_event.notify_events(ws_event.PATCH_CREATE|ws_event.PATCH_PUSH)
    return cmd_result.Result(cmd_result.OK, '')

def do_restore_patch(patchname, as_patchname=''):
    if not as_patchname:
        as_patchname = patchname
    if patch_db.patch_is_in_series(as_patchname):
        return cmd_result.Result(cmd_result.ERROR|cmd_result.SUGGEST_RENAME, _('{0}: Already exists in database').format(as_patchname))
    patch_db.do_restore_patch(patchname, as_patchname)
    if patchname == as_patchname:
        console.LOG.append_entry(_('restore patch "{0}"\n').format(patchname))
    else:
        console.LOG.append_entry(_('restore patch "{0}" as "{1}"\n').format(patchname, as_patchname))
    ws_event.notify_events(ws_event.PATCH_CREATE)
    return cmd_result.Result(cmd_result.OK, '')

def do_push_next_patch(force=False):
    console.LOG.start_cmd('push\n')
    eflags = cmd_result.OK
    msg = ''
    overlaps = patch_db.get_next_patch_overlap_data()
    if len(overlaps.uncommitted) > 0:
        if force:
            console.LOG.append_stderr(_('Uncommitted SCM changes in the following files:\n'))
            for filepath in sorted(overlaps.uncommitted):
                console.LOG.append_stderr('\t{0}\n'.format(filepath))
            console.LOG.append_stderr(_('have been incorporated.\n'))
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE
            msg += _('The following (overlapped) files have uncommitted SCM changes:\n')
            for filepath in sorted(overlaps.uncommitted):
                msg += '\t{0}\n'.format(filepath)
    if len(overlaps.unrefreshed) > 0:
        if force:
            console.LOG.append_stderr(_('Unrefreshed changes changes in the following files:\n'))
            for filepath in sorted(overlaps.unrefreshed):
                console.LOG.append_stderr('\t{0}\n'.format(filepath))
            console.LOG.append_stderr(_('have been incorporated.\n'))
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH
            msg += _('The following (overlapped) files have unrefreshed changes (in an applied patch):\n')
            for filepath in sorted(overlaps.unrefreshed):
                msg += _('\t{0} : in patch "{1}"\n').format(filepath, overlaps.unrefreshed[filepath])
    if eflags != cmd_result.OK:
        console.LOG.append_stderr(msg)
        console.LOG.end_cmd()
        return cmd_result.Result(eflags, msg)
    _db_ok, results = patch_db.apply_patch(force)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    for filepath in results:
        result = results[filepath]
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        if result.ecode:
            msg += result.stdout + result.stderr
    console.LOG.append_stdout(_('Patch "{0}" is now on top\n').format(patch_db.get_top_patch_name()))
    if highest_ecode > 1:
        eflags = cmd_result.ERROR
        msg = _('A refresh is required after issues are resolved.\n')
    elif highest_ecode > 0:
        eflags = cmd_result.WARNING
        msg = _('A refresh is required.\n')
    console.LOG.append_stderr(msg)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_PUSH)
    return cmd_result.Result(eflags, msg)

def do_pop_top_patch():
    if patch_db.top_patch_needs_refresh():
        top_patch = patch_db.get_top_patch_name()
        ws_event.notify_events(ws_event.PATCH_REFRESH)
        return cmd_result.Result(cmd_result.ERROR_SUGGEST_REFRESH, _('Top patch ("{0}") needs to be refreshed\n').format(top_patch))
    console.LOG.start_cmd('pop\n')
    result = patch_db.unapply_top_patch()
    if result is not True:
        stderr = _('{0}: top patch is now "{1}"').format(result, patch_db.get_top_patch_name())
        console.LOG.append_stderr(stderr)
        console.LOG.end_cmd()
        eflags = cmd_result.ERROR
    else:
        top_patch = patch_db.get_top_patch_name()
        if top_patch is None:
            console.LOG.append_stdout(_('There are now no patches applied\n'))
        else:
            console.LOG.append_stdout(_('Patch "{0}" is now on top\n').format(top_patch))
        console.LOG.end_cmd()
        stderr = ''
        eflags = cmd_result.OK
    ws_event.notify_events(ws_event.PATCH_POP)
    return cmd_result.Result(eflags, stderr)

def do_refresh_overlapped_files(file_list):
    console.LOG.start_cmd('refresh --files {0}\n'.format(utils.file_list_to_string(file_list)))
    results = patch_db.do_refresh_overlapped_files(file_list)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    msg = ''
    failed_files = []
    for filepath in results:
        result = results[filepath]
        console.LOG.append_stdout(_('Refreshing: {0}\n').format(filepath))
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        for line in result.stderr.splitlines(False):
            msg += _('{0}: {1}\n').format(filepath, line)
        if result.ecode > 2:
            failed_files.append(filepath)
    console.LOG.end_cmd()
    if highest_ecode > 2:
        eflags = cmd_result.ERROR
        msg += _('\nThe following files require another refresh after issues are resolved:\n')
        for filepath in failed_files:
            msg += '\t{0}\n'.format(filepath)
    else:
        eflags = cmd_result.OK if highest_ecode == 0 else cmd_result.WARNING
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, msg)

def do_refresh_patch(patchname=None):
    if patchname is None:
        patchname = patch_db.get_top_patch_name()
    console.LOG.start_cmd('refresh {0}\n'.format(patchname))
    results = patch_db.do_refresh_patch(patchname)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    msg = ''
    for filepath in results:
        result = results[filepath]
        console.LOG.append_stdout(_('Refreshing: {0}\n').format(filepath))
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        for line in result.stderr.splitlines(False):
            msg += '{0}: {1}\n'.format(filepath, line)
    console.LOG.end_cmd()
    if highest_ecode > 2:
        eflags = cmd_result.ERROR
        msg += _('\nPatch "{0}" requires another refresh after issues are resolved.').format(patchname)
    else:
        eflags = cmd_result.WARNING if (highest_ecode > 0 and msg) else cmd_result.OK
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, msg)

def do_remove_patch(patchname):
    console.LOG.start_cmd('remove patch: {0}\n'.format(patchname))
    patch_db.do_remove_patch(patchname)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_DELETE)
    return cmd_result.Result(cmd_result.OK, '')

def do_set_patch_description(patch, text):
    if not patch_db.is_writable():
        return cmd_result.Result(cmd_result.ERROR, _('Database is not writable'))
    patch_db.do_set_patch_description(patch, text)
    console.LOG.append_entry(_('set patch "{0}" description:\n"{1}"\n').format(patch, text))
    return cmd_result.Result(cmd_result.OK, '')

def do_set_series_description(text):
    if not patch_db.is_writable():
        return cmd_result.Result(cmd_result.ERROR, _('Database is not writable'))
    patch_db.do_set_series_description(text)
    console.LOG.append_entry(_('set series description:\n"{0}"\n').format(text))
    return cmd_result.Result(cmd_result.OK, '')

def do_set_patch_guards(patch, guards_str):
    if not patch_db.is_writable():
        return cmd_result.Result(cmd_result.ERROR, _('Database is not writable'))
    guards_list = guards_str.split()
    pos_guards = [grd[1:] for grd in guards_list if grd.startswith('+')]
    neg_guards = [grd[1:] for grd in guards_list if grd.startswith('-')]
    if len(guards_list) != (len(pos_guards) + len(neg_guards)):
        return cmd_result.Result(cmd_result.ERROR|cmd_result.SUGGEST_EDIT, _('Guards must start with "+" or "-" and contain no whitespace.'))
    patch_db.do_set_patch_guards(patch, patch_db.PatchData.Guards(positive=pos_guards, negative=neg_guards))
    ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(cmd_result.OK, '')

def do_select_guards(guards_str):
    if not patch_db.is_writable():
        return cmd_result.Result(cmd_result.ERROR, _('Database is not writable'))
    guards_list = guards_str.split()
    for guard in guards_list:
        if guard.startswith('+') or guard.startswith('-'):
            return cmd_result.Result(cmd_result.ERROR|cmd_result.SUGGEST_EDIT, _('Guard names may not start with "+" or "-".\n'))
    patch_db.do_select_guards(guards_list)
    ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(cmd_result.OK, '')

def do_add_files_to_patch(file_list, patch=None, force=False):
    if patch is None:
        console.LOG.start_cmd('add {0}\n'.format(utils.file_list_to_string(file_list)))
        patch = patch_db.get_top_patch_name()
    else:
        console.LOG.start_cmd('add --patch={0} {1}\n'.format(patch, utils.file_list_to_string(file_list)))
    for already_in_patch in patch_db.get_filepaths_in_patch(patch, file_list):
        file_list.remove(already_in_patch)
        console.LOG.append_stdout(_('File "{0}" already in patch "{1}". Ignored.\n').format(already_in_patch, patch))
    eflags = cmd_result.OK
    msg = ''
    overlaps = patch_db.get_filelist_overlap_data(file_list, patch)
    if len(overlaps.uncommitted) > 0:
        if force:
            console.LOG.append_stderr(_('Uncommitted SCM changes in the following files:\n'))
            for filepath in sorted(overlaps.uncommitted):
                console.LOG.append_stderr('\t{0}\n'.format(filepath))
            console.LOG.append_stderr(_('have been incorporated.\n'))
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE
            msg += _('The following files have uncommitted SCM changes:\n')
            for filepath in sorted(overlaps.uncommitted):
                msg += '\t{0}\n'.format(filepath)
    if len(overlaps.unrefreshed) > 0:
        if force:
            console.LOG.append_stderr(_('Unrefreshed changes changes in the following files:\n'))
            for filepath in sorted(overlaps.unrefreshed):
                console.LOG.append_stderr('\t{0}\n'.format(filepath))
            console.LOG.append_stderr(_('have been incorporated.\n'))
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH
            msg += _('The following files have unrefreshed changes (in an applied patch):\n')
            for filepath in sorted(overlaps.unrefreshed):
                msg += _('\t{0} : in patch "{1}"\n').format(filepath, overlaps.unrefreshed[filepath])
    if eflags is not cmd_result.OK:
        console.LOG.append_stderr(msg)
        console.LOG.end_cmd()
        return cmd_result.Result(eflags, msg)
    for filepath in file_list:
        patch_db.add_file_to_patch(patch, filepath, force=force)
        console.LOG.append_stdout(_('File "{0}" added to patch "{1}".\n').format(filepath, patch))
    console.LOG.end_cmd()
    if force:
        ws_event.notify_events(ws_event.FILE_ADD|ws_event.PATCH_REFRESH)
    else:
        ws_event.notify_events(ws_event.FILE_ADD)
    return cmd_result.Result(eflags, '')

def do_drop_files_from_patch(file_list, patch=None):
    if patch is None:
        console.LOG.start_cmd('drop {0}\n'.format(utils.file_list_to_string(file_list)))
        patch = patch_db.get_top_patch_name()
    else:
        console.LOG.start_cmd(_('drop --patch={0} {1}\n').format(patch, utils.file_list_to_string(file_list)))
    for filepath in file_list:
        patch_db.do_drop_file_fm_patch(patch, filepath)
        console.LOG.append_stdout(_('File "{0}" dropped from patch "{1}".\n').format(filepath, patch))
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.FILE_DEL)
    return cmd_result.Result(cmd_result.OK, '')

def is_pushable():
    if not patch_db.is_readable():
        return False
    return patch_db.is_pushable()

def is_poppable():
    return get_in_progress()

def is_top_applied_patch(patchname):
    if not patch_db.is_readable():
        return False
    return patch_db.is_top_applied_patch(patchname)

def is_blocked_by_guard(patchname):
    if not patch_db.is_readable():
        return False
    return patch_db.is_blocked_by_guard(patchname)

def is_readable():
    return patch_db.is_readable()

def is_writable():
    return patch_db.is_writable()

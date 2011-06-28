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
        return cmd_result.Result(cmd_result.OK, '', '')
    return cmd_result.Result(cmd_result.ERROR, '', str(result))

def close_db():
    '''Close the patch database if it is open'''
    if patch_db.is_readable():
        patch_db.release_db()

def do_initialization(description):
    '''Create a patch database in the current directory'''
    console.LOG.start_cmd('initialize {0}\n"{1}"'.format(os.getcwd(), description))
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
        raise cmd_result.Failure('Database is unreadable')
    return patch_db.get_patch_description(patch)

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

def do_create_new_patch(name, descr):
    if patch_db.patch_is_in_series(name):
        return cmd_result.Result(cmd_result.ERROR|cmd_result.SUGGEST_RENAME, '', '{0}: Already exists in database'.format(name))
    patch_db.create_new_patch(name, descr)
    console.LOG.append_entry('new patch "{0}"\n"{1}"'.format(name, descr))
    patch_db.apply_patch()
    ws_event.notify_events(ws_event.PATCH_CREATE|ws_event.PATCH_PUSH)
    return cmd_result.Result(cmd_result.OK, '', '')

def do_push_next_patch(force=False):
    console.LOG.start_cmd('push')
    eflags = cmd_result.OK
    msg = ''
    overlaps = patch_db.get_next_patch_overlap_data()
    if len(overlaps.uncommitted) > 0:
        if force:
            console.LOG.append_stderr('Uncommitted SCM changes in the following files:\n')
            for filename in sorted(overlaps.uncommitted):
                console.LOG.append_stderr('\t{0}\n'.format(filename))
            console.LOG.append_stderr('have been incorporated.\n')
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE
            msg += 'The following (overlapped) files have uncommitted SCM changes:\n'
            for filename in sorted(overlaps.uncommitted):
                msg += '\t{0}\n'.format(filename)
    if len(overlaps.unrefreshed) > 0:
        if force:
            console.LOG.append_stderr('Unrefreshed changes changes in the following files:\n')
            for filename in sorted(overlaps.unrefreshed):
                console.LOG.append_stderr('\t{0}\n'.format(filename))
            console.LOG.append_stderr('have been incorporated.\n')
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH
            msg += 'The following (overlapped) files have unrefreshed changes (in an applied patch):\n'
            for filename in sorted(overlaps.unrefreshed):
                msg += '\t{0} : in patch "{1}"\n'.format(filename, overlaps.unrefreshed[filename])
    if eflags != cmd_result.OK:
        console.LOG.append_stderr(msg)
        console.LOG.end_cmd()
        return cmd_result.Result(eflags, '', msg)
    _db_ok, results = patch_db.apply_patch(force)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    for filename in results:
        result = results[filename]
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        if result.ecode:
            msg += result.stdout + result.stderr
    console.LOG.append_stdout('Patch "{0}" is now on top\n'.format(patch_db.get_top_patch_name()))
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_PUSH)
    return cmd_result.Result(cmd_result.ERROR if highest_ecode > 0 else cmd_result.OK, '', msg)

def do_pop_top_patch():
    if patch_db.top_patch_needs_refresh():
        top_patch = patch_db.get_top_patch_name()
        ws_event.notify_events(ws_event.PATCH_REFRESH)
        return cmd_result.Result(cmd_result.ERROR_SUGGEST_REFRESH, '', 'Top patch ("{0}") needs to be refreshed'.format(top_patch))
    console.LOG.start_cmd('pop')
    result = patch_db.unapply_top_patch()
    if result is not True:
        stderr = '{0}: top patch is now "{1}"'.format(result, patch_db.get_top_patch_name())
        console.LOG.append_stderr(stderr)
        console.LOG.end_cmd()
        eflags = cmd_result.ERROR
    else:
        top_patch = patch_db.get_top_patch_name()
        if top_patch is None:
            console.LOG.append_stdout('There are now no patches applied\n')
        else:
            console.LOG.append_stdout('Patch "{0}" is now on top\n'.format(top_patch))
        console.LOG.end_cmd()
        stderr = ''
        eflags = cmd_result.OK
    ws_event.notify_events(ws_event.PATCH_POP)
    return cmd_result.Result(eflags, '', stderr)

def do_refresh_overlapped_files(file_list):
    console.LOG.start_cmd('refresh --files {0}'.format(utils.file_list_to_string(file_list)))
    results = patch_db.do_refresh_overlapped_files(file_list)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    msg = ''
    failed_files = []
    for filename in results:
        result = results[filename]
        console.LOG.append_stdout('Refreshing: {0}\n'.format(filename))
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        for line in result.stderr.splitlines(False):
            msg += '{0}: {1}\n'.format(filename, line)
        if result.ecode > 2:
            failed_files.append(filename)
    console.LOG.end_cmd()
    if highest_ecode > 2:
        eflags = cmd_result.ERROR
        msg += '\nThe following files require another refresh after issues are resolved:\n'
        for filename in failed_files:
            msg += '\t{0}\n'.format(filename)
    else:
        eflags = cmd_result.OK if highest_ecode == 0 else cmd_result.WARNING
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, '', msg)

def do_refresh_patch(name=None):
    if name is None:
        name = patch_db.get_top_patch_name()
    console.LOG.start_cmd('refresh {0}'.format(name))
    results = patch_db.do_refresh_patch(name)
    highest_ecode = max([result.ecode for result in results.values()]) if results else 0
    msg = ''
    for filename in results:
        result = results[filename]
        console.LOG.append_stdout('Refreshing: {0}\n'.format(filename))
        console.LOG.append_stdout(result.stdout)
        console.LOG.append_stderr(result.stderr)
        for line in result.stderr.splitlines(False):
            msg += '{0}: {1}\n'.format(filename, line)
    console.LOG.end_cmd()
    if highest_ecode > 2:
        eflags = cmd_result.ERROR
        msg += '\nPatch "{0}" requires another refresh after issues are resolved.'.format(name)
    else:
        eflags = cmd_result.WARNING if (highest_ecode > 0 and msg) else cmd_result.OK
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, '', msg)

def do_set_patch_description(patch, text):
    if not patch_db.is_writable():
        return cmd_result.Result(cmd_result.ERROR, '', 'Database is not writable')
    patch_db.do_set_patch_description(patch, text)
    console.LOG.append_entry('set patch "{0}" description:\n"{1}"'.format(patch, text))
    return cmd_result.Result(cmd_result.OK, '', '')

def do_add_files_to_patch(file_list, patch=None, force=False):
    if patch is None:
        console.LOG.start_cmd('add {0}'.format(utils.file_list_to_string(file_list)))
        patch = patch_db.get_top_patch_name()
    else:
        console.LOG.start_cmd('add --patch={0} {1}'.format(patch, utils.file_list_to_string(file_list)))
    for already_in_patch in patch_db.get_filenames_in_patch(patch, file_list):
        file_list.remove(already_in_patch)
        console.LOG.append_stdout('File "{0}" already in patch "{1}". Ignored.\n'.format(already_in_patch, patch))
    eflags = cmd_result.OK
    msg = ''
    overlaps = patch_db.get_filelist_overlap_data(file_list, patch)
    if len(overlaps.uncommitted) > 0:
        if force:
            console.LOG.append_stderr('Uncommitted SCM changes in the following files:\n')
            for filename in sorted(overlaps.uncommitted):
                console.LOG.append_stderr('\t{0}\n'.format(filename))
            console.LOG.append_stderr('have been incorporated.\n')
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE
            msg += 'The following files have uncommitted SCM changes:\n'
            for filename in sorted(overlaps.uncommitted):
                msg += '\t{0}\n'.format(filename)
    if len(overlaps.unrefreshed) > 0:
        if force:
            console.LOG.append_stderr('Unrefreshed changes changes in the following files:\n')
            for filename in sorted(overlaps.unrefreshed):
                console.LOG.append_stderr('\t{0}\n'.format(filename))
            console.LOG.append_stderr('have been incorporated.\n')
        else:
            eflags = cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH
            msg += 'The following files have unrefreshed changes (in an applied patch):\n'
            for filename in sorted(overlaps.unrefreshed):
                msg += '\t{0} : in patch "{1}"\n'.format(filename, overlaps.unrefreshed[filename])
    if eflags is not cmd_result.OK:
        console.LOG.append_stderr(msg)
        console.LOG.end_cmd()
        return cmd_result.Result(eflags, '', msg)
    for filename in file_list:
        patch_db.add_file_to_patch(patch, filename, force=force)
        console.LOG.append_stdout('File "{0}" added to patch "{1}".\n'.format(filename, patch))
    console.LOG.end_cmd()
    if force:
        ws_event.notify_events(ws_event.FILE_ADD|ws_event.PATCH_REFRESH)
    else:
        ws_event.notify_events(ws_event.FILE_ADD)
    return cmd_result.Result(eflags, '', '')

def do_drop_files_from_patch(file_list, patch=None):
    if patch is None:
        console.LOG.start_cmd('drop {0}'.format(utils.file_list_to_string(file_list)))
        patch = patch_db.get_top_patch_name()
    else:
        console.LOG.start_cmd('drop --patch={0} {1}'.format(patch, utils.file_list_to_string(file_list)))
    for filename in file_list:
        patch_db.do_drop_file_fm_patch(patch, filename)
        console.LOG.append_stdout('File "{0}" dropped from patch "{1}".\n'.format(filename, patch))
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.FILE_DEL)
    return cmd_result.Result(cmd_result.OK, '', '')

def is_pushable():
    if not patch_db.is_readable():
        return False
    return patch_db.is_pushable()

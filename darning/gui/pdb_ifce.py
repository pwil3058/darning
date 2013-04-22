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

'''GUI interface to patch_db'''
import os
import pango

from darning import rctx
from darning import patch_db
from darning import cmd_result
from darning import fsdb
from darning import utils

# patch_db commands that don't need wrapping
from darning.patch_db import find_base_dir

from darning.gui import ws_event
from darning.gui import console

class ReportContext(object):
    class OutFile(object):
        @staticmethod
        def write(text):
            console.LOG.append_stdout(text)
    class ErrFile(object):
        def __init__(self):
            self.text = ''
        def write(self, text):
            self.text += text
            console.LOG.append_stderr(text)
    def __init__(self):
        self.stdout = self.OutFile()
        self.stderr = self.ErrFile()
    @property
    def message(self):
        return self.stderr.text
    def reset(self):
        self.stderr.text = ''

RCTX = ReportContext()
rctx.reset(RCTX.stdout, RCTX.stderr)

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
    RCTX.reset()
    console.LOG.start_cmd(_('initialize {0}\n').format(os.getcwd()))
    console.LOG.append_stdin('"{0}"\n'.format(description))
    eflags = patch_db.do_create_db(description)
    console.LOG.end_cmd()
    return cmd_result.Result(eflags, RCTX.message)

def get_in_progress():
    return patch_db.is_readable() and patch_db.get_applied_patch_count() > 0

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
            self.base_dir.add_file(parts, item.status, item.related_file)
        self.decorate_dirs()

def get_file_db(patch=None):
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    return FileDb(patch_db.get_patch_file_table(patch))

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

def get_filepaths_in_top_patch(filepaths=None):
    '''
    Return the names of the files in the top patch.
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    if not patch_db.is_readable():
        return []
    return patch_db.get_filepaths_in_patch(patchname=None, filepaths=filepaths)

def get_filepaths_in_named_patch(patchname, filepaths=None):
    '''
    Return the names of the files in the named patch.
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    if not patch_db.is_readable():
        return []
    return patch_db.get_filepaths_in_patch(patchname=patchname, filepaths=filepaths)

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

def get_top_patch_for_file(filepath):
    if not patch_db.is_readable():
        return None
    return patch_db.get_top_patch_for_file(filepath)

def get_kept_patch_names():
    if not patch_db.is_readable():
        return []
    return patch_db.get_kept_patch_names()

def get_extdiff_files_for(filepath, patchname):
    if not patch_db.is_readable():
        return None
    if patchname is None:
        patchname = patch_db.get_top_patch_for_file(filepath)
    return patch_db.get_extdiff_files_for(filepath, patchname)

def get_reconciliation_paths(filepath):
    if not patch_db.is_readable():
        return None
    return patch_db.get_reconciliation_paths(filepath)

def get_outstanding_changes_below_top():
    if not patch_db.is_readable():
        return None
    return patch_db.get_outstanding_changes_below_top()

def do_create_new_patch(patchname, descr):
    RCTX.reset()
    console.LOG.start_cmd(_('new patch "{0}"\n').format(patchname))
    console.LOG.append_stdin('"{0}"\n'.format(descr))
    eflags = patch_db.do_create_new_patch(patchname, descr)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_CREATE|ws_event.PATCH_PUSH)
    return cmd_result.Result(eflags, RCTX.message)

def do_rename_patch(patchname, newname):
    RCTX.reset()
    console.LOG.start_cmd(_('rename patch "{0}" to "{1}"\n').format(patchname, newname))
    eflags = patch_db.do_rename_patch(patchname, newname)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(eflags, RCTX.message)

def do_restore_patch(patchname, as_patchname=''):
    RCTX.reset()
    if not as_patchname:
        as_patchname = patchname
        console.LOG.start_cmd(_('restore "{0}"\n').format(patchname))
    else:
        console.LOG.start_cmd(_('restore "{0}" as "{1}"\n').format(patchname, as_patchname))
    eflags = patch_db.do_restore_patch(patchname, as_patchname)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_CREATE)
    return cmd_result.Result(eflags, RCTX.message)

def do_push_next_patch(absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd('push\n')
    eflags = patch_db.do_apply_next_patch(absorb=absorb, force=force)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_PUSH|ws_event.FILE_CHANGES)
    return cmd_result.Result(eflags, RCTX.message)

def do_pop_top_patch():
    RCTX.reset()
    console.LOG.start_cmd('pop\n')
    eflags = patch_db.do_unapply_top_patch()
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_POP|ws_event.FILE_CHANGES)
    return cmd_result.Result(eflags, RCTX.message)

def do_refresh_overlapped_files(file_list):
    RCTX.reset()
    console.LOG.start_cmd('refresh --files {0}\n'.format(utils.file_list_to_string(file_list)))
    eflags = patch_db.do_refresh_overlapped_files(file_list)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, RCTX.message)

def do_refresh_patch(patchname=None):
    RCTX.reset()
    if patchname is None:
        console.LOG.start_cmd('refresh\n')
    else:
        console.LOG.start_cmd('refresh {0}\n'.format(patchname))
    eflags = patch_db.do_refresh_patch(patchname)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_REFRESH)
    return cmd_result.Result(eflags, RCTX.message)

def do_remove_patch(patchname):
    RCTX.reset()
    console.LOG.start_cmd('remove patch: {0}\n'.format(patchname))
    eflags =patch_db.do_remove_patch(patchname)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_DELETE)
    return cmd_result.Result(eflags, RCTX.message)

def do_set_patch_description(patchname, text):
    RCTX.reset()
    console.LOG.start_cmd('set patch description: {0}\n'.format(patchname))
    console.LOG.append_stdin(_('"{0}"\n').format(text))
    eflags = patch_db.do_set_patch_description(patchname, text)
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(eflags, RCTX.message)

def do_set_series_description(text):
    RCTX.reset()
    console.LOG.start_cmd(_('set series description\n'))
    console.LOG.append_stdin(_('"{0}"\n').format(text))
    eflags = patch_db.do_set_series_description(text)
    console.LOG.end_cmd()
    return cmd_result.Result(eflags, RCTX.message)

def do_set_patch_guards(patchname, guards_str):
    RCTX.reset()
    console.LOG.start_cmd(_('set guards "{0}" {1}\n').format(patchname, guards_str))
    eflags = patch_db.do_set_patch_guards_fm_str(patchname, guards_str)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(eflags, RCTX.message)

def do_select_guards(guards_str):
    RCTX.reset()
    console.LOG.start_cmd(_('select {0}\n').format(guards_str))
    eflags = patch_db.do_select_guards(guards_str.split())
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_MODIFY)
    return cmd_result.Result(eflags, RCTX.message)

def do_add_files_to_top_patch(filepaths, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd('add {0}\n'.format(utils.file_list_to_string(filepaths)))
    eflags = patch_db.do_add_files_to_top_patch(filepaths, absorb=absorb, force=force)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        if (absorb or force):
            ws_event.notify_events(ws_event.FILE_ADD|ws_event.PATCH_REFRESH)
        else:
            ws_event.notify_events(ws_event.FILE_ADD)
    return cmd_result.Result(eflags, RCTX.message)

def do_delete_files_in_top_patch(filepaths):
    RCTX.reset()
    console.LOG.start_cmd('delete "{0}"\n'.format(utils.file_list_to_string(filepaths)))
    eflags = patch_db.do_delete_files_in_top_patch(filepaths)
    ws_event.notify_events(ws_event.FILE_DEL)
    return cmd_result.Result(eflags, RCTX.message)

def do_copy_file_to_top_patch(filepath, as_filepath, overwrite=False):
    RCTX.reset()
    console.LOG.start_cmd('copy "{0}" "{1}"\n'.format(filepath, as_filepath))
    eflags = patch_db.do_copy_file_to_top_patch(filepath, as_filepath, overwrite=overwrite)
    ws_event.notify_events(ws_event.FILE_ADD)
    return cmd_result.Result(eflags, RCTX.message)

def do_rename_file_in_top_patch(filepath, new_filepath, force=False, overwrite=False):
    RCTX.reset()
    console.LOG.start_cmd('rename "{0}" "{1}"\n'.format(filepath, new_filepath))
    eflags = patch_db.do_rename_file_in_top_patch(filepath, new_filepath, force=force, overwrite=overwrite)
    ws_event.notify_events(ws_event.FILE_ADD|ws_event.FILE_DEL)
    return cmd_result.Result(eflags, RCTX.message)

def do_drop_files_from_patch(filepaths, patch=None):
    RCTX.reset()
    if patch is None:
        console.LOG.start_cmd('drop {0}\n'.format(utils.file_list_to_string(filepaths)))
    else:
        console.LOG.start_cmd(_('drop --patch={0} {1}\n').format(patch, utils.file_list_to_string(filepaths)))
    eflags = patch_db.do_drop_files_fm_patch(patch, filepaths)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.FILE_DEL|ws_event.PATCH_MODIFY)
    return cmd_result.Result(eflags, RCTX.message)

def do_duplicate_patch(patchname, as_patchname, newdescription):
    RCTX.reset()
    console.LOG.start_cmd(_('duplicate patch "{0}" as "{1}"\n').format(patchname, as_patchname))
    console.LOG.append_stdin('"{0}"\n'.format(newdescription))
    eflags = patch_db.do_duplicate_patch(patchname, as_patchname, newdescription)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_CREATE)
    return cmd_result.Result(eflags, RCTX.message)

def do_import_patch(epatch, as_patchname, overwrite=False):
    RCTX.reset()
    if overwrite:
        console.LOG.start_cmd(_('import --overwrite "{0}" as "{1}"\n').format(epatch.source_name, as_patchname))
    else:
        console.LOG.start_cmd(_('import "{0}" as "{1}"\n').format(epatch.source_name, as_patchname))
    eflags = patch_db.do_import_patch(epatch, as_patchname, overwrite=overwrite)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.PATCH_CREATE|ws_event.PATCH_PUSH)
    return cmd_result.Result(eflags, RCTX.message)

def do_export_patch_as(patchname, patch_filename, force=False, overwrite=False):
    RCTX.reset()
    options = '' if not force else '--force '
    options += '' if not overwrite else '--overwrite '
    console.LOG.start_cmd(_('export {0}"{1}" as "{2}"\n').format(options, patchname, patch_filename))
    eflags = patch_db.do_export_patch_as(patchname, patch_filename, force=force, overwrite=overwrite)
    console.LOG.end_cmd()
    return cmd_result.Result(eflags, RCTX.message)

def do_fold_epatch(epatch, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd(_('fold --file "{0}"\n').format(epatch.source_name))
    eflags = patch_db.do_fold_epatch(epatch, absorb=absorb, force=force)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.FILE_CHANGES)
    return cmd_result.Result(eflags, RCTX.message)

def do_fold_named_patch(patchname, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd(_('fold --patch "{0}"\n').format(patchname))
    eflags = patch_db.do_fold_named_patch(patchname, absorb=absorb, force=force)
    console.LOG.end_cmd()
    if cmd_result.is_less_than_error(eflags):
        ws_event.notify_events(ws_event.FILE_CHANGES|ws_event.PATCH_DELETE)
    return cmd_result.Result(eflags, RCTX.message)

def do_scm_absorb_applied_patches():
    RCTX.reset()
    console.LOG.start_cmd('absorb\n')
    eflags = patch_db.do_scm_absorb_applied_patches()
    console.LOG.end_cmd()
    # notify events regardless of return value as partial success is possible
    ws_event.notify_events(ws_event.PATCH_POP|ws_event.FILE_CHANGES)
    return cmd_result.Result(eflags, RCTX.message)

def is_pushable():
    if not patch_db.is_readable():
        return False
    return patch_db.is_pushable()

def is_poppable():
    return get_in_progress()

def is_top_patch(patchname):
    if not patch_db.is_readable():
        return False
    return patch_db.is_top_patch(patchname)

def is_blocked_by_guard(patchname):
    if not patch_db.is_readable():
        return False
    return patch_db.is_blocked_by_guard(patchname)

def is_readable():
    return patch_db.is_readable()

def is_writable():
    return patch_db.is_writable()

def is_absorbable():
    return patch_db.is_absorbable()

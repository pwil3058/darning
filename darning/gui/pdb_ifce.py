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
from itertools import ifilter

import pango

from ..cmd_result import CmdResult, CmdFailure

from .. import rctx
from .. import patch_db
from .. import fsdb
from .. import utils
from .. import pm_ifce

# patch_db commands that don't need wrapping
from ..patch_db import find_base_dir

from . import ws_event
from . import console

in_valid_pgnd = False
pgnd_is_mutable = False

def init(*args, **kwargs):
    global in_valid_pgnd
    global pgnd_is_mutable
    root = find_base_dir(remember_sub_dir=False)
    if root:
        os.chdir(root)
        result = open_db()
        in_valid_pgnd = is_readable()
        pgnd_is_mutable = is_writable()
        if in_valid_pgnd:
            from . import config
            config.PgndPathTable.append_saved_pgnd(root)
    else:
        in_valid_pgnd = False
        pgnd_is_mutable = False
        result = CmdResult.ok()
    return result

def new_playground(description, pgdir=None):
    global in_valid_pgnd, pgnd_is_mutable
    if pgdir is not None:
        result = chdir(pgdir)
        if not result.is_ok:
            return result
    if in_valid_pgnd:
        return CmdResult.warning( _("Already initialized"))
    result = do_initialization(description)
    if not result.is_ok:
        return result
    result = open_db()
    in_valid_pgnd = is_readable()
    pgnd_is_mutable = is_writable()
    if in_valid_pgnd:
        from . import config
        config.PgndPathTable.append_saved_pgnd(os.getcwd())
        ws_event.notify_events(ifce.NEW_PM)
    return result

def do_chdir(new_dir=None):
    global in_valid_pgnd, pgnd_is_mutable
    close_db()
    if new_dir:
        try:
            os.chdir(new_dir)
        except OSError as err:
            import errno
            ecode = errno.errorcode[err.errno]
            emsg = err.strerror
            open_db()
            in_valid_pgnd = is_readable()
            pgnd_is_mutable = is_writable()
            return CmdResult.error(stderr='%s: "%s" :%s' % (ecode, new_dir, emsg))
    return init()

class ReportContext(object):
    class OutFile(object):
        def __init__(self):
            self.text = ''
        def write(self, text):
            self.text += text
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
        return "\n".join([self.stdout.text, self.stderr.text])
    def reset(self):
        self.stdout.text = ''
        self.stderr.text = ''

RCTX = ReportContext()
rctx.reset(RCTX.stdout, RCTX.stderr)

def open_db():
    result = patch_db.load_db(lock=True)
    if result is True:
        return CmdResult.ok()
    return CmdResult.error(stderr=str(result) + '\n')

def close_db():
    '''Close the patch database if it is open'''
    if patch_db.is_readable():
        patch_db.release_db()

def _map_do(ecode):
    return CmdResult(ecode, RCTX.stdout.text, RCTX.stderr.text)

def do_initialization(description):
    '''Create a patch database in the current directory'''
    RCTX.reset()
    console.LOG.start_cmd(_('initialize {0}\n').format(os.getcwd()))
    console.LOG.append_stdin('"{0}"\n'.format(description))
    result = _map_do(patch_db.do_create_db(description))
    console.LOG.end_cmd()
    return result

def get_in_progress():
    return patch_db.is_readable() and patch_db.get_applied_patch_count() > 0

def get_applied_patch_count():
    return patch_db.get_applied_patch_count()

def get_all_patches_data():
    if not patch_db.is_readable():
        return []
    return patch_db.get_patch_table_data()

def get_selected_guards():
    if not patch_db.is_readable():
        return set()
    return patch_db.get_selected_guards()

class PatchListDataOld(object):
    def __init__(self, **kwargs):
        self._patches_data = get_all_patches_data()
        self._selected_guards = get_selected_guards()
    def __getattr__(self, name):
        # We have total control of the database so this always current
        if name == "is_current": return True
        if name == "selected_guards": return self._selected_guards
    def iter_patches(self):
        for patch_data in self._patches_data:
            yield patch_data

class PatchListData(pm_ifce.PatchListData):
    def _finalize(self, pdt):
        self._patches_data, self._selected_guards = pdt
    def _get_data_text(self, h):
        patches_data = get_all_patches_data()
        selected_guards = get_selected_guards()
        # the only thing that can really change unexpectably is the patch state BUT ...
        for patch_data in patches_data:
            h.update(str(patch_data))
        h.update(str(selected_guards))
        return (patches_data, selected_guards)

def get_patch_list_data():
    return PatchListData()

def get_patch_description(patch):
    if not patch_db.is_readable():
        raise CmdFailure(_('Database is unreadable'))
    return patch_db.get_patch_description(patch)

def get_series_description():
    if not patch_db.is_readable():
        raise CmdFailure(_('Database is unreadable'))
    return patch_db.get_series_description()

status_deco_map = {
    None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
    patch_db.FileData.Presence.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
    patch_db.FileData.Presence.REMOVED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
    patch_db.FileData.Presence.EXTANT: fsdb.Deco(pango.STYLE_NORMAL, "black"),
}

def get_status_deco(status):
    return status_deco_map[status.presence if status else None]

def get_status_icon(status, is_dir):
    import gtk
    from . import icons
    if is_dir:
        return gtk.STOCK_DIRECTORY
    elif status.validity == patch_db.FileData.Validity.REFRESHED:
        return icons.STOCK_FILE_REFRESHED
    elif status.validity == patch_db.FileData.Validity.NEEDS_REFRESH:
        return icons.STOCK_FILE_NEEDS_REFRESH
    elif status.validity == patch_db.FileData.Validity.UNREFRESHABLE:
        return icons.STOCK_FILE_UNREFRESHABLE
    else:
        return gtk.STOCK_FILE

class PatchFileDb(fsdb.GenericChangeFileDb):
    class FileDir(fsdb.GenericChangeFileDb.FileDir):
        def _calculate_status(self):
            if not self._status_set:
                validity = patch_db.FileData.Validity.REFRESHED
            else:
                validity = max([s.validity for s in list(self._status_set)])
            return patch_db.FileData.Status(None, validity)
        def dirs_and_files(self, hide_clean=False, **kwargs):
            if hide_clean:
                dirs = ifilter((lambda x: x.status.validity), self._subdirs_data)
                files = ifilter((lambda x: x.status.validity), self._files_data)
            else:
                dirs = iter(self._subdirs_data)
                files = iter(self._files_data)
            return (dirs, files)
    def __init__(self, patch_name=None):
        self._patch_name = patch_name
        fsdb.GenericChangeFileDb.__init__(self)
    @property
    def is_current(self):
        import hashlib
        h = hashlib.sha1()
        self._get_patch_data_text(h)
        return h.digest() == self._db_hash_digest
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_patch_file_table(self._patch_name)
        h.update(str(patch_status_text))
        return patch_status_text
    def _iterate_file_data(self, pdt):
        for item in pdt:
            yield item

class CombinedPatchFileDb(PatchFileDb):
    def _get_patch_data_text(self, h):
        patch_status_text = patch_db.get_combined_patch_file_table()
        h.update(str(patch_status_text))
        return patch_status_text

def get_patch_file_db(patch):
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    return PatchFileDb(patch)

def get_top_patch_file_db(patch=None):
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    return PatchFileDb(None)

def get_combined_patch_file_db():
    if not patch_db.is_readable():
        return fsdb.NullFileDb()
    return CombinedPatchFileDb()

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

# TODO: improve "do" start_cmd strings
def do_create_new_patch(patchname, descr):
    RCTX.reset()
    console.LOG.start_cmd(_('new patch "{0}"\n').format(patchname))
    console.LOG.append_stdin('"{0}"\n'.format(descr))
    result = _map_do(patch_db.do_create_new_patch(patchname, descr))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_NEW_PATCH|pm_ifce.E_PUSH)
    return result

def do_rename_patch(patchname, newname):
    RCTX.reset()
    console.LOG.start_cmd(_('rename patch "{0}" to "{1}"\n').format(patchname, newname))
    result = _map_do(patch_db.do_rename_patch(patchname, newname))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_MODIFY_PATCH)
    return result

def do_restore_patch(patchname, as_patchname=''):
    RCTX.reset()
    if not as_patchname:
        as_patchname = patchname
        console.LOG.start_cmd(_('restore "{0}"\n').format(patchname))
    else:
        console.LOG.start_cmd(_('restore "{0}" as "{1}"\n').format(patchname, as_patchname))
    result = _map_do(patch_db.do_restore_patch(patchname, as_patchname))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_NEW_PATCH)
    return result

def do_push_next_patch(absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd('push\n')
    result = _map_do(patch_db.do_apply_next_patch(absorb=absorb, force=force))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_PUSH)
    return result

def do_pop_top_patch():
    RCTX.reset()
    console.LOG.start_cmd('pop\n')
    result = _map_do(patch_db.do_unapply_top_patch())
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_POP)
    return result

def do_refresh_overlapped_files(file_list):
    RCTX.reset()
    console.LOG.start_cmd('refresh --files {0}\n'.format(utils.quoted_join(file_list)))
    result = _map_do(patch_db.do_refresh_overlapped_files(file_list))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_PATCH_REFRESH)
    return result

def do_refresh_patch(patchname=None):
    RCTX.reset()
    if patchname is None:
        console.LOG.start_cmd('refresh\n')
    else:
        console.LOG.start_cmd('refresh {0}\n'.format(patchname))
    result = _map_do(patch_db.do_refresh_patch(patchname))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_PATCH_REFRESH)
    return result

def do_remove_patch(patchname):
    RCTX.reset()
    console.LOG.start_cmd('remove patch: {0}\n'.format(patchname))
    eflags =patch_db.do_remove_patch(patchname)
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_DELETE_PATCH)
    return result

def do_set_patch_description(patchname, text):
    RCTX.reset()
    console.LOG.start_cmd('set patch description: {0}\n'.format(patchname))
    console.LOG.append_stdin(_('"{0}"\n').format(text))
    result = _map_do(patch_db.do_set_patch_description(patchname, text))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_MODIFY_PATCH)
    return result

def do_set_series_description(text):
    RCTX.reset()
    console.LOG.start_cmd(_('set series description\n'))
    console.LOG.append_stdin(_('"{0}"\n').format(text))
    result = _map_do(patch_db.do_set_series_description(text))
    console.LOG.end_cmd()
    return result

def do_set_patch_guards(patchname, guards_str):
    RCTX.reset()
    console.LOG.start_cmd(_('set guards "{0}" {1}\n').format(patchname, guards_str))
    result = _map_do(patch_db.do_set_patch_guards_fm_str(patchname, guards_str))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_MODIFY_PATCH)
    return result

def do_select_guards(guards_str):
    RCTX.reset()
    console.LOG.start_cmd(_('select {0}\n').format(guards_str))
    result = _map_do(patch_db.do_select_guards(guards_str.split()))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_MODIFY_GUARDS)
    return result

def do_add_files_to_top_patch(filepaths, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd('add {0}\n'.format(utils.quoted_join(filepaths)))
    result = _map_do(patch_db.do_add_files_to_top_patch(filepaths, absorb=absorb, force=force))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        if (absorb or force):
            ws_event.notify_events(pm_ifce.E_FILE_ADDED|pm_ifce.E_PATCH_REFRESH)
        else:
            ws_event.notify_events(pm_ifce.E_FILE_ADDED)
    return result

def do_delete_files_in_top_patch(filepaths):
    RCTX.reset()
    console.LOG.start_cmd('delete "{0}"\n'.format(utils.quoted_join(filepaths)))
    result = _map_do(patch_db.do_delete_files_in_top_patch(filepaths))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_FILE_DELETED)
    return result

def do_copy_file_to_top_patch(filepath, as_filepath, overwrite=False):
    RCTX.reset()
    console.LOG.start_cmd('copy "{0}" "{1}"\n'.format(filepath, as_filepath))
    result = _map_do(patch_db.do_copy_file_to_top_patch(filepath, as_filepath, overwrite=overwrite))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_FILE_ADDED)
    return result

def do_rename_file_in_top_patch(filepath, new_filepath, force=False, overwrite=False):
    RCTX.reset()
    console.LOG.start_cmd('rename "{0}" "{1}"\n'.format(filepath, new_filepath))
    result = _map_do(patch_db.do_rename_file_in_top_patch(filepath, new_filepath, force=force, overwrite=overwrite))
    console.LOG.end_cmd()
    ws_event.notify_events(pm_ifce.E_FILE_ADDED|pm_ifce.E_FILE_DELETED)
    return result

def do_drop_files_from_patch(filepaths, patch=None):
    RCTX.reset()
    if patch is None:
        console.LOG.start_cmd('drop {0}\n'.format(utils.quoted_join(filepaths)))
    else:
        console.LOG.start_cmd(_('drop --patch={0} {1}\n').format(patch, utils.quoted_join(filepaths)))
    result = _map_do(patch_db.do_drop_files_fm_patch(patch, filepaths))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_FILE_DELETED|pm_ifce.E_DELETE_PATCH)
    return result

def do_duplicate_patch(patchname, as_patchname, newdescription):
    RCTX.reset()
    console.LOG.start_cmd(_('duplicate patch "{0}" as "{1}"\n').format(patchname, as_patchname))
    console.LOG.append_stdin('"{0}"\n'.format(newdescription))
    result = _map_do(patch_db.do_duplicate_patch(patchname, as_patchname, newdescription))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_NEW_PATCH)
    return result

def do_import_patch(epatch, as_patchname, overwrite=False):
    RCTX.reset()
    if overwrite:
        console.LOG.start_cmd(_('import --overwrite "{0}" as "{1}"\n').format(epatch.source_name, as_patchname))
    else:
        console.LOG.start_cmd(_('import "{0}" as "{1}"\n').format(epatch.source_name, as_patchname))
    result = _map_do(patch_db.do_import_patch(epatch, as_patchname, overwrite=overwrite))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_NEW_PATCH|pm_ifce.E_PUSH)
    return result

def do_export_patch_as(patchname, patch_filename, force=False, overwrite=False):
    RCTX.reset()
    options = '' if not force else '--force '
    options += '' if not overwrite else '--overwrite '
    console.LOG.start_cmd(_('export {0}"{1}" as "{2}"\n').format(options, patchname, patch_filename))
    result = _map_do(patch_db.do_export_patch_as(patchname, patch_filename, force=force, overwrite=overwrite))
    console.LOG.end_cmd()
    return result

def do_fold_epatch(epatch, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd(_('fold --file "{0}"\n').format(epatch.source_name))
    result = _map_do(patch_db.do_fold_epatch(epatch, absorb=absorb, force=force))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_FILE_CHANGES)
    return result

def do_fold_named_patch(patchname, absorb=False, force=False):
    RCTX.reset()
    console.LOG.start_cmd(_('fold --patch "{0}"\n').format(patchname))
    result = _map_do(patch_db.do_fold_named_patch(patchname, absorb=absorb, force=force))
    console.LOG.end_cmd()
    if result.is_less_than_error:
        ws_event.notify_events(pm_ifce.E_FILE_CHANGES|pm_ifce.E_DELETE_PATCH)
    return result

def do_scm_absorb_applied_patches():
    RCTX.reset()
    console.LOG.start_cmd('absorb\n')
    result = _map_do(patch_db.do_scm_absorb_applied_patches())
    console.LOG.end_cmd()
    # notify events regardless of return value as partial success is possible
    ws_event.notify_events(pm_ifce.E_POP)
    return result

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

def all_applied_patches_refreshed():
    return patch_db.all_applied_patches_refreshed()

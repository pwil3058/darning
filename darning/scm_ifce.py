### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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

'''
Provide an interface to SCM controlling source on which patches sit
'''

from aipoed import enotify

E_FILE_ADDED, E_FILE_DELETED, E_FILE_MODIFIED, E_FILE_CHANGES = enotify.new_event_flags_and_mask(3)
E_FILE_MOVED = E_FILE_ADDED|E_FILE_DELETED

E_INDEX_MOD, E_COMMIT, E_BACKOUT, E_BRANCH, E_TAG, E_PUSH, E_PULL, E_INIT, E_CLONE, E_STASH, E_CS_CHANGES = enotify.new_event_flags_and_mask(10)

E_CHECKOUT, E_BISECT, E_MERGE, E_UPDATE, E_WD_CHANGES = enotify.new_event_flags_and_mask(4)

E_PGND_RC_CHANGED, E_USER_RC_CHANGED, E_RC_CHANGED = enotify.new_event_flags_and_mask(2)

E_LOG = enotify.new_event_flag()
E_REMOTE = enotify.new_event_flag()

_BACKEND = {}
_MISSING_BACKEND = {}

def add_back_end(newifce):
    if newifce.is_available:
        _BACKEND[newifce.name] = newifce
    else:
        _MISSING_BACKEND[newifce.name] = newifce

def backend_requirements():
    msg = _('No back ends are available. SCM systems:') + os.linesep
    for key in list(_MISSING_BACKEND.keys()):
        msg += '\t' + _MISSING_BACKEND[key].requires() + os.linesep
    msg += _("are the ones that are usnderstood.")
    return msg

def report_backend_requirements(parent=None):
    dialogue.main_window.inform_user(backend_requirements(), parent=parent)

def avail_backends():
    return list(_BACKEND.keys())

def playground_type(dir_path=None):
    # TODO: cope with nested playgrounds of different type and go for closest
    # TODO: give preference to quilt if both found to allow quilt to be used on hg?
    for bname in list(_BACKEND.keys()):
        if _BACKEND[bname].dir_is_in_valid_pgnd(dir_path):
            return bname
    return None

def get_ifce(dir_path=None):
    pgt = playground_type(dir_path)
    return _NULL_BACKEND if pgt is None else _BACKEND[pgt]

def create_new_playground(pgnd_dir, backend):
    return _BACKEND[backend].do_init_dir(pgnd_dir)

def clone_repo_as(repo_path, dir_path, backend):
    return _BACKEND[backend].do_clone_as(repo_path, dir_path)

class DummyTableData:
    is_current = True
    def reset(self):
        return self
    @staticmethod
    def iter_rows():
        for row in []:
            yield row

class _NULL_BACKEND:
    name = "os"
    cmd_label = "null"
    in_valid_pgnd = False
    @staticmethod
    def copy_clean_version_to(filepath, target_name):
        '''
        Copy a clean version of the named file to the specified target
        '''
        assert False, "Should not be called for null interface"
    @staticmethod
    def do_import_patch(patch_filepath):
        '''
        Copy a clean version of the named file to the specified target
        '''
        assert False, "Should not be called for null interface"
    @staticmethod
    def get_author_name_and_email():
        return None
    @staticmethod
    def get_branches_table_data():
        return DummyTableData()
    @staticmethod
    def get_log_table_data():
        return DummyTableData()
    @staticmethod
    def get_commit_message(commit=None):
        return None
    @staticmethod
    def get_commit_show(commit):
        return None
    @staticmethod
    def get_diff(*args):
        return ""
    @staticmethod
    def get_extension_enabled(extension):
        return False
    @staticmethod
    def get_file_status_digest():
        '''
        Get the Sha1 digest of the SCM view of the files' status
        '''
        return None
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        '''
        Get the subset of files which have uncommitted SCM changes.  If files
        is None assume all files in current directory.
        '''
        return []
    @staticmethod
    def get_heads_data():
        return []
    @staticmethod
    def get_history_data(rev=None, maxitems=None):
        return []
    @staticmethod
    def get_index_file_db():
        from aipoed.gui import fsdb
        return fsdb.NullFileDb()
    @staticmethod
    def get_parents_data(rev=None):
        return []
    @staticmethod
    def get_path_table_data():
        return []
    @staticmethod
    def get_playground_root():
        return None
    @staticmethod
    def get_remotes_table_data():
        return DummyTableData()
    @staticmethod
    def get_revision(filepath=None):
        '''
        Return the SCM revision for the named file or the whole playground
        if the filepath is None
        '''
        return None
    @staticmethod
    def get_stashes_table_data():
        return DummyTableData()
    @staticmethod
    def get_tags_table_data():
        return DummyTableData()
    @staticmethod
    def get_ws_file_db():
        '''
        Get the SCM view of the current directory
        '''
        from aipoed.gui import fsdb
        return fsdb.OsFileDb()
    @staticmethod
    def is_ready_for_import():
        '''
        Is the SCM in a position to accept an import?
        '''
        return (False, _("No (or unsupported) underlying SCM."))

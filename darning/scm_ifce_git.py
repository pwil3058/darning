### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
### Copyright (C) 2011 Jeff King <peff@peff.net>
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

'''SCM interface for Git (git)'''

import errno
import pango
import os
import re

from darning import runext
from darning import scm_ifce
from darning import fsdb
from darning import utils
from darning import patchlib
from darning import cmd_result

class FileStatus(object):
    UNMODIFIED = '  '
    WD_ONLY_MODIFIED = ' M'
    WD_ONLY_DELETED = ' D'
    MODIFIED = 'M '
    MODIFIED_MODIFIED = 'MM'
    MODIFIED_DELETED = 'MD'
    ADDED = 'A '
    ADDED_MODIFIED = 'AM'
    ADDED_DELETED = 'AD'
    DELETED = 'D '
    DELETED_MODIFIED = 'DM'
    RENAMED = 'R '
    RENAMED_MODIFIED = 'RM'
    RENAMED_DELETED = 'RD'
    COPIED = 'C '
    COPIED_MODIFIED = 'CM'
    COPIED_DELETED = 'CD'
    UNMERGED = 'UU'
    UNMERGED_ADDED = 'AA'
    UNMERGED_ADDED_US = 'AU'
    UNMERGED_ADDED_THEM = 'UA'
    UNMERGED_DELETED = 'DD'
    UNMERGED_DELETED_US = 'DU'
    UNMERGED_DELETED_THEM = 'DA'
    NOT_TRACKED = '??'
    IGNORED = '!!'
    MODIFIED_LIST = [
            # TODO: review order of modified set re directory decoration
            # order is preference order for directory decoration based on contents' states
            WD_ONLY_MODIFIED, WD_ONLY_DELETED,
            MODIFIED_MODIFIED, MODIFIED_DELETED,
            ADDED_MODIFIED, ADDED_DELETED,
            DELETED_MODIFIED,
            RENAMED_MODIFIED, RENAMED_DELETED,
            COPIED_MODIFIED, COPIED_DELETED,
            UNMERGED,
            UNMERGED_ADDED, UNMERGED_ADDED_US, UNMERGED_ADDED_THEM,
            UNMERGED_DELETED, UNMERGED_DELETED_US, UNMERGED_DELETED_THEM,
            MODIFIED, ADDED, DELETED, RENAMED, COPIED,
         ]
    MODIFIED_SET = set(MODIFIED_LIST)
    CLEAN_SET = set([UNMODIFIED, MODIFIED, ADDED, DELETED, RENAMED, COPIED,])

WD_DECO_MAP = {
        None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
        FileStatus.UNMODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "black"),
        FileStatus.WD_ONLY_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.WD_ONLY_DELETED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
        FileStatus.MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.MODIFIED_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.MODIFIED_DELETED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
        FileStatus.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
        FileStatus.ADDED_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.ADDED_DELETED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
        FileStatus.DELETED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
        FileStatus.DELETED_MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.RENAMED: fsdb.Deco(pango.STYLE_ITALIC, "pink"),
        FileStatus.RENAMED_MODIFIED: fsdb.Deco(pango.STYLE_ITALIC, "blue"),
        FileStatus.RENAMED_DELETED: fsdb.Deco(pango.STYLE_ITALIC, "red"),
        FileStatus.COPIED: fsdb.Deco(pango.STYLE_ITALIC, "green"),
        FileStatus.COPIED_MODIFIED: fsdb.Deco(pango.STYLE_ITALIC, "blue"),
        FileStatus.COPIED_DELETED: fsdb.Deco(pango.STYLE_ITALIC, "red"),
        FileStatus.UNMERGED: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_ADDED: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_ADDED_US: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_ADDED_THEM: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_DELETED: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_DELETED_US: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.UNMERGED_DELETED_THEM: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.NOT_TRACKED: fsdb.Deco(pango.STYLE_ITALIC, "cyan"),
        FileStatus.IGNORED: fsdb.Deco(pango.STYLE_ITALIC, "grey"),
    }

_FILE_DATA_RE = re.compile(r'(("([^"]+)")|(\S+))( -> (("([^"]+)")|(\S+)))?')

def get_git_file_data(string):
    match = _FILE_DATA_RE.match(string[3:])
    name = match.group(3) if match.group(3) else match.group(4)
    if match.group(5):
        extradata = fsdb.RFD(extradatamatch.group(8) if match.group(8) else match.group(9), '->')
    else:
        extradata = None
    return fsdb.Data(name, string[:2], extradata)

class GitDecoDir(fsdb.GenDir):
    def __init__(self):
        fsdb.GenDir.__init__(self)
    def _new_dir(self):
        return GitDecoDir()
    def _update_own_status(self):
        for status in FileStatus.MODIFIED_LIST:
            if status in self.status_set:
                self.status = status
                return
        self.status = FileStatus.UNMODIFIED
    def _is_hidden_dir(self, dkey):
        status = self.subdirs[dkey].status
        if status not in FileStatus.MODIFIED_SET:
            return dkey[0] == '.' or status == FileStatus.IGNORED
        return False
    def _is_hidden_file(self, fdata):
        if fdata.status not in FileStatus.MODIFIED_SET:
            return fdata.name[0] == '.' or fdata.status == FileStatus.IGNORED
        return False

class WDFileDB(fsdb.OsSnapshotFileDb):
    DIR_TYPE = GitDecoDir
    def __init__(self):
        fsdb.OsSnapshotFileDb.__init__(self, default_status=FileStatus.UNMODIFIED)
        result = runext.run_cmd(['git', 'status', '--porcelain', '--ignored', '--untracked=all'])
        if result.ecode != 0:
            return
        self.tree_hash.update(result.stdout)
        for line in result.stdout.splitlines():
            filepath, status, related_file_data = get_git_file_data(line)
            assert not os.path.isdir(filepath)
            self.base_dir.add_file(fsdb.split_path(filepath), status, related_file_data)
            if related_file_data is not None:
                result = runext.run_cmd(['git', 'status', '--porcelain', '--', related_file_data.path])
                status = result.stdout[:2] if (result.ecode == 0 and result.stdout) else None
                self.base_dir.add_file(fsdb.split_path(related_file_data.path), status, fsdb.RFD(filepath, '<-'))
        self.base_dir.update_status()
    def is_current(self):
        h = self._get_current_tree_hash()
        result = runext.run_cmd(['git', 'status', '--porcelain', '--ignored', '--untracked=all'])
        if result.ecode == 0:
            h.update(result.stdout)
        return h.digest() == self.tree_hash.digest()

class Git(object):
    name = 'git'
    @staticmethod
    def is_valid_repo():
        '''Is the currend working directory in a valid git repository?'''
        try:
            result = runext.run_cmd(['git', 'config', '--local', '-l'])
        except OSError as edata:
            if edata.errno == errno.ENOENT:
                return False
            else:
                raise
        return result.ecode == 0
    @staticmethod
    def get_revision(filepath=None):
        '''
        Return the SCM revision for the named file or the whole playground
        if the filepath is None
        '''
        cmd = ['git', 'show',]
        if filepath:
            cmd.append(filepath)
        result = runext.run_cmd(cmd)
        assert result.ecode == 0
        return result.stdout.splitlines()[0][7:]
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        '''
        Get the subset of files which have uncommitted git changes.  If files
        is None assume all files in current directory.
        '''
        cmd = ['git', 'status', '--porcelain', '--untracked-files=no',]
        if files:
            cmd += files
        result = runext.run_cmd(cmd)
        assert result.ecode == 0
        return [line[3:] for line in result.stdout.splitlines()]
    @staticmethod
    def get_file_db():
        '''
        Get the SCM view of the current directory
        '''
        return WDFileDB()
    @staticmethod
    def get_status_deco(status):
        '''
        Get the SCM specific decoration for the given status
        '''
        return WD_DECO_MAP[status]
    @staticmethod
    def is_clean(status):
        '''
        Does this status indicate a clean object?
        '''
        return status == FileStatus.UNMODIFIED
    @staticmethod
    def copy_clean_version_to(filepath, target_name):
        '''
        Copy a clean version of the named file to the specified target
        '''
        result = runext.run_cmd(['git', 'cat-file', 'blob', 'HEAD:{}'.format(filepath)])
        assert result.ecode == 0
        if result.stdout:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write(result.stdout)
    @staticmethod
    def do_import_patch(patch_filepath):
        ok_to_import, msg = Git.is_ready_for_import()
        if not ok_to_import:
            return runext.Result(-1, '', msg)
        epatch = patchlib.Patch.parse_text_file(patch_filepath)
        description = epatch.get_description()
        if not description:
            return runext.Result(-1, '', 'Empty description')
        result = runext.run_cmd(['git', 'apply', patch_filepath])
        if result.ecode != 0:
            return result
        result = runext.run_cmd(['git', 'add'] + epatch.get_file_paths(1))
        if result.ecode != 0:
            return result
        return runext.run_cmd(['git', 'commit', '-q', '-m', description])
    @staticmethod
    def is_ready_for_import():
        result = runext.run_cmd(['hg', 'qtop'])
        if not index_is_empty():
            return cmd_result.Result(False, _('Index is NOT empty\n'))
        return cmd_result.Result(True, '')

def index_is_empty():
    result = runext.run_cmd(['git', 'status', '--porcelain', '--untracked-files=no'])
    for line in result.stdout.splitlines():
        if line[0] != ' ':
            return False
    return True


scm_ifce.add_back_end(Git)

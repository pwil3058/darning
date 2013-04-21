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

from darning import runext
from darning import scm_ifce
from darning import fsdb
from darning import utils
from darning import patchlib

class Git(object):
    name = 'git'
    class FileStatus(object):
        MODIFIED = 'M'
        ADDED = 'A'
        DELETED = 'D'
        RENAMED = 'R'
        COPIED = 'C'
        UNMODIFIED = ' '
        NOT_TRACKED = '?'
        IGNORED = '!'
        UNMERGED = 'U'
        MODIFIED_SET = set([MODIFIED, ADDED, DELETED, RENAMED, COPIED, UNMERGED])
    deco_map = {
            None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
            FileStatus.UNMODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "black"),
            FileStatus.MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
            FileStatus.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
            FileStatus.DELETED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
            FileStatus.UNMERGED: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
            FileStatus.RENAMED: fsdb.Deco(pango.STYLE_ITALIC, "pink"),
            FileStatus.COPIED: fsdb.Deco(pango.STYLE_ITALIC, "green"),
            FileStatus.NOT_TRACKED: fsdb.Deco(pango.STYLE_ITALIC, "cyan"),
            FileStatus.IGNORED: fsdb.Deco(pango.STYLE_ITALIC, "grey"),
        }
    class FileDb(object):
        def __init__(self):
            pass
        def _is_not_hidden_file(self, name, status):
            if status == Git.FileStatus.IGNORED:
                return False
            elif status in Git.FileStatus.MODIFIED_SET:
                return True
            return name[0] != '.'
        def _get_dir_state(self, dirpath):
            result = runext.run_cmd(['git', 'status', '--porcelain', '--ignored', dirpath])
            lines = result.stdout.splitlines()
            if len(lines) == 1 and os.path.samefile(lines[0][3:], dirpath):
                return lines[0][1]
            status_set = set()
            for line in lines:
                working_status = line[1]
                if working_status in [Git.FileStatus.NOT_TRACKED, Git.FileStatus.IGNORED] and line[3:] != dirpath:
                    continue
                status_set.add(working_status)
            if len(status_set) == 0:
                return Git.FileStatus.UNMODIFIED
            for status in Git.FileStatus.MODIFIED_SET:
                if status in status_set:
                    return status
            return Git.FileStatus.UNMODIFIED
        def dir_contents(self, dirpath, show_hidden=False):
            if not dirpath:
                dirpath = os.curdir
            dirs = []
            file_status_map = {}
            elements = os.listdir(dirpath)
            for element in elements:
                epath = os.path.join(dirpath, element)
                if os.path.isdir(epath):
                    status = self._get_dir_state(epath)
                    if self._is_not_hidden_file(element, status) or show_hidden:
                        dirs.append(fsdb.Data(element, status, None))
                else:
                    file_status_map[element] = Git.FileStatus.UNMODIFIED
            result = runext.run_cmd(['git', 'status', '--porcelain', '--ignored', dirpath + os.sep])
            for line in result.stdout.splitlines():
                filepath = line[3:]
                if os.path.isdir(filepath):
                     continue
                dirpart, name = os.path.split(filepath)
                if not name or (dirpart and dirpart != dirpath):
                    continue
                file_status_map[name] = line[1]
            files = []
            for name, status in file_status_map.items():
                if self._is_not_hidden_file(name, status) or show_hidden:
                    files.append(fsdb.Data(name, status, None))
            dirs.sort()
            files.sort()
            return (dirs, files)
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
        return Git.FileDb()
    @staticmethod
    def get_status_deco(status):
        '''
        Get the SCM specific decoration for the given status
        '''
        return Git.deco_map[status]
    @staticmethod
    def is_clean(status):
        '''
        Does this status indicate a clean object?
        '''
        return status == Git.FileStatus.UNMODIFIED
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
        if not index_is_empty():
            return runext.Result(-1, '', _('Index is NOT empty\n'))
        epatch = patchlib.Patch.parse_text_file(patch_filepath)
        result = runext.run_cmd(['git', 'apply', patch_filepath])
        if result.ecode != 0:
            return result
        result = runext.run_cmd(['git', 'add'] + epatch.get_file_paths(1))
        if result.ecode != 0:
            return result
        return runext.run_cmd(['git', 'commit', '-q', '-m', epatch.get_description()])

def index_is_empty():
    result = runext.run_cmd(['git', 'status', '--porcelain', '--untracked-files=no'])
    for line in result.stdout.splitlines():
        if line[0] != ' ':
            return False
    return True


scm_ifce.add_back_end(Git)

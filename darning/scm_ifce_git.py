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
import hashlib

from darning import runext
from darning import scm_ifce
from darning import utils
from darning import patchlib
from darning import cmd_result
from . import fsdb_git

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
        return fsdb_git.WsFileDb()
    @staticmethod
    def get_file_status_digest():
        result = runext.run_cmd(['git', 'status', '--porcelain', '--ignored', '--untracked=all'])
        if result.ecode == 0:
            return hashlib.sha1(result.stdout).digest()
        return None
    @staticmethod
    def get_status_deco(status):
        '''
        Get the SCM specific decoration for the given status
        '''
        return fsdb_git.WD_DECO_MAP[status]
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

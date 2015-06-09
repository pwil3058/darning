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

from .cmd_result import CmdResult
from .utils import singleton

from . import runext
from . import scm_ifce
from . import utils
from . import patchlib
from . import fsdb_git

@singleton
class Git(object):
    name = 'git'
    @staticmethod
    def __getattr__(attr_name):
        if attr_name == "is_available":
            '''Is the currend working directory in a valid git repository?'''
            try:
                return runext.run_cmd(["git", "version"]).is_ok
            except OSError as edata:
                if edata.errno == errno.ENOENT:
                    return False
                else:
                    raise
        if attr_name == "in_valid_pgnd": return runext.run_cmd(["git", "config", "--local", "-l"]).is_ok
    @staticmethod
    def dir_is_in_valid_pgnd(dir_path=None):
        '''Is the current working (or specified) directory in a valid git repository?'''
        if dir_path:
            orig_dir_path = os.getcwd()
            os.chdir(dir_path)
        result = runext.run_cmd(["git", "config", "--local", "-l"])
        if dir_path:
            os.chdir(orig_dir_path)
        return result.is_ok
    @staticmethod
    def get_revision(filepath=None):
        '''
        Return the SCM revision for the named file or the whole playground
        if the filepath is None
        '''
        cmd = ['git', 'show',]
        if filepath:
            cmd.append(filepath)
        return runext.run_get_cmd(cmd).stdout.splitlines()[0][7:]
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        '''
        Get the subset of files which have uncommitted git changes.  If files
        is None assume all files in current directory.
        '''
        cmd = ['git', 'status', '--porcelain', '--untracked-files=no',]
        if files:
            cmd += files
        return [line[3:] for line in runext.run_get_cmd(cmd).splitlines()]
    @staticmethod
    def get_file_db():
        '''
        Get the SCM view of the current directory
        '''
        return fsdb_git.WsFileDb()
    @staticmethod
    def get_file_status_digest():
        stdout = runext.run_get_cmd(['git', 'status', '--porcelain', '--ignored', '--untracked=all'], default=None)
        return None if stdout is None else hashlib.sha1(stdout).digest()
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
        contents = runext.run_get_cmd(['git', 'cat-file', 'blob', 'HEAD:{}'.format(filepath)])
        if contents:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write(contents)
    @classmethod
    def do_import_patch(cls, patch_filepath):
        ok_to_import, msg = cls.is_ready_for_import()
        if not ok_to_import:
            return CmdResult.error(stderr=msg)
        epatch = patchlib.Patch.parse_text_file(patch_filepath)
        description = epatch.get_description()
        if not description:
            return CmdResult.error(stderr='Empty description')
        result = runext.run_cmd(['git', 'apply', patch_filepath])
        if not result.is_less_than_error:
            return result
        result = runext.run_cmd(['git', 'add'] + epatch.get_file_paths(1))
        if not result.is_less_than_error:
            return result
        return runext.run_cmd(['git', 'commit', '-q', '-m', description])
    @staticmethod
    def is_ready_for_import():
        return (True, '') if index_is_empty() else (False, _('Index is NOT empty\n'))
    @staticmethod
    def get_author_name_and_email():
        import email
        email_addr = runext.run_get_cmd(['git', 'config', "user.email"], default=None)
        if not email_addr:
            email_addr = os.environ.get("GIT_AUTHOR_EMAIL", None)
        if not email_addr:
            return None
        name = runext.run_cmd(['git', 'config', "user.name"], default=None)
        if not name:
            name = utils.get_first_in_envar(["GIT_AUTHOR_NAME", "LOGNAME", "GECOS"], default=_("unknown"))
        return email.utils.formataddr(name, email_addr)

def index_is_empty():
    stdout = runext.run_get_cmd(['git', 'status', '--porcelain', '--untracked-files=no'])
    for line in stdout.splitlines():
        if line[0] != ' ':
            return False
    return True

scm_ifce.add_back_end(Git())

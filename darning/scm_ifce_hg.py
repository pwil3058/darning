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

'''SCM interface for Mercurial (hg)'''

import errno
import pango

from darning import runext
from darning import scm_ifce
from darning import fsdb
from darning import utils
from darning import cmd_result

class FileStatus(object):
    MODIFIED = 'M'
    ADDED = 'A'
    REMOVED = 'R'
    CLEAN = 'C'
    MISSING = '!'
    NOT_TRACKED = '?'
    IGNORED = 'I'
    ORIGIN = ' '
    UNRESOLVED = 'U'
    MODIFIED_SET = set([MODIFIED, ADDED, REMOVED, MISSING, UNRESOLVED])

WD_DECO_MAP = {
        None: fsdb.Deco(pango.STYLE_NORMAL, "black"),
        FileStatus.CLEAN: fsdb.Deco(pango.STYLE_NORMAL, "black"),
        FileStatus.MODIFIED: fsdb.Deco(pango.STYLE_NORMAL, "blue"),
        FileStatus.ADDED: fsdb.Deco(pango.STYLE_NORMAL, "darkgreen"),
        FileStatus.REMOVED: fsdb.Deco(pango.STYLE_NORMAL, "red"),
        FileStatus.UNRESOLVED: fsdb.Deco(pango.STYLE_NORMAL, "magenta"),
        FileStatus.MISSING: fsdb.Deco(pango.STYLE_ITALIC, "pink"),
        FileStatus.NOT_TRACKED: fsdb.Deco(pango.STYLE_ITALIC, "cyan"),
        FileStatus.IGNORED: fsdb.Deco(pango.STYLE_ITALIC, "grey"),
    }

class FileDir(fsdb.GenDir):
    def __init__(self):
        fsdb.GenDir.__init__(self)
    def _new_dir(self):
        return FileDir()
    def _update_own_status(self):
        if FileStatus.UNRESOLVED in self.status_set:
            self.status = FileStatus.UNRESOLVED
        elif self.status_set & FileStatus.MODIFIED_SET:
            self.status = FileStatus.MODIFIED
        elif self.status_set == set([FileStatus.IGNORED]):
            self.status = FileStatus.IGNORED
        elif self.status_set in [set([FileStatus.NOT_TRACKED]), set([FileStatus.NOT_TRACKED, FileStatus.IGNORED])]:
            self.status = FileStatus.NOT_TRACKED
        elif self.status_set in [set([FileStatus.CLEAN]), set([FileStatus.CLEAN, FileStatus.IGNORED])]:
            self.status = FileStatus.CLEAN
    def _is_hidden_dir(self, dkey):
        status = self.subdirs[dkey].status
        if status not in [FileStatus.UNRESOLVED, FileStatus.MODIFIED]:
            return dkey[0] == '.' or status == FileStatus.IGNORED
        return False
    def _is_hidden_file(self, fdata):
        if fdata.status not in FileStatus.MODIFIED_SET:
            return fdata.name[0] == '.' or fdata.status == FileStatus.IGNORED
        return False

class FileDb(fsdb.GenFileDb):
    DIR_TYPE = FileDir
    def __init__(self, file_list, unresolved_file_list):
        fsdb.GenFileDb.__init__(self)
        lfile_list = len(file_list)
        index = 0
        while index < lfile_list:
            item = file_list[index]
            index += 1
            filepath = item[2:]
            status = item[0]
            related_file = None
            if status == FileStatus.ADDED and index < lfile_list:
                if file_list[index][0] == FileStatus.ORIGIN:
                    related_file = fsdb.RFD(file_list[index][2:], fsdb.Relation.COPIED_FROM)
                    index += 1
            elif filepath in unresolved_file_list:
                status = FileStatus.UNRESOLVED
            parts = fsdb.split_path(filepath)
            self.base_dir.add_file(parts, status, related_file)

class Mercurial(object):
    name = 'hg'
    @staticmethod
    def is_valid_repo():
        '''Is the currend working directory in a valid hg repository?'''
        try:
            result = runext.run_cmd(['hg', 'root'])
        except OSError as edata:
            if edata.errno == errno.ENOENT:
                return False
            else:
                raise
        return result.ecode == 0 and result.stdout
    @staticmethod
    def get_revision(filepath=None):
        '''
        Return the SCM revision for the named file or the whole playground
        if the filepath is None
        '''
        cmd = ['hg', 'log', '-l', '1', '--follow', '--template', '"{node}"']
        if filepath:
            cmd.append(filepath)
        result = runext.run_cmd(cmd)
        if filepath is None:
            assert result.ecode == 0
        elif result.ecode != 0:
            return None
        return result.stdout
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        '''
        Get the subset of files which have uncommitted hg changes.  If files
        is None assume all files in current directory.
        '''
        cmd = ['hg', 'status', '-mardn'] + (files if files else ['.'])
        result = runext.run_cmd(cmd)
        assert result.ecode == 0
        return result.stdout.splitlines()
    @staticmethod
    def get_file_db():
        '''
        Get the SCM view of the current directory
        '''
        def unresolved_file_list():
            cmd = ['hg', 'resolve', '--list', '.']
            result = runext.run_cmd(cmd)
            if result.ecode != 0:
                return []
            return [line[2:] for line in result.stdout.splitlines() if line[0] == FileStatus.UNRESOLVED]
        cmd = ['hg', 'status', '-AC', '.']
        result = runext.run_cmd(cmd)
        scm_file_db = FileDb(result.stdout.splitlines(), unresolved_file_list())
        scm_file_db.decorate_dirs()
        return scm_file_db
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
        return status == FileStatus.CLEAN
    @staticmethod
    def copy_clean_version_to(filepath, target_name):
        '''
        Copy a clean version of the named file to the specified target
        '''
        result = runext.run_cmd(['hg', 'cat', filepath])
        assert result.ecode == 0
        if result.stdout:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write(result.stdout)
    @staticmethod
    def do_import_patch(patch_filepath):
        ok_to_import, msg = Mercurial.is_ready_for_import()
        if not ok_to_import:
            return runext.Result(-1, '', msg)
        return runext.run_cmd(['hg', 'import', '-q', patch_filepath])
    @staticmethod
    def is_ready_for_import():
        result = runext.run_cmd(['hg', 'qtop'])
        if result.ecode == 0:
            return cmd_result.Result(False, _('There are "mq" patches applied.'))
        result = runext.run_cmd(['hg', 'parents', '--template', '{rev}\\n'])
        if result.ecode != 0:
            return cmd_result.Result(False, result.stdout + result.stderr)
        elif len(result.stdout.splitlines()) > 1:
            return cmd_result.Result(False, _('There is an incomplete merge in progress.'))
        return cmd_result.Result(True, '')

scm_ifce.add_back_end(Mercurial)

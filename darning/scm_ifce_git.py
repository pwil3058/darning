### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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

"""SCM interface for Git (git)"""

import errno
import gi
gi.require_version("Pango", "1.0")
from gi.repository import Pango
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
from . import enotify

from .gui import ifce

def _do_action_cmd(cmd, success_emask, fail_emask, eflag_modifiers):
    from .gui import console
    # TODO: improve _do_action_cmd() and move to runext
    result = runext.run_cmd_in_console(console.LOG, cmd)
    if result.is_ok:
        if success_emask:
            enotify.notify_events(success_emask)
        if result.stderr:
            return CmdResult.warning(result.stdout, result.stderr)
        else:
            return CmdResult.ok()
    else:
        if fail_emask:
            enotify.notify_events(fail_emask)
        eflags = CmdResult.ERROR
        for tgt_string, suggestion in eflag_modifiers:
            if result.stderr.find(tgt_string) != -1:
                eflags |= suggestion
        return CmdResult(eflags, result.stdout, result.stderr)

class TableData:
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        h = hashlib.sha1()
        pdt = self._get_data_text(h)
        self._db_hash_digest = h.digest()
        self._current_text_digest = None
        self._finalize(pdt)
    def __getattr__(self, name):
        if name == "is_current": return self._is_current()
    def _finalize(self, pdt):
        assert False, "_finalize() must be defined in child"
    def _is_current(self):
        h = hashlib.sha1()
        self._current_text = self._get_data_text(h)
        self._current_text_digest = h.digest()
        return self._current_text_digest == self._db_hash_digest
    def reset(self):
        if self._current_text_digest is None:
            return self.__class__(**self._kwargs)
        if self._current_text_digest != self._db_hash_digest:
            self._db_hash_digest = self._current_text_digest
            self._finalize(self._current_text)
        return self
    def _get_data_text(self, h):
        assert False, "_get_data_text() must be defined in child"
    def iter_rows(self):
        for row in self._rows:
            yield row

class BranchTableData(TableData):
    RE = re.compile("([^ ]+)\s+([a-fA-F0-9]{7}[a-fA-F0-9]*)?\s*([^\s].*)")
    def _get_data_text(self, h):
        all_branches_text = runext.run_get_cmd(["git", "branch", "-v"], default="")
        h.update(all_branches_text.encode())
        merged_branches_text = runext.run_get_cmd(["git", "branch", "--merged"], default="")
        h.update(merged_branches_text.encode())
        return (all_branches_text, merged_branches_text)
    def _finalize(self, pdt):
        all_branches_text, merged_branches_text = pdt
        self._lines = all_branches_text.splitlines()
        self._merged_branches = {line[2:].strip() for line in merged_branches_text.splitlines()}
    def iter_rows(self):
        from .gui.branches import BranchListRow
        for line in self._lines:
            is_current = line[0]
            name, rev, synopsis = self.RE.match(line[2:]).groups()
            is_merged = name in self._merged_branches
            yield BranchListRow(name=name, is_current=is_current, is_merged=is_merged, rev=rev, synopsis=synopsis)

class TagTableData(TableData):
    def _get_data_text(self, h):
        text = runext.run_get_cmd(["git", "tag"], default="")
        h.update(text.encode())
        return text
    def _finalize(self, pdt):
        self._lines = pdt.splitlines()
    def _get_annotation(self, name):
        result = runext.run_cmd(["git", "rev-parse", name])
        result = runext.run_cmd(["git", "cat-file", "-p", result.stdout.strip()])
        if result.stdout.startswith("object"):
            cat_lines = result.stdout.splitlines()
            return cat_lines[5] if len(cat_lines) > 5 else ""
        return ""
    def iter_rows(self):
        from .gui.tags import TagListRow
        for line in self._lines:
            yield TagListRow(name=line, annotation=self._get_annotation(line))

class RemoteRepoTableData(TableData):
    _VREMOTE_RE = re.compile(r"(\S+)\s+(\S+)\s*(\S*)")
    def _get_data_text(self, h):
        text = runext.run_get_cmd(["git", "remote", "-v"], default="")
        h.update(text.encode())
        return text
    def _finalize(self, pdt):
        self._lines = pdt.splitlines()
    def iter_rows(self):
        from .gui.remotes import RemotesListRow
        for i, line in enumerate(self._lines):
            m = self._VREMOTE_RE.match(line)
            if i % 2 == 0:
                name, inbound_url = m.group(1, 2)
            else:
                assert name == m.group(1)
                yield RemotesListRow(name=name, inbound_url=inbound_url, outbound_url=m.group(2))

class LogTableData(TableData):
    def _get_data_text(self, h):
        text = runext.run_get_cmd(["git", "log", "--pretty=format:%H%n%h%n%an%n%cr%n%s"], default="")
        h.update(text.encode())
        return text
    def _finalize(self, pdt):
        self._lines = pdt.splitlines()
    def iter_rows(self):
        from .gui.log import LogListRow
        for i, line in enumerate(self._lines):
            chooser = i % 5
            if chooser == 0:
                commit = line
            elif chooser == 1:
                abbrevcommit = line
            elif chooser == 2:
                author = line
            elif chooser == 3:
                when = line
            else:
                yield LogListRow(commit=commit, abbrevcommit=abbrevcommit, author=author, when=when, subject=line)

@singleton
class Interface:
    name = "git"
    INDEX_DECO_MAP = fsdb_git.INDEX_DECO_MAP
    WD_DECO_MAP = fsdb_git.WD_DECO_MAP
    @staticmethod
    def __getattr__(attr_name):
        if attr_name == "is_available":
            try:
                return runext.run_cmd(["git", "version"]).is_ok
            except OSError as edata:
                if edata.errno == errno.ENOENT:
                    return False
                else:
                    raise
        if attr_name == "in_valid_pgnd": return runext.run_cmd(["git", "config", "--local", "-l"]).is_ok
        raise AttributeError(attr_name)
    @staticmethod
    def copy_clean_version_to(filepath, target_name):
        contents = runext.run_get_cmd(["git", "cat-file", "blob", "HEAD:{}".format(filepath)])
        if contents:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, "w") as fobj:
                fobj.write(contents)
    @staticmethod
    def dir_is_in_valid_pgnd(dir_path=None):
        if dir_path:
            orig_dir_path = os.getcwd()
            os.chdir(dir_path)
        result = runext.run_cmd(["git", "config", "--local", "-l"])
        if dir_path:
            os.chdir(orig_dir_path)
        return result.is_ok
    @staticmethod
    def do_add_files_to_index(file_list, force=False):
        if force:
            cmd = ["git", "add", "-f", "--"] + file_list
        else:
            cmd = ["git", "add", "--"] + file_list
        return _do_action_cmd(cmd, scm_ifce.E_INDEX_MOD|scm_ifce.E_FILE_CHANGES, None, [("Use -f if you really want to add them.", CmdResult.SUGGEST_FORCE)])
    @staticmethod
    def do_checkout_branch(branch):
        cmd = ["git", "checkout", branch]
        return _do_action_cmd(cmd, scm_ifce.E_BRANCH|ifce.E_CHANGE_WD, None, [])
    @staticmethod
    def do_checkout_tag(tag):
        cmd = ["git", "checkout", tag]
        return _do_action_cmd(cmd, scm_ifce.E_TAG|ifce.E_CHANGE_WD, None, [])
    @staticmethod
    def do_clone_as(repo, tgtdir=None):
        cmd = ["git", "clone", repo]
        if tgtdir is not None:
            cmd.append(tgtdir)
        return _do_action_cmd(cmd, scm_ifce.E_CLONE, None, [])
    @staticmethod
    def do_commit_staged_changes(msg):
        cmd = ["git", "commit", "-m", msg]
        return _do_action_cmd(cmd, scm_ifce.E_INDEX_MOD|scm_ifce.E_COMMIT|scm_ifce.E_FILE_CHANGES, None, [])
    @staticmethod
    def do_create_branch(branch, target=None, force=False):
        cmd = ["git", "branch"]
        if force:
            cmd.append("-f")
        cmd.append(branch)
        if target:
            cmd.append(target)
        return _do_action_cmd(cmd, scm_ifce.E_BRANCH, None, [("already exists", CmdResult.SUGGEST_FORCE)])
    @classmethod
    def do_import_patch(cls, patch_filepath):
        ok_to_import, msg = cls.is_ready_for_import()
        if not ok_to_import:
            return CmdResult.error(stderr=msg)
        epatch = patchlib.Patch.parse_text_file(patch_filepath)
        description = epatch.get_description()
        if not description:
            return CmdResult.error(stderr="Empty description")
        result = runext.run_cmd(["git", "apply", patch_filepath])
        if not result.is_less_than_error:
            return result
        result = runext.run_cmd(["git", "add"] + epatch.get_file_paths(1))
        if not result.is_less_than_error:
            return result
        return runext.run_cmd(["git", "commit", "-q", "-m", description])
    @staticmethod
    def do_init_dir(tgtdir=None):
        cmd = ["git", "init"]
        if tgtdir is not None:
            cmd += ["--", tgtdir]
        return _do_action_cmd(cmd, ifce.E_NEW_SCM, None, [])
    @staticmethod
    def do_pull_from_repo(repo=None):
        cmd = ["git", "pull"]
        if repo is not None:
            cmd.append(repo)
        return _do_action_cmd(cmd, scm_ifce.E_PULL, None, [])
    @staticmethod
    def do_push_to_repo(repo=None):
        cmd = ["git", "push"]
        if repo is not None:
            cmd.append(repo)
        return _do_action_cmd(cmd, scm_ifce.E_PUSH, None, [])
    @staticmethod
    def do_remove_files_from_index(file_list):
        cmd = ["git", "reset", "HEAD", "--"] + file_list
        return _do_action_cmd(cmd, scm_ifce.E_INDEX_MOD, None, [])
    @staticmethod
    def do_remove_files_in_index(file_list, force=False):
        if force:
            cmd = ["git", "rm", "-f", "--"] + file_list
        else:
            cmd = ["git", "rm", "--"] + file_list
        return _do_action_cmd(cmd, scm_ifce.E_INDEX_MOD, None, [("or -f to force removal", CmdResult.SUGGEST_FORCE)])
    @staticmethod
    def do_set_tag(tag, annotated=False, msg=None, signed=False, key_id=None, target=None, force=False):
        cmd = ["git", "tag"]
        if force:
            cmd.append("-f")
        if annotated:
            cmd += ["-m", msg]
            if signed:
                cmd.append("-s")
            if key_id:
                cmd += ["-u", key_id]
        cmd.append(tag)
        if target:
            cmd.append(target)
        return _do_action_cmd(cmd, scm_ifce.E_TAG, None, [("already exists", CmdResult.SUGGEST_FORCE)])
    @staticmethod
    def get_author_name_and_email():
        import email
        email_addr = runext.run_get_cmd(["git", "config", "user.email"], default=None)
        if not email_addr:
            email_addr = os.environ.get("GIT_AUTHOR_EMAIL", None)
        if not email_addr:
            return None
        name = runext.run_get_cmd(["git", "config", "user.name"], default=None)
        if not name:
            name = utils.get_first_in_envar(["GIT_AUTHOR_NAME", "LOGNAME", "GECOS"], default=_("unknown"))
        return email.utils.formataddr((name, email_addr))
    @staticmethod
    def get_branches_table_data():
        return BranchTableData()
    @staticmethod
    def get_clean_contents(file_path):
        return runext.run_get_cmd(["git", "cat-file", "blob", "HEAD:{}".format(file_path)], do_rstrip=False, default=None, decode_stdout=False)
    @staticmethod
    def get_log_table_data():
        return LogTableData()
    @staticmethod
    def get_commit_message(commit=None):
        cmd = ["git", "log", "-n", "1", "--pretty=format:%s%n%n%b"]
        if commit:
            cmd.append(commit)
        result = runext.run_cmd(cmd)
        if result.is_ok:
            return result.stdout
        return None
    @staticmethod
    def get_commit_show(commit):
        cmd = ["git", "show", commit]
        result = runext.run_cmd(cmd)
        if result.is_ok:
            return result.stdout
        return None
    @staticmethod
    def get_diff(*args):
        return runext.run_get_cmd(["git", "diff", "--no-ext-diff"] + list(args), do_rstrip=False)
    @staticmethod
    def get_file_status_digest():
        stdout = runext.run_get_cmd(["git", "status", "--porcelain", "--ignored", "--untracked=all"], default=None)
        return None if stdout is None else hashlib.sha1(stdout.encode()).digest()
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        cmd = ["git", "status", "--porcelain", "--untracked-files=no",]
        if files:
            cmd += files
        return [line[3:] for line in runext.run_get_cmd(cmd).splitlines()]
    @staticmethod
    def get_index_file_db():
        return fsdb_git.IndexFileDb()
    @staticmethod
    def get_playground_root():
        if not runext.run_cmd(["git", "config", "--local", "-l"]).is_ok:
            return None
        dirpath = os.getcwd()
        while True:
            if os.path.isdir(os.path.join(dirpath, ".git")):
                return dirpath
            else:
                dirpath, basename = os.path.split(dirpath)
                if not basename:
                    break
        return None
    @staticmethod
    def get_remotes_table_data():
        return RemoteRepoTableData()
    @staticmethod
    def get_revision(filepath=None):
        cmd = ["git", "show",]
        if filepath:
            cmd.append(filepath)
        return runext.run_get_cmd(cmd).stdout.splitlines()[0][7:]
    @staticmethod
    def get_status_deco(status):
        return fsdb_git.WD_DECO_MAP[status]
    @staticmethod
    def get_tags_table_data():
        return TagTableData()
    @staticmethod
    def get_ws_file_db():
        return fsdb_git.WsFileDb()
    @staticmethod
    def is_ready_for_import():
        return (True, "") if index_is_empty() else (False, _("Index is NOT empty\n"))
    @staticmethod
    def launch_difftool(*args):
        return runext.run_cmd_in_bgnd(["git", "difftool", "--noprompt"] + list(args))

def index_is_empty():
    stdout = runext.run_get_cmd(["git", "status", "--porcelain", "--untracked-files=no"])
    for line in stdout.splitlines():
        if line[0] != " ":
            return False
    return True

scm_ifce.add_back_end(Interface())

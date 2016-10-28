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
import hashlib
import re

from .wsm.bab import CmdResult
from .wsm.bab import enotify
from .wsm.bab import runext

from .wsm.bab.decorators import singleton

# Some generalized lambdas for constructing commands
from .wsm.bab.runext import OPTNL_FLAG
from .wsm.bab.runext import OPTNL_FLAGS
from .wsm.bab.runext import OPTNL_FLAG_WITH_ARG
from .wsm.bab.runext import OPTNL_ARG
from .wsm.bab.runext import OPTNL_ARG_LIST

from .wsm.hg_gui import fsdb_hg_mq

from .wsm import scm

from . import scm_ifce
from . import utils

# TODO: replace "rollback" with "commit --amend"

SUGGEST_FORCE_RE = re.compile("(use -f to force|not overwriting - file exists)")
SUGGEST_RENAME_RE = re.compile("already exists")
SUGGEST_MERGE_OR_DISCARD_RE = re.compile("use 'hg merge' or 'hg update -C'")
SUGGEST_DISCARD_RE = re.compile("use 'hg update -C")

SUGGESTION_TABLE = (
    (CmdResult.Suggest.FORCE, lambda x: bool(SUGGEST_FORCE_RE.search(x.stderr))),
    (CmdResult.Suggest.RENAME, lambda x: bool(SUGGEST_RENAME_RE.search(x.stderr))),
    (CmdResult.Suggest.MERGE_OR_DISCARD, lambda x: bool(SUGGEST_MERGE_OR_DISCARD_RE.search(x.stderr))),
    (CmdResult.Suggest.DISCARD, lambda x: bool(SUGGEST_DISCARD_RE.search(x.stderr))),
)

def _run_do_cmd(cmd, input_text=None, sanitize_stderr=None):
    from .wsm.gtx import console
    result = runext.run_cmd_in_console(console=console.LOG, cmd=cmd, input_text=input_text, sanitize_stderr=sanitize_stderr)
    return result.mapped_for_suggestions(SUGGESTION_TABLE)

NOSUCH_RE = re.compile(_("^.*: No such file or directory$\n?"), re.M)

ROOT = lambda : runext.run_get_cmd(["hg", "root"], default=None)
MQ_IN_CHARGE = lambda : runext.run_get_cmd(["hg", "qapplied"], default=False)

_cs_summary_template_lines = \
    [
        "{desc|firstline}",
        "{rev}",
        "{node}",
        "{date|isodate}",
        "{date|age}",
        "{author|person}",
        "{author|email}",
        "{tags}",
        "{branches}",
        "{desc}",
        "",
    ]
CS_SUMMARY_TEMPLATE = "\\n".join(_cs_summary_template_lines)
CS_TABLE_TEMPLATE = "{rev}:{node}:{date|age}:{tags}:{branches}:{author|person}:{desc|firstline}\\n"

def _get_enabled_extensions():
    stdout = runext.run_get_cmd(["hg", "config", "extensions"])
    return [name.split(".")[-1].rstrip() for name, value in (line.split("=") for line in stdout.splitlines()) if not value.lstrip().startswith("!")]

@singleton
class Mercurial(object):
    name = "hg"
    @staticmethod
    def __getattr__(attr_name):
        if attr_name == "is_available":
            '''Is the currend working directory in a valid git repository?'''
            try:
                return runext.run_cmd(["hg", "version"]).is_ok
            except OSError as edata:
                if edata.errno == errno.ENOENT:
                    return False
                else:
                    raise
        if attr_name == "in_valid_pgnd": return runext.run_cmd(["hg", "root"]).is_ok
    @staticmethod
    def dir_is_in_valid_pgnd(dir_path=None):
        '''Is the current working (or specified) directory in a valid hg repository?'''
        if dir_path:
            orig_dir_path = os.getcwd()
            os.chdir(dir_path)
        result = runext.run_cmd(["hg", "root"])
        if dir_path:
            os.chdir(orig_dir_path)
        return result.is_ok
    @staticmethod
    def copy_clean_version_to(file_path, target_name):
        '''
        Copy a clean version of the named file to the specified target
        '''
        contents = runext.run_get_cmd(["hg", "cat", file_path])
        if contents:
            # TODO: should this be conditional on contents not being empty?
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, "w") as fobj:
                fobj.write(contents)
    @staticmethod
    def do_add_files(file_paths, dry_run=False):
        if dry_run:
            return runext.run_cmd(["hg", "add"] + ["-n", "--verbose"] + file_paths).mapped_for_suggestions(self.SUGGESTION_TABLE)
        result = _run_do_cmd(do_add_files.cmd + file_paths)
        enotify.notify_events(scm.E_FILE_ADDED)
        return result
    @staticmethod
    def do_backout(self, rev, msg, merge=False):
        cmd = ["hg", "backout"] + OPTNL_FLAG_WITH_ARG("-m", msg) + OPTNL_FLAG(merge, "--merge") + OPTNL_ARG(rev)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_BACKOUT|scm_files.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_clone_as(dir_path, target=None):
        cmd = ["hg", "clone", dir_path] + OPTNL_ARG(target)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_CLONE)
        return result
    @staticmethod
    def do_commit_change(self, msg, file_paths=None, amend=False):
        cmd = ["hg", "-v", "commit"] + OPTNL_FLAG_WITH_ARG("-m", msg) + OPTNL_FLAG(amend, "--amend") + OPTNL_ARG_LIST(file_paths)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_COMMIT|scm.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_copy_files(file_paths, destn, force=False, dry_run=False):
        cmd = ["hg", "copy"] + FORCE_FLAG(force)
        if dry_run:
            return runext.run_cmd(cmd + ["-n", "--verbose"] + file_paths + [destn]).mapped_for_suggestions(SUGGESTION_TABLE)
        result = _run_do_cmd(cmd + file_paths + [destn])
        enotify.notify_events(scm.E_FILE_ADDED)
        return result
    @classmethod
    def do_import_patch(cls, patch_file_path):
        ok_to_import, msg = cls.is_ready_for_import()
        if not ok_to_import:
            return CmdResult.error(stderr=msg)
        return _run_do_cmd(["hg", "import", "-q", patch_file_path])
    @staticmethod
    def do_init(dir_path=None):
        result = _run_do_cmd(["hg", "init"] + OPTNL_ARG(dir_path))
        enotify.notify_events(scm.E_INIT)
        return result
    @staticmethod
    def do_mark_files_resolved(file_paths):
        cmd = ["hg", "resolve", "--mark"] + file_paths
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_mark_files_unresolved(file_paths):
        cmd = ["hg", "resolve", "--unmark"] + file_paths
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_merge_workspace(rev=None, force=False):
        cmd = ["hg", "merge"] + OPTIONAL_FLAG(force, "-f") + OPTNL_FLAG_WITH_ARG("--rev", rev)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_MERGE)
        return result
    @staticmethod
    def do_move_files(file_paths, destn, force=False, dry_run=False):
        cmd = ["hg", "rename"] + FORCE_FLAG(force)
        if dry_run:
            return runext.run_cmd(cmd + ["-n", "--verbose"] + file_paths + [destn]).mapped_for_suggestions(SUGGESTION_TABLE)
        result = _run_do_cmd(cmd + file_paths + [destn])
        enotify.notify_events(scm.E_FILE_DELETED|scm.E_FILE_ADDED)
        return result
    @staticmethod
    def do_move_tag(tag, rev, msg=None):
        cmd = ["hg", "tag", "-f", "--rev", rev] + OPTNL_FLAG_WITH_ARG("-m", msg) + [tag]
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_TAG)
        return result
    @staticmethod
    def do_pull_from(rev=None, update=False, source=None):
        cmd = ["hg", "pull"] + OPTNL_FLAG(update, "-u") + OPTNL_FLAG_WITH_ARG("--rev", rev) + OPTNL_ARG(source)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_PULL|scm.E_UPDATE if update else scm.E_PULL)
        return result
    @staticmethod
    def do_push_to(rev=None, update=False, path=None):
        cmd = ["hg", "push"] + OPTNL_FLAG(update, "-u") + OPTNL_FLAG_WITH_ARG("--rev", rev) + OPTNL_ARG(path)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_PUSH|scm.E_UPDATE if update else scm.E_PUSH)
        return result
    @staticmethod
    def do_remove_files(file_paths, force=False):
        cmd = ["hg", "remove"] + OPTNL_FLAG(force, "-f") + file_paths
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_FILE_DELETED)
        return result
    @staticmethod
    def do_remove_tag(tag, local=False, msg=None):
        cmd = ["hg", "tag", "--remove"] + OPTNL_FLAG(local, "-l") + OPTNL_FLAG_WITH_ARG("-m", msg) + [tag]
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_TAG)
        return result
    @staticmethod
    def do_resolve_workspace(file_paths=None):
        cmd = ["hg", "resolve"] + OPTNL_FLAG(not file_paths, "--all") + OPTNL_ARG_LIST(file_paths)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_revert_files(file_paths=None, dry_run=False):
        if dry_run:
            cmd = ["hg", "revert", "--n", "--verbose"] + OPTNL_FLAG(not file_paths, "--all") + OPTNL_ARG_LIST(file_paths)
            return runext.run_cmd(cmd).mapped_for_suggestions(self.SUGGESTION_TABLE)
        cmd = ["hg", "revert"] + OPTNL_FLAG(not file_paths, "--all") + OPTNL_ARG_LIST(file_paths)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_FILE_CHANGES)
        return result
    @staticmethod
    def do_rollback_repo():
        # TODO: remove rollback from interface: deprecated and dangerous add amend instead
        result = _run_do_cmd('hg rollback')
        enotify.notify_events(scm.E_CS_CHANGES|scm.E_WD_CHANGES)
        return result
    @staticmethod
    def do_set_branch(branch, force=False):
        cmd = ["hg", "branch"] + OPTNL_FLAG(force, "-f") + [branch]
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_BRANCH)
        return result
    @staticmethod
    def do_set_tag(tag, rev=None, local=False, force=False, msg=None):
        if not tag:
            return CmdResult.ok()
        cmd = ["hg", "tag"] + OPTNL_FLAG(local, "-l") + OPTNL_FLAG(force, "-f") + OPTNL_FLAG_WITH_ARG("--rev", rev) + OPTNL_FLAG_WITH_ARG("--m", msg) + [tag]
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_TAG)
        return result
    @staticmethod
    def do_update_workspace(rev=None, discard=False):
        cmd = ["hg", "update"] + OPTNL_FLAG(discard, "-C") + OPTNL_FLAG_WITH_ARG("--rev", rev)
        result = _run_do_cmd(cmd)
        enotify.notify_events(scm.E_UPDATE)
        return result
    @staticmethod
    def do_verify_repo():
        return _run_do_cmd(["hg", "verify"])
    @staticmethod
    def get_author_name_and_email():
        return runext.run_get_cmd(["hg", "showconfig", "ui.username"], default=None)
    @staticmethod
    def get_branches_data():
        if not ROOT():
            return []
        dre = re.compile("^(\S+)\s*(\d+):")
        cmd = ["hg", "branches"]
        branch_list_iter = ([dat.group(1), int(dat.group(2))] for dat in (dre.match(line) for line in runext.run_get_cmd(cmd).splitlines()) if dat)
        cmd = ["hg", "log", "--template", "{tags}:{date|age}:{author|person}:{desc|firstline}", "--rev"]
        return [branch + runext.run_get_cmd(cmd + [str(branch[1])]).split(":", 3) for branch in branch_list_iter]
    @staticmethod
    def get_clean_contents(file_path):
        return runext.run_get_cmd(["hg", "cat", file_path], do_rstrip=False, default=None, decode_stdout=False)
    @staticmethod
    def get_extension_enabled(extension):
        return extension in _get_enabled_extensions()
    @staticmethod
    def get_file_status_digest():
        h = hashlib.sha1()
        for cmd in [["hg", "resolve", "--list", "."], ["hg", "status", "-AC", "."]]:
            h.update(runext.run_get_cmd(cmd, default="").encode())
        return h.digest()
    @staticmethod
    def get_files_with_uncommitted_changes(files=None):
        '''
        Get the subset of files which have uncommitted hg changes.  If files
        is None assume all files in current directory.
        '''
        cmd = ["hg", "status", "-mardn"] + (list(files) if files else ["."])
        return runext.run_get_cmd(cmd, sanitize_stderr=lambda x: NOSUCH_RE.sub("", x)).splitlines()
    @staticmethod
    def get_heads_data():
        if not ROOT():
            return []
        cmd = ["hg", "heads", "--template", CS_TABLE_TEMPLATE]
        # WORKAROUND: "hg heads" returns 1 with no error message or other output if repository is empty
        return [[int(pdata[0])] + pdata[1:] for pdata in (line.split(":", 6) for line in runext.run_get_cmd(cmd, default="").splitlines())]
    @staticmethod
    def get_history_data(rev=None, maxitems=None):
        if not ROOT():
            return []
        cmd = ["hg", "log", "--template", CS_TABLE_TEMPLATE]
        if maxitems:
            if rev is not None:
                rev2 = max(int(rev) - maxitems + 1, 0)
                cmd += ["--rev", "{0}:{1}".format(int(rev), rev2)]
            else:
                cmd += ["-l", str(maxitems)]
        elif rev is not None:
            cmd += ["--rev", rev]
        return [[int(pdata[0])] + pdata[1:] for pdata in (line.split(":", 6) for line in runext.run_get_cmd(cmd).splitlines())]
    @staticmethod
    def get_parents_data(rev=None):
        cmd = ["hg", "parents", "--template", CS_TABLE_TEMPLATE]
        if rev is None and MQ_IN_CHARGE():
            qbase = "qbase"
        if rev is not None:
            cmd += ["--rev", str(rev)]
        return [[int(pdata[0])] + pdata[1:] for pdata in (line.split(":", 6) for line in runext.run_get_cmd(cmd, default="").splitlines())]
    @staticmethod
    def get_path_table_data():
        path_re = re.compile('^(\S*)\s+=\s+(\S*.*)\s*$')
        cmd = ["hg", "paths"]
        return [[match.group(1), match.group(2)] for match in (path_re.match(line) for line in runext.run_get_cmd(cmd).splitlines()) if match]
    @staticmethod
    def get_playground_root():
        return runext.run_get_cmd(["hg", "root"], default=None)
    @staticmethod
    def get_revision(file_path=None):
        '''
        Return the SCM revision for the named file or the whole playground
        if the file_path is None
        '''
        cmd = ["hg", "log", "-l", "1", "--follow", "--template", "\"{node}\""]
        if file_path:
            cmd.append(file_path)
        revision = runext.run_get_cmd(cmd, default=None)
        if file_path is None:
            assert revision is not None
        return revision
    @staticmethod
    def get_tags_data():
        if not ROOT():
            return []
        dre = re.compile("^(\S+)\s*(\d+):(\S+)\s*(\S*)")
        cmd = ["hg", "-v", "tags"]
        tag_data_iter = (dre.match(line) for line in runext.run_get_cmd(cmd).splitlines())
        tag_list = [[dat.group(1), dat.group(4), int(dat.group(2))] for dat in tag_data_iter if dat]
        cmd = ["hg", "log", "--template", "{rev}:{branches}:{date|age}:{author|person}:{desc|firstline}\\n"]
        lastrev = None
        for tag_data in tag_list:
            if tag_data[2] != lastrev:
                cmd += ["--rev", str(tag_data[2])]
                lastrev = tag_data[2]
        index = 0
        ntags = len(tag_list)
        for line in runext.run_get_cmd(cmd).splitlines():
            fields = line.split(":", 4)
            rev = int(fields[0])
            addon = fields[1:]
            while index < ntags and tag_list[index][2] == rev:
                tag_list[index].extend(addon)
                index += 1
        return tag_list
    @staticmethod
    def get_wd_file_db():
        '''
        Get the SCM view of the current directory
        '''
        return fsdb_hg_mq.WsFileDb()
    @staticmethod
    def is_ready_for_import():
        if runext.run_cmd(["hg", "qtop"]).is_ok:
            return (False, _("There are \"mq\" patches applied."))
        result = runext.run_cmd(["hg", "parents", "--template", "{rev}\\n"])
        if not result.is_ok:
            return (False, result.stdout + result.stderr)
        elif len(result.stdout.splitlines()) > 1:
            return (False, _("There is an incomplete merge in progress."))
        return (True, "")

scm_ifce.add_back_end(Mercurial())

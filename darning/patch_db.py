# Copyright (C) 2015 Peter Williams <peter_ono@users.sourceforge.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""
Implement a patch stack management database
"""

import os
import stat
import pickle
import collections
import shutil
import copy
import difflib
import tempfile
import re
import zlib

from contextlib import contextmanager

from .bab import CmdResult
from .bab import os_utils
from .bab import runext
from .bab import options
from .bab import utils

from .patch_diff import diffs
from .patch_diff import diff_preamble
from .patch_diff import patches

from . import ntuples
from . import rctx as RCTX
from . import mixins
from .scm import scm_ifce

from .pm import PatchState, FileStatus, Presence, Validity, PatchTableRow
from .pm import MERGE_CRE, patch_timestamp_str

options.define("pop", "drop_added_tws", options.Defn(options.str_to_bool, True, _("Remove added trailing white space (TWS) from patch after pop")))
options.define("push", "drop_added_tws", options.Defn(options.str_to_bool, True, _("Remove added trailing white space (TWS) from patch before push")))
options.define("absorb", "drop_added_tws", options.Defn(options.str_to_bool, True, _("Remove added trailing white space (TWS) from patch before absorb")))
options.define("remove", "keep_patch_backup", options.Defn(options.str_to_bool, True, _("Keep back up copies of removed patches.  Facilitates restoration at a later time.")))

# A convenience tuple for sending an original and patched version of something
_O_IP_PAIR = collections.namedtuple("_O_IP_PAIR", ["original_version", "patched_version"])
# A convenience tuple for sending original, patched and stashed versions of something
_O_IP_S_TRIPLET = collections.namedtuple("_O_IP_S_TRIPLET", ["original_version", "patched_version", "stashed_version"])

_DIR_PATH = ".darning.dbd"
_BLOBS_DIR_PATH = os.path.join(_DIR_PATH, "blobs")
_PATCHES_DATA_FILE_PATH = os.path.join(_DIR_PATH, "patches_data")
_BLOB_REF_COUNT_FILE_PATH = os.path.join(_DIR_PATH, "blob_ref_counts")
_DESCRIPTION_FILE_PATH = os.path.join(_DIR_PATH, "description")
_LOCK_FILE_PATH = os.path.join(_DIR_PATH, "lock_db_ng")

def get_blob_dir_path(git_hash):
    """Get path of directory containing the file that contains the
    content associated with "git_hash".
    """
    return os.path.join(_BLOBS_DIR_PATH, git_hash[:2])

def get_blob_path(git_hash):
    """Get path of file containing content associated with "git_hash".
    """
    return os.path.join(_BLOBS_DIR_PATH, git_hash[:2], git_hash[2:])

_SUB_DIR = None

class Failure(object):
    """Report failure"""
    def __init__(self, msg):
        self._bool = False
        self.msg = msg
    def __bool__(self):
        return self._bool
    def __nonzero__(self):
        return self._bool
    def __str__(self):
        return self.msg
    def __repr__(self):
        return _("Failure({0})").format(self.msg)

def rel_subdir(file_path):
    return file_path if _SUB_DIR is None else os.path.relpath(file_path, _SUB_DIR)

def rel_basedir(file_path):
    if os.path.isabs(file_path):
        file_path = os.path.relpath(file_path)
    elif _SUB_DIR is not None:
        file_path = os.path.join(_SUB_DIR, file_path)
    return file_path

# TODO: do we really need is_valid_dir_name()
_VALID_DIR_NAME_CRE = re.compile(r"^[ \w.-]+$")
ALLOWED_DIR_NAME_CHARS_MSG = _("Only alphanumeric characters plus \" \", \"_\", \"-\" and \".\" are allowed.")

def is_valid_dir_name(dirname):
    return _VALID_DIR_NAME_CRE.match(dirname) is not None

# Probably don't need this but hold on to it for the time being
#def prepend_subdir(file_paths):
    #for findex in range(len(file_paths)):
        #file_paths[findex] = rel_basedir(file_paths[findex])
    #return file_paths

def iter_prepending_subdir(file_paths):
    if _SUB_DIR is None:
        for file_path in file_paths:
            yield file_path
    else:
        for file_path in file_paths:
            yield rel_basedir(file_path)

def iter_with_subdir(file_paths):
    if _SUB_DIR is None:
        for file_path in file_paths:
            yield (file_path, file_path)
    else:
        for file_path in file_paths:
            yield (rel_basedir(file_path), file_path)

def find_base_dir(dir_path=None, remember_sub_dir=False):
    """Find the nearest directory above that contains a database"""
    global _SUB_DIR # pylint: disable=global-statement
    dir_path = os.getcwd() if dir_path is None else os.path.abspath(os.path.expanduser(dir_path))
    subdir_parts = []
    while True:
        # NB: we look for the lock file to distinguish from legacy playgrounds
        if os.path.isfile(os.path.join(dir_path, _LOCK_FILE_PATH)):
            _SUB_DIR = None if not subdir_parts else os.path.join(*subdir_parts)
            return dir_path
        else:
            dir_path, basename = os.path.split(dir_path)
            if not basename:
                break
            if remember_sub_dir:
                subdir_parts.insert(0, basename)
    return None

def _tidy_text(text):
    """Return the given text with any trailing white space removed.
    Also ensure there is a new line at the end of the lastline."""
    tidy_text = ""
    if text: # This will allow text to be None
        for line in text.splitlines():
            tidy_text += re.sub("[ \t]+$", "", line) + "\n"
    return tidy_text

def _do_apply_diff_to_file(filepath, diff, delete_empty=False):
    patch_cmd_hdr = ["patch", "--merge", "--force", "-p1", "--batch", ]
    patch_cmd = patch_cmd_hdr + (["--remove-empty-files", filepath] if delete_empty else [filepath])
    result = runext.run_cmd(patch_cmd, input_text=str(diff).encode())
    # move all but the first line of stdout to stderr
    # drop first line so that reports can be made relative to subdir
    olines = result.stdout.splitlines(True)
    prefix = "{0}: ".format(rel_subdir(filepath))
    # Put file name at start of line so they make sense on their own
    if len(olines) > 1:
        stderr = prefix + prefix.join(olines[1:] + result.stderr.splitlines(True))
    elif result.stderr:
        stderr = prefix + prefix.join(result.stderr.splitlines(True))
    else:
        stderr = ""
    return CmdResult(result.ecode, "", stderr)


class OverlapData(object):
    def __init__(self, unrefreshed=None, uncommitted=None):
        self.unrefreshed = {} if not unrefreshed else unrefreshed
        self.uncommitted = set() if not uncommitted else set(uncommitted)
    def __bool__(self):
        return self.__len__() > 0
    def __len__(self):
        return len(self.unrefreshed) + len(self.uncommitted)
    def report_and_abort(self):
        for filepath in sorted(self.uncommitted):
            rfilepath = rel_subdir(filepath)
            RCTX.stderr.write(_("{0}: file has uncommitted SCM changes.\n").format(rfilepath))
        for filepath in sorted(self.unrefreshed):
            rfilepath = rel_subdir(filepath)
            opatch = self.unrefreshed[filepath]
            RCTX.stderr.write(_("{0}: file has unrefreshed changes in (applied) patch \"{1}\".\n").format(rfilepath, opatch.name))
        RCTX.stderr.write(_("Aborted.\n"))
        return CmdResult.ERROR | CmdResult.Suggest.FORCE_ABSORB_OR_REFRESH if len(self.unrefreshed) > 0 else CmdResult.ERROR | CmdResult.Suggest.FORCE_OR_ABSORB

class SupervisedDictFactory:
    ALLOWED_ITEMS = dict()
    MAY_BE_NONE = frozenset()
    REQUIRED = frozenset()
    DEFAULT_NONE = frozenset()

    @classmethod
    def new_dict(cls, **kwargs):
        nd = dict()
        for key, v_type in cls.ALLOWED_ITEMS.items():
            if key in kwargs:
                if kwargs[key] is None and key not in cls.MAY_BE_NONE:
                    nd[key] = v_type()
                else:
                    nd[key] = kwargs[key]
            elif key in cls.REQUIRED:
                assert False, "{} is a compulsory key for {} dictionaries".format(key, cls)
            elif key in cls.DEFAULT_NONE:
                nd[key] = None
            else:
                nd[key] = v_type()
        assert cls.verify_dict(nd), "{}:\n\t {} produced invalid product:\n\t {}".format(cls, kwargs, nd)
        return nd

    @classmethod
    def verify_dict(cls, candidate_dict):
        if len(cls.ALLOWED_ITEMS) != len(candidate_dict):
            return False
        try:
            for key, v_type in cls.ALLOWED_ITEMS.items():
                if not isinstance(candidate_dict[key], v_type):
                    if key not in cls.MAY_BE_NONE or candidate_dict[key] is not None:
                        return False
        except KeyError:
            return False
        return True

class _DataBaseData(SupervisedDictFactory):
    ALLOWED_ITEMS = {
        "selected_guards" : set,
        "patch_series_data" : list,
        "applied_patches_data" : list,
        "combined_patch_data" : dict,
        "kept_patches" :dict
    }
    MAY_BE_NONE = frozenset(["combined_patch_data"])
    REQUIRED = frozenset()
    DEFAULT_NONE = frozenset(["combined_patch_data"])

class _PatchData(SupervisedDictFactory):
    ALLOWED_ITEMS = {
        "name" : str,
        "description" : str,
        "files_data" : dict,
        "pos_guards" : set,
        "neg_guards" : set
    }
    MAY_BE_NONE = frozenset()
    REQUIRED = frozenset(["name"])
    DEFAULT_NONE = frozenset()

    @staticmethod
    def decrement_ref_counts(patch_data, blob_ref_counts):
        for pfd in patch_data["files_data"].values():
            if pfd["orig"] is not None:
                blob_ref_counts[pfd["orig"]["git_hash"][:2]][pfd["orig"]["git_hash"][2:]] -= 1
            if pfd["darned"] is not None:
                blob_ref_counts[pfd["darned"]["git_hash"][:2]][pfd["darned"]["git_hash"][2:]] -= 1
            if pfd["came_from"] is not None:
                blob_ref_counts[pfd["came_from"]["orig"]["git_hash"][:2]][pfd["came_from"]["orig"]["git_hash"][2:]] -= 1

    @staticmethod
    def clear(patch_data, database):
        for file_data in patch_data["files_data"].values():
            _FileData.release_contents(file_data, database)
        patch_data["files_data"].clear()
        patch_data.clear()

class _CombinedPatchData(SupervisedDictFactory):
    ALLOWED_ITEMS = {"files_data" : dict, "prev" : dict}
    MAY_BE_NONE = frozenset(["prev"])
    REQUIRED = frozenset(["files_data", "prev"])
    DEFAULT_NONE = frozenset(["prev"])

    @classmethod
    def make_new_dict(cls, prev=None):
        files_data = dict() if not prev else {file_path : copy.copy(file_data) for file_path, file_data in prev["files_data"].items()}
        return cls.new_dict(files_data=files_data, prev=prev)

class _DiffData(SupervisedDictFactory):
    """Factory to create/manage persistent diff data in dictionaries"""
    ALLOWED_ITEMS = {"diff_type" : str, "diff_lines" : list}

    @staticmethod
    def fix_trailing_whitespace(diff_data):
        pdiff = diffs.diff_parse_lines(diff_data["diff_lines"])
        result = pdiff.fix_trailing_whitespace()
        if result: # Only need to reset the data if changes were reported
            diff_data["diff_lines"] = list(pdiff.iter_lines())
        return result

    @staticmethod
    def report_trailing_whitespace(diff_data):
        return diffs.diff_parse_lines(diff_data["diff_lines"]).report_trailing_whitespace()

class _FileData(SupervisedDictFactory):
    """Factory to create/manage persistent file data for patches in dictionaries"""
    ALLOWED_ITEMS  = {
        "orig" : dict,
        "darned" : dict,
        "came_from" : dict,
        "renamed_as" : str,
        "diff" : dict,
        "diff_wrt" : dict
    }
    MAY_BE_NONE = frozenset(["orig", "darned", "came_from", "renamed_as", "diff", "diff_wrt"])
    REQUIRED = frozenset(["orig", "darned"])
    DEFAULT_NONE = frozenset(["came_from", "renamed_as", "diff"])

    @staticmethod
    def release_contents(f_data, database):
        database.release_stored_content(f_data["orig"])
        database.release_stored_content(f_data["darned"])
        if f_data["came_from"]:
            database.release_stored_content(f_data["came_from"]["orig"])
        f_data.clear()

class _CombinedFileData(SupervisedDictFactory):
    """Factory to create/manage essential file data for combined patches in dictionaries"""
    ALLOWED_ITEMS = {"top" : dict, "bottom" : dict }
    MAY_BE_NONE = frozenset(["top", "bottom"])

class _EssentialFileData(SupervisedDictFactory):
    """Factory to create/manage essential file data in dictionaries"""
    ALLOWED_ITEMS = {"git_hash" : str, "lstats" : os.stat_result}

    @staticmethod
    def different(efd1, efd2):
        """Are the data different from diff's pointof view?"""
        if efd1 is None:
            return efd2 is not None
        elif efd2 is None:
            return True
        elif efd1["lstats"].st_mode != efd2["lstats"].st_mode:
            return True
        elif efd1["git_hash"] != efd2["git_hash"]:
            return True
        else:
            return False

    @staticmethod
    def permissions(efd):
        """Extract the "permissions" bits for the file"""
        return stat.S_IMODE(efd["lstats"].st_mode)

    @staticmethod
    def timestamp(efd):
        """Create the "timestamp" string for the file"""
        return patch_timestamp_str(efd["lstats"].st_mtime)

class _CameFromData(SupervisedDictFactory):
    """Factory to create/manage "came from' data in dictionaries"""
    ALLOWED_ITEMS = {"file_path" : str, "as_rename" : bool, "orig" : dict}

class DarnIt(Exception):
    def __init__(self, **kwargs):
        Exception.__init__(self)
        self.__kwargs = kwargs
    def __getattr__(self, attr_name):
        return self.__kwargs[attr_name]

class DarnItPatchError(DarnIt): pass
class DarnItPatchExists(DarnItPatchError): pass
class DarnItUnknownPatch(DarnItPatchError): pass
class DarnItPatchIsApplied(DarnItPatchError): pass
class DarnItNoPatchesApplied(DarnItPatchError): pass
class DarnItPatchNeedsRefresh(DarnItPatchError): pass
class DarnItNoPushablePatches(DarnItPatchError): pass
class DarnItPatchOverlapsChanges(DarnItPatchError): pass

class DarnItFileError(DarnIt): pass
class DarnItFileHasUnresolvedMerges(DarnItFileError): pass

def _find_named_patch_in_list(patch_list, patch_name):
    for index, patch in enumerate(patch_list):
        if patch["name"] == patch_name:
            return (index, patch)
    return (None, None)

def _named_patch_is_in_list(patch_list, patch_name):
    for patch in patch_list:
        if patch["name"] == patch_name:
            return True
    return False

def _guards_block_patch(guards, patch):
    if guards:
        if patch["pos_guards"] and not patch["pos_guards"] & guards:
            return True
        elif patch["neg_guards"] & guards:
            return True
    elif patch["pos_guards"]:
        return True
    return False

def _content_has_unresolved_merges(content):
    if content.find(b"\000"):
        return False
    for line in content.decode().splitlines():
        if MERGE_CRE.match(line):
            return True
    return False

def _file_has_unresolved_merges(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f_obj:
            return _content_has_unresolved_merges(f_obj.read())
    else:
        return False

def generate_diff_preamble_lines(file_path, before, after, came_from=None):
    if came_from:
        lines = ["diff --git {0} {1}\n".format(os.path.join("a", came_from["file_path"]), os.path.join("b", file_path)), ]
    else:
        lines = ["diff --git {0} {1}\n".format(os.path.join("a", file_path), os.path.join("b", file_path)), ]
    if before is None:
        if after is not None:
            lines.append("new file mode {0:07o}\n".format(after["lstats"].st_mode))
    elif after is None:
        lines.append("deleted file mode {0:07o}\n".format(before["lstats"].st_mode))
    else:
        if before["lstats"].st_mode != after["lstats"].st_mode:
            lines.append("old mode {0:07o}\n".format(before["lstats"].st_mode))
            lines.append("new mode {0:07o}\n".format(after["lstats"].st_mode))
    if came_from:
        if came_from["as_rename"]:
            lines.append("rename from {0}\n".format(came_from["file_path"]))
            lines.append("rename to {0}\n".format(file_path))
        else:
            lines.append("copy from {0}\n".format(came_from["file_path"]))
            lines.append("copy to {0}\n".format(file_path))
    if before or after:
        hash_line = "index {0}".format(before["git_hash"] if before else "0" *48)
        hash_line += "..{0}".format(after["git_hash"] if after else "0" *48)
        hash_line += " {0:07o}\n".format(after["lstats"].st_mode) if after and before and before["lstats"].st_mode == after["lstats"].st_mode else "\n"
        lines.append(hash_line)
    return lines

def generate_diff_preamble(file_path, before, after, came_from=None):
    return diff_preamble.preamble_parse_lines(generate_diff_preamble_lines(file_path, before, after, came_from))


_DiffCreationData = collections.namedtuple("_DiffCreationData", ["label", "efd", "content", "timestamp"])

def git_hashes_differ(efd1, efd2):
    if efd1 is None:
        return efd2 is not None
    elif efd2 is None:
        return False
    else:
        return efd1["git_hash"] != efd2["git_hash"]

class FileDiffMixin(object):
    def get_diff_before_data(self, as_refreshed=False, with_timestamps=False):
        if self["came_from"]:
            efd = self["came_from"]["orig"]
            label = os.path.join("a", self["came_from"]["file_path"])
        elif self["renamed_as"]:
            efd = None
            label = "/dev/null"
        else:
            efd = self["orig"]
            label = os.path.join("a", self.path) if efd else "/dev/null"
        timestamp = _EssentialFileData.timestamp(efd) if (with_timestamps and efd) else ""
        content = b"" if as_refreshed else self.patch.database.get_content_for(efd)
        return _DiffCreationData(label, efd, content, timestamp)
    def get_diff_after_data(self, as_refreshed=False, with_timestamps=False):
        if as_refreshed or not self.patch.is_applied:
            efd = self["darned"]
            label = os.path.join("b", self.path) if efd else "/dev/null"
            content = b""
        else:
            overlapping_file = self.get_overlapping_file()
            if overlapping_file is not None:
                efd = overlapping_file["orig"]
                content = self.patch.database.get_content_for(efd)
            elif os.path.exists(self.path):
                with open(self.path, "rb") as f_obj:
                    content = f_obj.read()
                efd = _EssentialFileData.new_dict(git_hash=utils.get_git_hash_for_content(content), lstats=os.lstat(self.path))
            else:
                efd = None
                content = b""
            label = os.path.join("b", self.path) if efd else "/dev/null"
        timestamp = _EssentialFileData.timestamp(efd) if (with_timestamps and efd) else ""
        return _DiffCreationData(label, efd, content, timestamp)
    def get_diff_plus(self, as_refreshed=False, with_timestamps=False):
        assert as_refreshed is False or not isinstance(self, CombinedFileData)
        before = self.get_diff_before_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        after = self.get_diff_after_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        preamble = generate_diff_preamble(self.path, before.efd, after.efd, self["came_from"])
        if not as_refreshed and not isinstance(self, CombinedFileData):
            as_refreshed = after.efd and self["darned"] and after.efd["git_hash"] == self["darned"]["git_hash"]
        if as_refreshed:
            diff = diffs.diff_parse_lines(self["diff"]["diff_lines"]) if self["diff"] else None
        elif before.content == after.content:
            diff = None
        elif before.content.find(b"\000") != -1 or after.content.find(b"\000") != -1:
            diff = diffs.GitBinaryDiff.generate_diff(before, after)
        else:
            diff = diffs.UnifiedDiff.generate_diff(before, after)
        diff_plus = patches.DiffPlus([preamble], diff)
        if self["renamed_as"] and after.efd is None:
            diff_plus.trailing_junk.append(_("# Renamed to: {0}\n").format(self["renamed_as"]))
        return diff_plus
    def get_diff_text(self, as_refreshed=False, with_timestamps=False):
        assert as_refreshed is False or not isinstance(self, CombinedFileData)
        before = self.get_diff_before_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        after = self.get_diff_after_data(as_refreshed=as_refreshed, with_timestamps=with_timestamps)
        preamble = "".join(generate_diff_preamble_lines(self.path, before.efd, after.efd, self["came_from"]))
        if not as_refreshed and not isinstance(self, CombinedFileData):
            as_refreshed = after.efd and self["darned"] and after.efd["git_hash"] == self["darned"]["git_hash"]
        if as_refreshed:
            diff = "" if self["diff"] is None else "".join(self["diff"]["diff_lines"])
        elif before.content == after.content:
            diff = ""
        elif before.content.find(b"\000") != -1 or after.content.find(b"\000") != -1:
            diff = "".join(diffs.GitBinaryDiff.generate_diff_lines(before, after))
        else:
            diff = "".join(diffs.UnifiedDiff.generate_diff_lines(before, after))
        trailing_junk = _("# Renamed to: {0}\n").format(self["renamed_as"]) if self["renamed_as"] and after.efd is None else ""
        return preamble + (diff if diff else "") + trailing_junk

class FileData(mixins.PedanticDictProxyMixin, FileDiffMixin):
    PROXIED_ITEMS = _FileData.ALLOWED_ITEMS
    PROXIED_DICT_NAME = "persistent_file_data"
    def __init__(self, file_path, persistent_file_data, patch):
        self.path = file_path
        self.persistent_file_data = persistent_file_data
        self.patch = patch
    def __lt__(self, other):
        return self.path < other.path
    def __gt__(self, other):
        return self.path > other.path
    def clone_for_patch(self, for_patch):
        orig = self.patch.database.clone_stored_content_data(self["orig"])
        darned = self.patch.database.clone_stored_content_data(self["darned"])
        if self["came_from"]:
            cf_orig = self.patch.database.clone_stored_content_data(self["came_from"]["orig"])
            came_from = _CameFromData.new_dict(file_path=self["came_from"]["file_path"], as_rename=self["came_from"]["as_rename"], orig=cf_orig)
        else:
            came_from = None
        clone_data = _FileData.new_dict(orig=orig, darned=darned, came_from=came_from, renamed_as=self["renamed_as"], diff=self["diff"], diff_wrt=self["diff_wrt"])
        return self.__class__(self.path, clone_data, for_patch)
    @classmethod
    def new(cls, file_path, patch, overlaps=OverlapData()):
        # NB: presence of overlaps implies absorb
        orig = patch.database.store_file_content(file_path, overlaps)
        darned = patch.database.clone_stored_content_data(orig)
        return cls(file_path, _FileData.new_dict(orig=orig, darned=darned, diff_wrt=orig), patch)
    @classmethod
    def new_as_copy(cls, file_path, patch, came_from_path):
        # NB: absence of overlaps implies force
        orig = patch.database.store_file_content(file_path)
        came_from = patch.create_came_from_for_copy(came_from_path)
        try:
            shutil.copy2(came_from_path, file_path)
        except OSError:
            patch.database.release_stored_content(orig)
            if came_from:
                patch.database.release_stored_content(came_from["orig"])
            raise
        if came_from:
            darned = patch.database.clone_stored_content_data(came_from["orig"])
            diff_wrt = came_from["orig"]
        else:
            darned = patch.database.clone_stored_content_data(orig)
            diff_wrt = orig
        return cls(file_path, _FileData.new_dict(orig=orig, darned=darned, diff_wrt=diff_wrt, came_from=came_from), patch)
    def copy_contents_from(self, copy_from_path):
        new_came_from = self.patch.create_came_from_for_copy(copy_from_path)
        try:
            shutil.copy2(copy_from_path, self.path)
        except OSError:
            if new_came_from:
                self.patch.database.release_stored_content(new_came_from["orig"])
            raise
        if self["came_from"]:
            self.patch.database.release_stored_content(self["came_from"]["orig"])
        # TODO: handle disable=attribute-defined-outside-init better
        # e.g don't use wrapped names for internal assignments
        # pylint: disable=attribute-defined-outside-init
        self["came_from"] = new_came_from
        if self["came_from"]:
            self.patch.database.release_stored_content(self["darned"])
            self["darned"] = self.patch.database.clone_stored_content_data(self["came_from"]["orig"])
            self["diff_wrt"] = self["came_from"]["orig"]
            self["diff"] = None
    @classmethod
    def new_as_move(cls, file_path, patch, fm_file_data):
        # NB: absence of overlaps implies force
        orig = patch.database.store_file_content(file_path)
        try:
            os.rename(fm_file_data.path, file_path)
        except OSError:
            patch.database.release_stored_content(orig)
            raise
        diff = None
        if fm_file_data["came_from"]:
            came_from = fm_file_data["came_from"]
            diff_wrt = came_from["orig"]
            darned = patch.database.clone_stored_content_data(came_from["orig"])
            if came_from["as_rename"]:
                assert came_from["file_path"] != file_path
                patch.get_file(came_from["file_path"])["renamed_as"] = file_path
            fm_file_data["came_from"] = None
        elif fm_file_data["orig"] is None:
            # this a rename of a file created in this patch
            came_from = None
            darned = patch.database.clone_stored_content_data(fm_file_data["darned"])
            diff_wrt = fm_file_data["diff_wrt"]
            diff = fm_file_data["diff"]
        else:
            came_from = _CameFromData.new_dict(file_path=fm_file_data.path, as_rename=True, orig=patch.database.clone_stored_content_data(fm_file_data["orig"]))
            fm_file_data["renamed_as"] = file_path
            darned = patch.database.clone_stored_content_data(came_from["orig"])
            diff_wrt = came_from["orig"]
        fm_file_data["diff_wrt"] = None
        fm_file_data["diff"] = None
        fm_file_data["darned"] = patch.database.release_stored_content(fm_file_data["darned"])
        return cls(file_path, _FileData.new_dict(orig=orig, darned=darned, diff=diff, diff_wrt=diff_wrt, came_from=came_from), patch)
    def move_contents_from(self, fm_file_data):
        # NB: move the contents first and let exceptions go uncaught
        # so that there is nothing to undo in that event
        os.rename(fm_file_data.path, self.path)
        # shouldn't get here if the rename fails
        # pylint: disable=attribute-defined-outside-init
        if self["came_from"]:
            self.patch.database.release_stored_content(self["came_from"]["orig"])
            if self["came_from"]["as_rename"]:
                self.patch.get_file(self["came_from"]["file_path"])["renamed_as"] = False
            self["came_from"] = None
        if fm_file_data["came_from"]:
            if fm_file_data["came_from"]["as_rename"]:
                # rename of a rename
                if fm_file_data["came_from"]["file_path"] == self.path:
                    # Boomerang
                    assert self["renamed_as"] == fm_file_data.path
                    self.patch.database.release_stored_content(fm_file_data["came_from"]["orig"])
                    fm_file_data["came_from"] = None
                    self["renamed_as"] = None
                else:
                    self["came_from"] = fm_file_data["came_from"]
                    fm_file_data["came_from"] = None
                    self.patch.get_file(self["came_from"]["file_path"])["renamed_as"] = self.path
                    self.patch.database.release_stored_content(self["darned"])
                    self["darned"] = self.patch.database.clone_stored_content_data(self["came_from"]["orig"])
                    self["diff_wrt"] = self["came_from"]["orig"]
                    self["diff"] = None
            else:
                # this a rename of a copy
                self["came_from"] = fm_file_data["came_from"]
                fm_file_data["came_from"] = None
        elif fm_file_data["orig"] is None:
            # this a rename of a file created in this patch
            self.patch.database.release_stored_content(self["darned"])
            self["darned"] = self.patch.database.clone_stored_content_data(fm_file_data["darned"])
            self["diff_wrt"] = fm_file_data["diff_wrt"]
            self["diff"] = fm_file_data["diff"]
        else:
            efd = self.patch.database.clone_stored_content_data(fm_file_data["orig"])
            self["came_from"] = _CameFromData.new_dict(file_path=fm_file_data.path, as_rename=True, orig=efd)
            fm_file_data["renamed_as"] = self.path
            self.patch.database.release_stored_content(self["darned"])
            self["darned"] = self.patch.database.clone_stored_content_data(self["came_from"]["orig"])
            self["diff_wrt"] = self["came_from"]["orig"]
            self["diff"] = None
        fm_file_data["diff_wrt"] = None
        fm_file_data["diff"] = None
        fm_file_data["darned"] = self.patch.database.release_stored_content(fm_file_data["darned"])
    def release_contents(self):
        return _FileData.release_contents(self.persistent_file_data, self.patch.database)
    @property
    def presence(self):
        if self["orig"] is None:
            return Presence.ADDED
        if self.patch.is_applied:
            if not os.path.exists(self.path):
                return Presence.REMOVED
            return Presence.EXTANT
        elif self["darned"] is None:
            return Presence.REMOVED
        return Presence.EXTANT
    @property
    def validity(self):
        if not self.patch.is_applied:
            return None
        overlapping_file = self.get_overlapping_file()
        if self._needs_refresh(overlapping_file):
            if self._has_unresolved_merges(overlapping_file):
                return Validity.UNREFRESHABLE
            else:
                return Validity.NEEDS_REFRESH
        else:
            return Validity.REFRESHED
    @property
    def needs_refresh(self):
        if not self.patch.is_applied:
            # None means "undeterminable"
            return None
        return self._needs_refresh(self.get_overlapping_file())
    def _needs_refresh(self, overlapping_file):
        if self["diff_wrt"] == dict(): # NB: Empty dictionary has a special meaning do not abbreviate this test
            return True
        if self["came_from"]:
            if _EssentialFileData.different(self["came_from"]["orig"], self["diff_wrt"]):
                return True
        elif self["renamed_as"]:
            if self["diff_wrt"]:
                return True
        elif _EssentialFileData.different(self["orig"], self["diff_wrt"]):
            return True
        if overlapping_file is None:
            if self["darned"]:
                try:
                    lstats = os.lstat(self.path)
                except OSError:
                    return True
                if self["darned"]["lstats"].st_mode != lstats.st_mode:
                    return True
                elif self["darned"]["lstats"].st_size != lstats.st_size:
                    return True
                elif self["darned"]["lstats"].st_mtime != lstats.st_mtime:
                    # NB: using modify time and size instead of comparing hash values
                    # but since change modification times doesn't mean contents changed
                    # we will check (this is expensive but good for the UIX)
                    return self["darned"]["git_hash"] != utils.get_git_hash_for_file(self.path)
            else:
                return os.path.exists(self.path)
        else:
            return _EssentialFileData.different(self["darned"], overlapping_file["orig"])
        return False
    @property
    def has_actionable_preamble(self):
        if self["came_from"]:
            return True
        elif self["orig"]:
            return self["darned"] and _EssentialFileData.permissions(self["orig"]) != _EssentialFileData.permissions(self["darned"])
        return bool(self["darned"])
    @property
    def has_unresolved_merges(self):
        if not self.patch.is_applied:
            # None means "undeterminable"
            return None
        return self._has_unresolved_merges(self.get_overlapping_file())
    def _has_unresolved_merges(self, overlapping_file):
        if overlapping_file is None:
            return _file_has_unresolved_merges(self.path)
        else:
            content = self.patch.database.get_content_for(overlapping_file["orig"])
            return _content_has_unresolved_merges(content)
    @property
    def related_file_data(self):
        from .bab.nmd_tuples import PathAndRelation as RFD
        if self["came_from"]:
            if self["came_from"]["as_rename"]:
                return RFD(self["came_from"]["file_path"], os_utils.Relation.MOVED_FROM)
            else:
                return RFD(self["came_from"]["file_path"], os_utils.Relation.COPIED_FROM)
        elif self["renamed_as"]:
            return RFD(self["renamed_as"], os_utils.Relation.MOVED_TO)
        return None
    def get_overlapping_file(self):
        return self.patch.get_overlapping_file(self.path)
    def _get_before_content_path(self):
        if self["came_from"]:
            return get_blob_path(self["came_from"]["orig"]["git_hash"])
        elif self["orig"]:
            return get_blob_path(self["orig"]["git_hash"])
        else:
            return "/dev/null"
    def get_reconciliation_paths(self):
        assert self.patch.is_top_patch
        # make it hard for the user to (accidentally) create these files if they don't exist
        before_path = self._get_before_content_path()
        stashed_path = get_blob_path(self["darned"]["git_hash"]) if self["darned"] else "/dev/null"
        # The user has to be able to cope with the main file not existing (meld can)
        return _O_IP_S_TRIPLET(before_path, self.path, stashed_path)
    def get_extdiff_paths(self):
        assert self.patch.is_applied and self.get_overlapping_file() is None
        # make it hard for the user to (accidentally) create these files if they don't exist
        before_path = self._get_before_content_path()
        # The user has to be able to cope with the main file not existing (meld can)
        return _O_IP_PAIR(before_path, self.path)
    def get_table_row(self):
        # TODO: get rid of need to import fsdb_darning
        from .gui import fsdb_darning
        return fsdb_darning.FileData(self.path, FileStatus(self.presence, self.validity), self.related_file_data)
    def get_refresh_after_data(self, overlapping_file, with_timestamps=False):
        if overlapping_file is not None:
            efd = self.patch.database.clone_stored_content_data(overlapping_file["orig"])
            content = self.patch.database.get_content_for(efd)
        elif os.path.exists(self.path):
            with open(self.path, "rb") as f_obj:
                content = f_obj.read()
            efd = _EssentialFileData.new_dict(git_hash=self.patch.database.store_content(content), lstats=os.lstat(self.path))
        else:
            efd = None
            content = b""
        label = os.path.join("b", self.path) if efd else "/dev/null"
        timestamp = _EssentialFileData.timestamp(efd) if (with_timestamps and efd) else ""
        return _DiffCreationData(label, efd, content, timestamp)
    def do_refresh(self, stdout=None, with_timestamps=False):
        assert self.patch.is_applied
        # pylint: disable=attribute-defined-outside-init
        overlapping_file = self.get_overlapping_file()
        if self._has_unresolved_merges(overlapping_file):
            self["diff_wrt"] = dict() # Empty dictionary means associated diff is STALE
            raise DarnItFileHasUnresolvedMerges(file_path=self.path)
        before = self.get_diff_before_data(as_refreshed=False, with_timestamps=with_timestamps)
        after = self.get_refresh_after_data(overlapping_file, with_timestamps=with_timestamps)
        if before.content == after.content:
            self["diff"] = None
        elif before.content.find(b"\000") != -1 or after.content.find(b"\000") != -1:
            self["diff"] = _DiffData.new_dict(diff_type="binary", diff_lines=diffs.GitBinaryDiff.generate_diff_lines(before, after))
        else:
            self["diff"] = _DiffData.new_dict(diff_type="unified", diff_lines=diffs.UnifiedDiff.generate_diff_lines(before, after))
        self.patch.database.release_stored_content(self["darned"])
        self["darned"] = after.efd
        self["diff_wrt"] = before.efd
        if stdout:
            if not after.efd:
                stdout.write(_("\"{0}\": file does not exist\n").format(rel_subdir(self.path)))
            elif before.efd and after.efd and after.efd["lstats"].st_mode != before.efd["lstats"].st_mode:
                stdout.write(_("\"{0}\": mode {1:07o} -> {2:07o}.\n").format(rel_subdir(self.path), before.efd["lstats"].st_mode, after.efd["lstats"].st_mode))
    def apply_diff(self, drop_atws=True):
        # we assume that "orig" data is correct
        current_efd = self["came_from"]["orig"] if self["came_from"] else self["orig"]
        retval = CmdResult.OK
        already_exists = os.path.exists(self.path)
        if self["diff"]:
            if self["diff"]["diff_type"] == "binary":
                if self["darned"] is not None:
                    with open(self.path, "wb") as f_obj:
                        f_obj.write(self.patch.database.get_content_for(self["darned"]))
                    if already_exists:
                        RCTX.stdout.write(_("\"{0}\": binary file replaced.\n").format(rel_subdir(self.path)))
                    else:
                        RCTX.stdout.write(_("\"{0}\": binary file created.\n").format(rel_subdir(self.path)))
                elif already_exists:
                    os.remove(self.path)
                    RCTX.stdout.write(_("\"{0}\": binary file deleted.\n").format(rel_subdir(self.path)))
                if git_hashes_differ(current_efd, self["diff_wrt"]):
                    retval = CmdResult.WARNING
                    RCTX.stderr.write(_("Warning: \"{0}\": binary file's original has changed.\n").format(rel_subdir(self.path)))
            else:
                result = _do_apply_diff_to_file(self.path, "".join(self["diff"]["diff_lines"]), delete_empty=self["darned"] is None)
                if os.path.exists(self.path):
                    if self["came_from"]:
                        if self["came_from"]["as_rename"]:
                            RCTX.stdout.write(_("\"{0}\": renamed from \"{1}\" and modified.\n").format(rel_subdir(self.path), rel_subdir(self["came_from"]["file_path"])))
                        else:
                            RCTX.stdout.write(_("\"{0}\": copied from \"{1}\" and modified.\n").format(rel_subdir(self.path), rel_subdir(self["came_from"]["file_path"])))
                    elif already_exists:
                        RCTX.stdout.write(_("\"{0}\": modified.\n").format(rel_subdir(self.path)))
                    else:
                        RCTX.stdout.write(_("\"{0}\": created.\n").format(rel_subdir(self.path)))
                else:
                    assert already_exists
                    RCTX.stdout.write(_("\"{0}\": deleted.\n").format(rel_subdir(self.path)))
                if drop_atws:
                    atws_lines = _DiffData.fix_trailing_whitespace(self["diff"])
                    if atws_lines:
                        RCTX.stdout.write(_("\"{1}\": had added trailing white space at line(s) {{{1}}}: removed before application.\n").format(rel_subdir(self.path), ", ".join([str(line) for line in atws_lines])))
                else:
                    atws_lines = _DiffData.report_trailing_whitespace(self["diff"])
                    if atws_lines:
                        retval = CmdResult.WARNING
                        RCTX.stderr.write(_("Warning: \"{0}\": has added trailing white space at line(s) {{{2}}}.\n").format(rel_subdir(self.path), ", ".join([str(line) for line in atws_lines])))
                if result.ecode != 0:
                    RCTX.stderr.write(result.stdout)
                else:
                    RCTX.stdout.write(result.stdout)
                RCTX.stderr.write(result.stderr)
                retval = result.ecode
        elif self["came_from"]:
            if self["came_from"]["as_rename"]:
                RCTX.stdout.write(_("\"{0}\": renamed from \"{1}\".\n").format(rel_subdir(self.path), rel_subdir(self["came_from"]["file_path"])))
            else:
                RCTX.stdout.write(_("\"{0}\": copied from \"{1}\".\n").format(rel_subdir(self.path), rel_subdir(self["came_from"]["file_path"])))
        elif self["renamed_as"]:
            RCTX.stdout.write(_("\"{0}\": renamed as \"{1}\".\n").format(rel_subdir(self.path), rel_subdir(self["renamed_as"])))
        else:
            RCTX.stdout.write(_("\"{0}\": unchanged.\n").format(rel_subdir(self.path)))
        if self["darned"]:
            if os.path.exists(self.path):
                os.chmod(self.path, _EssentialFileData.permissions(self["darned"]))
            else:
                retval = max(retval, CmdResult.WARNING)
                RCTX.stderr.write(_("Expected file not found.\n"))
        return retval

class CombinedFileData(mixins.PedanticDictProxyMixin, FileDiffMixin):
    PROXIED_ITEMS = _CombinedFileData.ALLOWED_ITEMS
    PROXIED_DICT_NAME = "persistent_data"
    def __init__(self, file_path, persistent_data, combined_patch):
        self.path = file_path
        self.persistent_data = persistent_data
        self.patch = combined_patch
    def __getitem__(self, key):
        # NB: for the time being we ignore copy/rename data
        if key == "came_from": return None
        if key == "renamed_as": return None
        if key == "orig": return self.persistent_data["bottom"]["orig"]
        if key == "darned": return self.persistent_data["top"]["darned"]
        if key == "diff": return None # we don't keep a diff
        return mixins.PedanticDictProxyMixin.__getitem__(self, key)
    def get_overlapping_file(self):
        return None
    @property
    def presence(self):
        if self["bottom"]["orig"] is None:
            return Presence.ADDED
        if not os.path.exists(self.path):
            return Presence.REMOVED
        return Presence.EXTANT
    @property
    def validity(self):
        if self._needs_refresh():
            if _file_has_unresolved_merges(self.path):
                return Validity.UNREFRESHABLE
            else:
                return Validity.NEEDS_REFRESH
        else:
            return Validity.REFRESHED
    @property
    def was_ephemeral(self):
        return self["bottom"]["orig"] is None and not os.path.exists(self.path)
    def _needs_refresh(self):
        if self["top"]["diff_wrt"] == dict(): # NB: Empty dictionary has a special meaning do not abbreviate this test
            return True
        if self["top"]["came_from"]:
            if _EssentialFileData.different(self["top"]["came_from"]["orig"], self["top"]["diff_wrt"]):
                return True
        elif self["top"]["renamed_as"]:
            if self["top"]["diff_wrt"]:
                return True
        elif _EssentialFileData.different(self["top"]["orig"], self["top"]["diff_wrt"]):
            return True
        if self["top"]["darned"]:
            try:
                lstats = os.lstat(self.path)
            except OSError:
                return True
            if self["top"]["darned"]["lstats"].st_mode != lstats.st_mode:
                return True
            elif self["top"]["darned"]["lstats"].st_size != lstats.st_size:
                return True
            elif self["top"]["darned"]["lstats"].st_mtime != lstats.st_mtime:
                # NB: using modify time and size instead of comparing hash values
                # but since change modification times doesn't mean contents changed
                # we will check (this is expensive but good for the UIX)
                return self["top"]["darned"]["git_hash"] != utils.get_git_hash_for_file(self.path)
            else:
                return False
        else:
            return os.path.exists(self.path)
    def get_table_row(self):
        from .gui import fsdb_darning
        return fsdb_darning.FileData(self.path, FileStatus(self.presence, self.validity), None)

class Patch(mixins.PedanticDictProxyMixin):
    PROXIED_ITEMS = _PatchData.ALLOWED_ITEMS
    PROXIED_DICT_NAME = "persistent_patch_data"
    def __init__(self, patch_data, database):
        self.persistent_patch_data = patch_data
        self.database = database
        assert patch_data in database["patch_series_data"]
    def __eq__(self, other):
        try:
            return self.persistent_patch_data == other.persistent_patch_data
        except AttributeError:
            assert other is None or _PatchData.verify_dict(other)
            return self.persistent_patch_data == other
    @property
    def name(self):
        return self["name"]
    @property
    def description(self):
        return self["description"]
    @property
    def is_applied(self):
        return self.persistent_patch_data in self.database["applied_patches_data"]
    @property
    def is_blocked_by_guard(self):
        return _guards_block_patch(self.database["selected_guards"], self.persistent_patch_data)
    @property
    def is_top_patch(self):
        return self.persistent_patch_data == self.database.top_patch.persistent_patch_data
    @property
    def needs_refresh(self):
        if not self.is_applied:
            return None # Undeterminable
        for pfile in self.iterate_files():
            if pfile.needs_refresh :
                return True
        return False
    @property
    def state(self):
        if not self.is_applied:
            return PatchState.NOT_APPLIED
        elif self.needs_refresh:
            return PatchState.APPLIED_NEEDS_REFRESH
            #PatchState.APPLIED_UNREFRESHABLE self.has_unresolved_merges else
        else:
            return PatchState.APPLIED_REFRESHED
    @property
    def guards(self):
        return ntuples.Guards(self["pos_guards"], self["neg_guards"])
    def iterate_files(self, file_paths=None):
        if file_paths is None:
            return (FileData(file_path, pfd, self) for file_path, pfd in self["files_data"].items())
        else:
            return (FileData(file_path, self["files_data"][file_path], self) for file_path in file_paths)
    def iterate_files_sorted(self, file_paths=None):
        if file_paths is None:
            return (FileData(file_path, pfd, self) for file_path, pfd in sorted(self["files_data"].items()))
        else:
            return (FileData(file_path, pfd, self) for file_path, pfd in sorted(self["files_data"].items()) if file_path in file_paths)
    def iterate_overlying_patches(self):
        applied_index = self.database["applied_patches_data"].index(self.persistent_patch_data)
        return self.database.iterate_applied_patches(start=applied_index + 1)
    def get_file(self, file_path):
        return FileData(file_path, self["files_data"][file_path], self)
    def has_file_with_path(self, file_path):
        return file_path in self["files_data"]
    def get_file_paths_set(self, file_paths=None):
        if file_paths is None:
            return set(self["files_data"].keys())
        else:
            return {file_path for file_path in self["files_data"].keys() if file_path in file_paths}
    def get_files_table(self):
        return [patch_file.get_table_row() for patch_file in self.iterate_files()]
    def get_overlapping_file(self, file_path):
        for patch in self.iterate_overlying_patches():
            file_data = patch["files_data"].get(file_path, None)
            if file_data:
                return FileData(file_path, file_data, patch)
        return None
    def get_table_row(self):
        return PatchTableRow(self["name"], self.state, self["pos_guards"], self["neg_guards"])
    def create_came_from_for_copy(self, came_from_path):
        try:
            came_from_file = self.get_file(came_from_path)
            if came_from_file["came_from"]:
                efd = self.database.clone_stored_content_data(came_from_file["came_from"]["orig"])
                came_from_path = came_from_file["came_from"]["file_path"]
            else:
                efd = self.database.clone_stored_content_data(came_from_file["orig"])
        except KeyError:
            efd = self.database.store_file_content(came_from_path)
        return _CameFromData.new_dict(file_path=came_from_path, as_rename=False, orig=efd) if efd else None
    def do_apply(self, overlaps=OverlapData()):
        # NB: presence of overlaps implies absorb
        if len(self["files_data"]) == 0:
            return CmdResult.OK
        drop_atws = options.get("push", "drop_added_tws")
        copies = []
        renames = []
        rename_fms = []
        creates = []
        others = []
        # Do the caching of existing files first to obviate copy/rename problems
        for file_data in self.iterate_files_sorted():
            file_data["orig"] = self.database.update_stored_content_data(file_data.path, file_data["orig"], overlaps)
            if file_data["came_from"]:
                file_data["came_from"]["orig"] = self.database.update_stored_content_data(file_data["came_from"]["file_path"], file_data["came_from"]["orig"])
                if file_data["came_from"]["as_rename"]:
                    renames.append(file_data)
                else:
                    copies.append(file_data)
            elif file_data["renamed_as"]:
                rename_fms.append(file_data)
            elif file_data["diff_wrt"] is None:
                creates.append(file_data)
            else:
                others.append(file_data)
            self.database.combined_patch.add_file(file_data)
        biggest_ecode = CmdResult.OK
        # Next do the files that are created by this patch as they may have been copied
        for file_data in creates:
            biggest_ecode = max(biggest_ecode, file_data.apply_diff(drop_atws))
        # Now do the copying
        for file_data in copies:
            if not os.path.exists(file_data["came_from"]["file_path"]):
                biggest_ecode = CmdResult.ERROR
                RCTX.stderr.write(_("{0}: failed to copy {1}.\n").format(rel_subdir(file_data.path), rel_subdir(file_data["came_from"]["file_path"])))
            else:
                try:
                    shutil.copy2(file_data["came_from"]["file_path"], file_data.path)
                except OSError as edata:
                    biggest_ecode = CmdResult.ERROR
                    RCTX.stderr.write(edata)
        # and renaming
        for file_data in renames:
            # NB if there's more than one rename then there is a possibility of
            # complex interactions that make using os.rename problematic
            # so we just move content and mode using stored original data
            fm_file_data = self.get_file(file_data["came_from"]["file_path"])
            # TODO: investigate whether fm_file_data["orig"] can be None here. Duplicated patch?
            try:
                with open(file_data.path, "wb") as f_obj:
                    f_obj.write(self.database.get_content_for(fm_file_data["orig"]))
                os.chmod(file_data.path, _EssentialFileData.permissions(fm_file_data["orig"]))
            except (OSError, IOError) as edata:
                biggest_ecode = CmdResult.ERROR
                RCTX.stderr.write(edata)
        # finish the renaming by removing the originals if necessary
        for file_data in rename_fms:
            if file_data["darned"] is None:
                os.remove(file_data.path)
        # and finally apply any patches
        for file_data in rename_fms + renames + copies + others:
            biggest_ecode = max(biggest_ecode, file_data.apply_diff(drop_atws))
        return biggest_ecode
    def undo_apply(self):
        for file_path, file_data in self["files_data"].items():
            if file_data["orig"] is None:
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            # TODO: add special handling for restoring deleted soft links on pop
            # TODO: use move to put back renamed files
            orig_content = self.database.get_content_for(file_data["orig"])
            with open(file_path, "wb") as f_obj:
                f_obj.write(orig_content)
            os.chmod(file_path, _EssentialFileData.permissions(file_data["orig"]))
    def add_file(self, file_data):
        assert not self.is_applied or self.is_top_patch
        assert file_data.path not in self["files_data"]
        self["files_data"][file_data.path] = file_data.persistent_file_data
        if self.is_applied:
            self.database.combined_patch.add_file(file_data)
    def clear(self):
        return _PatchData.clear(self.persistent_patch_data, self.database)
    def drop_file(self, file_data):
        assert not self.is_applied or self.is_top_patch
        if self.is_applied:
            self.database.combined_patch.drop_file(file_data)
            if file_data["orig"]:
                with open(file_data.path, "wb") as f_obj:
                    f_obj.write(self.database.get_content_for(file_data["orig"]))
                os.chmod(file_data.path, _EssentialFileData.permissions(file_data["orig"]))
            elif os.path.exists(file_data.path):
                os.remove(file_data.path)
        # if this file was the result of a rename then we make the original a normal file
        if file_data["came_from"] and file_data["came_from"]["as_rename"]:
            self.get_file(file_data["came_from"]["file_path"])["renamed_as"] = None
        del self["files_data"][file_data.path]
        # if this file had been renamed then the renamed version becomes a copy
        if file_data["renamed_as"]:
            self.get_file(file_data["renamed_as"])["came_from"]["as_rename"] = False
            file_data["renamed_as"] = None
        file_data.release_contents()
    def drop_named_file(self, file_path):
        self.drop_file(self.get_file(file_path))
    def do_refresh(self, stdout=None):
        eflag = CmdResult.OK
        for file_data in self.iterate_files_sorted():
            try:
                file_data.do_refresh(stdout=stdout)
            except DarnItFileHasUnresolvedMerges:
                RCTX.stderr.write(_("\"{0}\": file has unresolved merge(s).\n").format(rel_subdir(file_data.path)))
                eflag = CmdResult.ERROR
        return eflag
    def do_rename_file(self, file_path, new_file_path):
        assert os.path.exists(file_path)
        assert self.is_top_patch
        try:
            file_data = self.get_file(file_path)
            already_in_patch = True
        except KeyError:
            file_data = FileData.new(file_path, self)
            self.add_file(file_data)
            already_in_patch = False
        try:
            if new_file_path in self["files_data"]:
                self.get_file(new_file_path).move_contents_from(file_data)
            else:
                self.add_file(FileData.new_as_move(new_file_path, self, file_data))
        except OSError:
            if already_in_patch:
                file_data["renamed_as"] = None # pylint: disable=attribute-defined-outside-init
            else:
                self.drop_file(file_data)
            raise
        # if we got here everything is OK so we can finish cleaning up
        if file_data["orig"] is None:
            # No longer needed as it was created in this patch and now has no content or histroy
            self.drop_file(file_data)
    def do_set_guards(self, pos_guards, neg_guards):
        self["pos_guards"] = set(pos_guards)
        self["neg_guards"] = set(neg_guards)
    def write_to_file(self, file_path):
        with open(file_path, "wb") as f_obj:
            f_obj.write(self.description)
            for file_data in self.iterate_files_sorted():
                f_obj.write(file_data.get_diff_text())
    def _apply_diff_plus_changes(self, diff_plus, drop_atws=True, num_strip_levels=1):
        retval = CmdResult.OK
        file_path = diff_plus.get_file_path(num_strip_levels)
        if isinstance(diff_plus.diff, diffs.GitBinaryDiff):
            git_preamble = diff_plus.get_preamble_for_type("git")
            if "deleted file mode" in git_preamble.extras:
                RCTX.stdout.write(_("Deleting binary file \"{0}\".\n").format(rel_subdir(file_path)))
                try:
                    os.remove(file_path)
                except OSError as edata:
                    retval = CmdResult.ERROR
                    RCTX.stderr.write("{0}: {1}\n".format(rel_subdir(file_path), edata))
            elif "new file mode" in git_preamble.extras:
                RCTX.stdout.write(_("Creating binary file \"{0}\".\n").format(rel_subdir(file_path)))
                try:
                    with open(file_path, "wb") as f_obj:
                        f_obj.write(diff_plus.diff.forward.data_raw)
                except IOError as edata:
                    retval = CmdResult.ERROR
                    RCTX.stderr.write("{0}: {1}\n".format(rel_subdir(file_path), edata))
            else:
                RCTX.stdout.write(_("Patching binary file \"{0}\".\n").format(rel_subdir(file_path)))
                if diff_plus.diff.forward.method == diffs.GitBinaryDiffData.LITERAL:
                    # if it's literal just insert the raw data.
                    try:
                        with open(file_path, "wb") as f_obj:
                            f_obj.write(diff_plus.diff.forward.data_raw)
                    except IOError as edata:
                        retval = CmdResult.ERROR
                        RCTX.stderr.write("{0}: {1}\n".format(rel_subdir(file_path), edata))
                elif diff_plus.is_compatible_with(utils.get_git_hash_for_file(file_path)):
                    from .patch_diff import gitdelta
                    with open(file_path, "rb") as f_obj:
                        contents = f_obj.read()
                    try:
                        new_contents = gitdelta.patch_delta(contents, diff_plus.diff.forward.data_raw)
                    except gitdelta.PatchError as edata:
                        retval = CmdResult.ERROR
                        RCTX.stderr.write(_("\"{0}\": imported binary delta failed to apply: {1}.\n").format(rel_subdir(file_path), edata))
                    else:
                        with open(file_path, "wb") as f_obj:
                            f_obj.write(new_contents)
                else:
                    # the original file has changed and it would be unwise to apply the delta
                    retval = CmdResult.ERROR
                    RCTX.stderr.write(_("\"{0}\": imported binary delta can not be applied.\n").format(rel_subdir(file_path)))
        elif diff_plus.diff:
            RCTX.stdout.write(_("Patching file \"{0}\".\n").format(rel_subdir(file_path)))
            if drop_atws:
                atws_lines = diff_plus.fix_trailing_whitespace()
                if atws_lines:
                    RCTX.stdout.write(_("Added trailing white space to \"{0}\" at line(s) {{{1}}}: removed before application.\n").format(rel_subdir(file_path), ", ".join([str(line) for line in atws_lines])))
            else:
                atws_lines = diff_plus.report_trailing_whitespace()
                if atws_lines:
                    RCTX.stderr.write(_("Added trailing white space to \"{1}\" at line(s) {{{2}}}.\n").format(rel_subdir(file_path), ", ".join([str(line) for line in atws_lines])))
            result = _do_apply_diff_to_file(file_path, diff_plus.diff, delete_empty=diff_plus.get_outcome() < 0)
            RCTX.stderr.write(result.stderr)
            if result.ecode == CmdResult.OK and result.stderr:
                retval = CmdResult.WARNING
            else:
                retval = result.ecode
        if retval == CmdResult.OK:
            self.get_file(file_path).do_refresh()
        if os.path.exists(file_path):
            new_mode = diff_plus.get_new_mode()
            if new_mode is not None:
                os.chmod(file_path, new_mode)
        return retval
    def do_fold_epatch(self, epatch, absorb=False, force=False):
        assert not (force and absorb)
        assert self.is_top_patch
        if not force:
            new_file_paths = []
            for diff_plus in epatch.diff_pluses:
                file_path = diff_plus.get_file_path(epatch.num_strip_levels)
                if file_path in self["files_data"]:
                    continue
                git_preamble = diff_plus.get_preamble_for_type("git")
                if git_preamble and ("copy from" in git_preamble.extras or "rename from" in git_preamble.extras):
                    continue
                new_file_paths.append(file_path)
            overlaps = self.database.get_overlap_data(new_file_paths, self)
            if not absorb and len(overlaps) > 0:
                return overlaps.report_and_abort()
        else:
            overlaps = OverlapData()
        copies = []
        renames = []
        creates = []
        cold_deletes = []
        others = []
        failures = []
        # Do the caching of existing files first to obviate copy/rename problems
        for diff_plus in epatch.diff_pluses:
            file_path = diff_plus.get_file_path(epatch.num_strip_levels)
            if file_path not in self["files_data"]:
                self.add_file(FileData.new(file_path, self, overlaps=overlaps))
            git_preamble = diff_plus.get_preamble_for_type("git")
            if git_preamble:
                copied_from = git_preamble.extras.get("copy from", None)
                renamed_from = git_preamble.extras.get("rename from", None)
                if renamed_from is not None:
                    if renamed_from not in self["files_data"]:
                        self.add_file(FileData.new(renamed_from, self, overlaps=overlaps))
                    renames.append((diff_plus, renamed_from))
                elif copied_from is not None:
                    copies.append((diff_plus, copied_from))
                elif git_preamble.extras.get("new file mode", False):
                    creates.append(diff_plus)
                elif git_preamble.extras.get("deleted file mode", False) and diff_plus.diff is None:
                    cold_deletes.append(diff_plus)
                else:
                    others.append(diff_plus)
            elif diff_plus.get_outcome() > 0:
                creates.append(diff_plus)
            else:
                others.append(diff_plus)
        drop_atws = options.get("push", "drop_added_tws")
        biggest_ecode = CmdResult.OK
        # Now use patch to create any file created by the fold
        for diff_plus in creates:
            biggest_ecode = max(self._apply_diff_plus_changes(diff_plus, drop_atws, epatch.num_strip_levels), biggest_ecode)
        # Do any copying
        for diff_plus, came_from_path in copies:
            new_file_data = self.get_file(diff_plus.get_file_path(epatch.num_strip_levels))
            # We copy the current version here not the original
            # TODO: think about force/absorb ramifications HERE
            RCTX.stdout.write(_("Copying \"{0}\" to \"{1}\".\n").format(rel_subdir(came_from_path), rel_subdir(new_file_data.path)))
            try:
                new_file_data.copy_contents_from(came_from_path)
            except OSError:
                biggest_ecode = CmdResult.ERROR
                RCTX.stderr.write(_("{0}: failed to copy {1}.\n").format(rel_subdir(new_file_data.path), rel_subdir(came_from_path)))
                failures.append(diff_plus)
        # Do any renaming
        for diff_plus, came_from_path in renames:
            new_file_data = self.get_file(diff_plus.get_file_path(epatch.num_strip_levels))
            fm_file_data = self.get_file(came_from_path)
            RCTX.stdout.write(_("Renaming/moving \"{0}\" to \"{1}\".\n").format(rel_subdir(came_from_path), rel_subdir(new_file_data.path)))
            try:
                new_file_data.move_contents_from(fm_file_data)
            except OSError:
                biggest_ecode = CmdResult.ERROR
                RCTX.stderr.write(_("{0}: failed to move {1}.\n").format(rel_subdir(new_file_data.path), rel_subdir(came_from_path)))
                failures.append(diff_plus)
                continue
            if fm_file_data["orig"] is None:
                self.drop_file(fm_file_data)
        # Apply the remaining changes
        for diff_plus, _dummy in copies + renames: # pylint: disable=unused-variable
            # NB: don't try applying patch if the copy/rename failed
            if diff_plus not in failures:
                biggest_ecode = max(self._apply_diff_plus_changes(diff_plus, drop_atws, epatch.num_strip_levels), biggest_ecode)
        for diff_plus in others:
            biggest_ecode = max(self._apply_diff_plus_changes(diff_plus, drop_atws, epatch.num_strip_levels), biggest_ecode)
        for diff_plus in cold_deletes:
            file_path = diff_plus.get_file_path(epatch.num_strip_levels)
            rel_file_path = rel_subdir(file_path)
            try:
                RCTX.stdout.write(_("Deleting \"{0}\".\n").format(rel_file_path))
                os.remove(file_path)
            except OSError:
                biggest_ecode = CmdResult.ERROR
                RCTX.stderr.write(_("{0}: deletion failed.\n").format(rel_file_path))
        return biggest_ecode

class TextDiffPlus(patches.DiffPlus):
    def __init__(self, file_data, with_timestamps=False):
        diff_plus = file_data.get_diff_plus(as_refreshed=True, with_timestamps=with_timestamps)
        patches.DiffPlus.__init__(self, preambles=diff_plus.preambles, diff=diff_plus.diff)
        self.validity = file_data.validity

class TextPatch(patches.Patch):
    def __init__(self, patch, with_timestamps=False, with_stats=True):
        patches.Patch.__init__(self, num_strip_levels=1)
        self.source_name = patch.name
        self.state = PatchState.APPLIED_REFRESHED if patch.is_applied else PatchState.NOT_APPLIED
        self.set_description(patch.description)
        for file_data in patch.iterate_files_sorted():
            if file_data["diff"] is None and not file_data.has_actionable_preamble:
                continue
            edp = TextDiffPlus(file_data, with_timestamps=with_timestamps)
            if edp.diff is None and (file_data["renamed_as"] and not file_data["came_from"]):
                continue
            self.diff_pluses.append(edp)
            if self.state == PatchState.NOT_APPLIED:
                continue
            if self.state == PatchState.APPLIED_REFRESHED and edp.validity != Validity.REFRESHED:
                self.state = PatchState.APPLIED_NEEDS_REFRESH if edp.validity == Validity.NEEDS_REFRESH else PatchState.APPLIED_UNREFRESHABLE
            elif self.state == PatchState.APPLIED_NEEDS_REFRESH and edp.validity == Validity.UNREFRESHABLE:
                self.state = PatchState.APPLIED_UNREFRESHABLE
        if with_stats:
            self.set_header_diffstat(strip_level=self.num_strip_levels)
    def get_hash_digest(self):
        import hashlib
        h = hashlib.sha1()
        h.update(str(self).encode())
        h.update(str(self.state).encode())
        return h.digest()

class CombinedPatch(mixins.PedanticDictProxyMixin):
    PROXIED_ITEMS = _CombinedPatchData.ALLOWED_ITEMS
    PROXIED_DICT_NAME = "persistent_data"
    is_applied = True
    def __init__(self, persistent_data, database):
        self.persistent_data = persistent_data
        self.database = database
    def add_file(self, file_data):
        if self["prev"]:
            prev_file_data = self["prev"]["files_data"].get(file_data.path, None)
            bottom = prev_file_data["bottom"] if prev_file_data else file_data.persistent_file_data
        else:
            bottom = file_data.persistent_file_data
        self["files_data"][file_data.path] = _CombinedFileData.new_dict(top=file_data.persistent_file_data, bottom=bottom)
    def drop_file(self, file_data):
        assert self["files_data"][file_data.path]["top"] == file_data.persistent_file_data, "\n\t{}\n!=\n\t {}".format(self["files_data"][file_data.path]["top"], file_data.persistent_file_data)
        prev_file_data = self["prev"]["files_data"].get(file_data.path, None) if self["prev"] else None
        if prev_file_data:
            self["files_data"][file_data.path] = copy.copy(prev_file_data)
        else:
            del self["files_data"][file_data.path]
    def iterate_files_sorted(self, file_paths=None):
        if file_paths is None:
            return (CombinedFileData(file_path, pfd, self) for file_path, pfd in sorted(self["files_data"].items()))
        else:
            return (CombinedFileData(file_path, pfd, self) for file_path, pfd in sorted(self["files_data"].items()) if file_path in file_paths)
    def get_files_table(self):
        return [file_data.get_table_row() for file_data in self.iterate_files_sorted() if not file_data.was_ephemeral]
    def get_file(self, file_path):
        return CombinedFileData(file_path, self["files_data"][file_path], self)
    def has_file_with_path(self, file_path):
        try:
            return not self.get_file(file_path).was_ephemeral
        except KeyError:
            return False
    def get_text_diff(self, file_paths=None, with_timestamps=False):
        text = ""
        if file_paths:
            for file_path in file_paths:
                text += self.get_file(file_path).get_diff_text(with_timestamps=with_timestamps)
        else:
            for file_data in self.iterate_files_sorted():
                if file_data.was_ephemeral:
                    continue
                text += file_data.get_diff_text(with_timestamps=with_timestamps)
        return text
    def get_diff_pluses(self, file_paths=None, with_timestamps=False):
        if file_paths:
            return [self.get_file(file_path).get_diff_plus(with_timestamps=with_timestamps) for file_path in file_paths]
        else:
            return [file_data.get_diff_plus(with_timestamps=with_timestamps) for file_data in self.iterate_files_sorted()]

_ContentState = collections.namedtuple("_ContentState", ["orphans", "missing", "bad_content"])

class DataBase(mixins.PedanticDictProxyMixin):
    PROXIED_ITEMS = _DataBaseData.ALLOWED_ITEMS
    PROXIED_DICT_NAME = "_PPD"
    def __init__(self, patches_persistent_data, blob_ref_counts, is_writable):
        self._PPD = patches_persistent_data
        self.blob_ref_counts = blob_ref_counts
        self.is_writable = is_writable
        for patch in patches_persistent_data["applied_patches_data"]:
            assert patch in patches_persistent_data["patch_series_data"]
    @property
    def top_patch(self):
        return None if not self._PPD["applied_patches_data"] else Patch(self._PPD["applied_patches_data"][-1], self)
    @property
    def top_patch_name(self):
        return None if not self._PPD["applied_patches_data"] else self._PPD["applied_patches_data"][-1]["name"]
    @property
    def base_patch(self):
        return None if not self._PPD["applied_patches_data"] else Patch(self._PPD["applied_patches_data"][0], self)
    @property
    def base_patch_name(self):
        return None if not self._PPD["applied_patches_data"] else self._PPD["applied_patches_data"][0]["name"]
    @property
    def prev_patch(self):
        return None if len(self._PPD["applied_patches_data"]) < 2 else Patch(self._PPD["applied_patches_data"][-2], self)
    @property
    def prev_patch_name(self):
        return None if len(self._PPD["applied_patches_data"]) < 2 else self._PPD["applied_patches_data"][-2]["name"]
    def _next_patch_data(self):
        if self._PPD["applied_patches_data"]:
            top_patch_index = self._PPD["patch_series_data"].index(self._PPD["applied_patches_data"][-1])
            for patch in self._PPD["patch_series_data"][top_patch_index + 1:]:
                if not _guards_block_patch(self._PPD["selected_guards"], patch):
                    return patch
        else:
            for patch in self._PPD["patch_series_data"]:
                if not _guards_block_patch(self._PPD["selected_guards"], patch):
                    return patch
        return None
    @property
    def next_patch(self):
        next_patch_data = self._next_patch_data()
        return Patch(next_patch_data, self) if next_patch_data else None
    @property
    def next_patch_name(self):
        next_patch_data = self._next_patch_data()
        return next_patch_data["name"] if next_patch_data else None
    @property
    def is_pushable(self):
        return self._next_patch_data() is not None
    @property
    def combined_patch(self):
        return CombinedPatch(self["combined_patch_data"], self) if self["combined_patch_data"] else None
    @property
    def patch_count(self):
        return len(self._PPD["patch_series_data"])
    @property
    def applied_patch_count(self):
        return len(self._PPD["applied_patches_data"])
    def create_new_patch(self, patch_name, description):
        assert self.is_writable
        if _named_patch_is_in_list(self._PPD["patch_series_data"], patch_name):
            raise DarnItPatchExists(patch_name=patch_name)
        new_patch = _PatchData.new_dict(name=patch_name, description=_tidy_text(description))
        if self._PPD["applied_patches_data"]:
            top_patch_index = self._PPD["patch_series_data"].index(self._PPD["applied_patches_data"][-1])
            self._PPD["patch_series_data"].insert(top_patch_index + 1, new_patch)
        else:
            self._PPD["patch_series_data"].insert(0, new_patch)
        self._PPD["applied_patches_data"].append(new_patch)
        assert self._PPD["applied_patches_data"][-1] == new_patch
        assert new_patch in self._PPD["patch_series_data"]
        self._PPD["combined_patch_data"] = _CombinedPatchData.make_new_dict(self._PPD["combined_patch_data"])
        return Patch(new_patch, self)
    def duplicate_patch(self, patch, new_patch_name, new_description):
        assert self.is_writable
        if _named_patch_is_in_list(self._PPD["patch_series_data"], new_patch_name):
            raise DarnItPatchExists(patch_name=new_patch_name)
        new_patch_data = _PatchData.new_dict(name=new_patch_name, description=_tidy_text(new_description))
        if self._PPD["applied_patches_data"]:
            top_patch_index = self._PPD["patch_series_data"].index(self._PPD["applied_patches_data"][-1])
            self._PPD["patch_series_data"].insert(top_patch_index + 1, new_patch_data)
        else:
            self._PPD["patch_series_data"].insert(0, new_patch_data)
        new_patch = Patch(new_patch_data, self)
        for file_data in patch.iterate_files():
            new_patch.add_file(file_data.clone_for_patch(new_patch))
        return new_patch
    def duplicate_named_patch(self, patch_name, new_patch_name, new_description):
        patch = self.get_named_patch(patch_name)
        if patch.needs_refresh:
            raise DarnItPatchNeedsRefresh(patch_name=patch.name)
        return self.duplicate_patch(patch, new_patch_name, new_description)
    def remove_patch(self, patch, retain_copy=False):
        assert self.is_writable
        if patch.is_applied:
            raise DarnItPatchIsApplied(patch_name=patch.name)
        self["patch_series_data"].remove(patch)
        if retain_copy:
            try:
                _PatchData.clear(self["kept_patches"].pop(patch.name), self)
            except KeyError:
                pass
            self["kept_patches"][patch.name] = patch.persistent_patch_data
        else:
            patch.clear()
    def remove_named_patch(self, patch_name, retain_copy=False):
        patch = self.get_named_patch(patch_name)
        return self.remove_patch(patch, retain_copy=retain_copy)
    def delete_kept_patch(self, patch_name):
        try:
            _PatchData.clear(self["kept_patches"].pop(patch_name), self)
        except KeyError:
            raise DarnItUnknownPatch(patch_name=patch_name)
    def restore_named_patch(self, patch_name, as_patch_name=None):
        assert self.is_writable
        if not as_patch_name:
            as_patch_name = patch_name
        if self.has_patch_with_name(as_patch_name):
            raise DarnItPatchExists(patch_name=as_patch_name)
        try:
            patch_data = self["kept_patches"].pop(patch_name)
        except KeyError:
            raise DarnItUnknownPatch(patch_name=patch_name)
        patch_data["name"] = as_patch_name
        if self._PPD["applied_patches_data"]:
            top_patch_index = self._PPD["patch_series_data"].index(self._PPD["applied_patches_data"][-1])
            self._PPD["patch_series_data"].insert(top_patch_index + 1, patch_data)
        else:
            self._PPD["patch_series_data"].insert(0, patch_data)
        return Patch(patch_data, self)
    def get_named_patch(self, patch_name):
        _index, patch = _find_named_patch_in_list(self._PPD["patch_series_data"], patch_name) # pylint: disable=unused-variable
        if not patch:
            raise DarnItUnknownPatch(patch_name=patch_name)
        return Patch(patch, self)
    def iterate_applied_patches(self, start=0, stop=None, backwards=False):
        if backwards:
            return (Patch(patch_data, self) for patch_data in reversed(self["applied_patches_data"][slice(start, stop)]))
        else:
            return (Patch(patch_data, self) for patch_data in self["applied_patches_data"][slice(start, stop)])
    def iterate_series(self, start=0, stop=None):
        return (Patch(patch_data, self) for patch_data in self["patch_series_data"][slice(start, stop)])
    def pop_top_patch(self, force=False):
        assert self.is_writable
        if not self["applied_patches_data"]:
            raise DarnItNoPatchesApplied()
        if not force and self.top_patch.needs_refresh:
            raise DarnItPatchNeedsRefresh(patch_name=self.top_patch_name)
        self.top_patch.undo_apply()
        self["applied_patches_data"].pop()
        self._PPD["combined_patch_data"] = self._PPD["combined_patch_data"]["prev"]
        return self.top_patch
    def push_next_patch(self, absorb=False, force=False):
        assert not (absorb and force)
        patch = self.next_patch
        if not patch:
            raise DarnItNoPushablePatches()
        if force:
            overlaps = OverlapData()
        else:
            # We don't worry about overlaps for files that came from a copy or rename
            overlaps = self.get_overlap_data([file_data.path for file_data in patch.iterate_files() if file_data["came_from"] is None])
            if not absorb and len(overlaps):
                raise DarnItPatchOverlapsChanges(overlaps=overlaps)
        self["applied_patches_data"].append(patch.persistent_patch_data)
        self._PPD["combined_patch_data"] = _CombinedPatchData.make_new_dict(self._PPD["combined_patch_data"])
        return patch.do_apply(overlaps)
    def get_kept_patch_names(self):
        return sorted(list(self._PPD["kept_patches"].keys()))
    def get_selected_guards(self):
        return sorted(self._PPD["selected_guards"])
    def set_selected_guards(self, guards):
        self._PPD["selected_guards"] = set(guards)
    def get_overlap_data(self, file_paths, patch=None):
        """
        Get the data detailing unrefreshed/uncommitted files that will be
        overlapped by the files in filelist if they are added to the named
        (or next, if patch_name is None) patch.
        """
        if not file_paths:
            return OverlapData()
        # NB: let this blow up if index fails
        patch_index = None if patch is None else self["applied_patches_data"].index(patch.persistent_patch_data)
        remaining_files = set(file_paths)
        uncommitted = set(scm_ifce.get_current_ifce().get_files_with_uncommitted_changes(remaining_files))
        unrefreshed = {}
        for patch in self.iterate_applied_patches(stop=patch_index, backwards=True):
            if len(uncommitted) + len(remaining_files) == 0:
                break
            patch_file_paths_set = patch.get_file_paths_set(remaining_files)
            if patch_file_paths_set:
                remaining_files -= patch_file_paths_set
                uncommitted -= patch_file_paths_set
                for patched_file in patch.iterate_files(patch_file_paths_set):
                    if patched_file.needs_refresh:
                        unrefreshed[patched_file.path] = patch
        return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)
    def get_top_patch_for_file(self, file_path):
        for applied_patch in reversed(self._PPD["applied_patches_data"]):
            if file_path in applied_patch["files_data"]:
                return applied_patch["name"]
        return None
    def has_patch_with_name(self, name):
        for patch in self["patch_series_data"]:
            if patch["name"] == name:
                return True
        return False
    def incr_ref_count_for_hash(self, git_hash):
        try:
            self.blob_ref_counts[git_hash[:2]][git_hash[2:]] += 1
        except KeyError:
            try:
                self.blob_ref_counts[git_hash[:2]][git_hash[2:]] = 1
            except KeyError:
                self.blob_ref_counts[git_hash[:2]] = {git_hash[2:] : 1}
        return self.blob_ref_counts[git_hash[:2]][git_hash[2:]]
    def check_content(self):
        assert not self.is_writable
        orphans = []
        missing = []
        bad_content = []
        for base_dir_path, _dir_names, file_names in os.walk(_BLOBS_DIR_PATH): # pylint: disable=unused-variable
            if file_names:
                key1 = os.path.basename(base_dir_path)
                for file_name in file_names:
                    if utils.get_git_hash_for_file(os.path.join(base_dir_path, file_name)) != key1 + file_name:
                        bad_content.append(key1 + file_name)
                    try:
                        if self.blob_ref_counts[key1][file_name] < 1:
                            orphans.append(key1 + file_name)
                    except KeyError:
                        orphans.append(key1 + file_name)
        for key1, ref_counts in self.blob_ref_counts.items():
            for file_name in ref_counts.keys():
                if not os.path.isfile(os.path.join(_BLOBS_DIR_PATH, key1, file_name)):
                    missing.append(key1 + file_name)
        return _ContentState(orphans=orphans, missing=missing, bad_content=bad_content)
    def validate_ref_counts(self):
        blob_ref_counts = self.blob_ref_counts.copy()
        for patch_data in self["patch_series_data"]:
            _PatchData.decrement_ref_counts(patch_data, blob_ref_counts)
        for patch_data in self["kept_patches"].values():
            _PatchData.decrement_ref_counts(patch_data, blob_ref_counts)
        bad_ref_counts = []
        for key1, ref_counts in blob_ref_counts.items():
            for key2, count in ref_counts.items():
                if count != 0:
                    bad_ref_counts.append((key1 + key2, count))
        return bad_ref_counts
    def store_content(self, content):
        git_hash = utils.get_git_hash_for_content(content)
        if self.incr_ref_count_for_hash(git_hash) == 1:
            blob_dir_path = get_blob_dir_path(git_hash)
            if not os.path.exists(blob_dir_path):
                os.mkdir(blob_dir_path)
            blob_file_path = get_blob_path(git_hash)
            with open(blob_file_path, "wb") as f_obj:
                f_obj.write(content)
            utils.do_turn_off_write_for_file(blob_file_path)
        return git_hash
    def store_file_content(self, file_path, overlaps=OverlapData()):
        overlapped_patch = overlaps.unrefreshed.get(file_path, None)
        if overlapped_patch:
            return self.clone_stored_content_data(overlapped_patch.get_file(file_path)["darned"])
        if file_path in overlaps.uncommitted:
            contents = scm_ifce.get_current_ifce().get_clean_contents(file_path)
            if contents is None:
                # Will occur if file has been added to SCM but not committed
                return None
        elif os.path.exists(file_path):
            with open(file_path, "rb") as f_obj:
                contents = f_obj.read()
        else:
            return None
        return _EssentialFileData.new_dict(git_hash=self.store_content(contents), lstats=os.lstat(file_path))
    def update_stored_content_data(self, file_path, old_data, overlaps=OverlapData()):
        # NB: get new data first so that if it hasn't changed not much gets done
        new_data = self.store_file_content(file_path, overlaps)
        self.release_stored_content(old_data)
        return new_data
    def clone_stored_content_data(self, content_data):
        if content_data is None:
            return None
        cloned_data = content_data.copy()
        self.incr_ref_count_for_hash(cloned_data["git_hash"])
        return cloned_data
    def release_stored_content(self, efd):
        if efd is not None:
            dir_name, file_name = efd["git_hash"][:2], efd["git_hash"][2:]
            self.blob_ref_counts[dir_name][file_name] -= 1
            if self.blob_ref_counts[dir_name][file_name] == 0:
                os.remove(os.path.join(_BLOBS_DIR_PATH, dir_name, file_name))
                del self.blob_ref_counts[dir_name][file_name]
    @staticmethod
    def get_content_for(obj):
        if obj is None:
            return b""
        else:
            with open(get_blob_path(obj["git_hash"]), "rb") as f_obj:
                return f_obj.read()

def do_create_db(dir_path=None, description=None):
    """Create a patch database in the current directory?"""
    def rollback():
        """Undo steps that were completed before failure occured"""
        for filnm in [patches_data_file_path, database_lock_file_path, blob_ref_count_file_path, description_file_path]:
            if os.path.exists(filnm):
                os.remove(filnm)
        for dirnm in [database_blobs_dir_path, database_dir_path]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    if not dir_path:
        dir_path = os.getcwd()
    root = find_base_dir(dir_path=dir_path, remember_sub_dir=False)
    if root is not None:
        RCTX.stderr.write(_("Inside existing playground: \"{0}\".\n").format(os.path.relpath(root)))
        return CmdResult.ERROR
    database_dir_path = os.path.join(dir_path, _DIR_PATH)
    database_blobs_dir_path = os.path.join(dir_path, _BLOBS_DIR_PATH)
    patches_data_file_path = os.path.join(dir_path, _PATCHES_DATA_FILE_PATH)
    blob_ref_count_file_path = os.path.join(dir_path, _BLOB_REF_COUNT_FILE_PATH)
    description_file_path = os.path.join(dir_path, _DESCRIPTION_FILE_PATH)
    if os.path.exists(database_dir_path):
        if os.path.exists(database_blobs_dir_path) and os.path.exists(patches_data_file_path):
            RCTX.stderr.write(_("Database already exists.\n"))
        else:
            RCTX.stderr.write(_("Database directory exists.\n"))
        return CmdResult.ERROR
    database_lock_file_path = os.path.join(dir_path, _LOCK_FILE_PATH)
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(database_dir_path, dir_mode)
        os.mkdir(database_blobs_dir_path, dir_mode)
        with open(database_lock_file_path, "wb") as f_obj:
            f_obj.write(b"0")
        with open(description_file_path, "w") as f_obj:
            f_obj.write(_tidy_text(description))
        db_obj = _DataBaseData.new_dict()
        with open(patches_data_file_path, "wb", stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH) as f_obj:
            pickle.dump(db_obj, f_obj)
        with open(blob_ref_count_file_path, "wb", stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH) as f_obj:
            pickle.dump(dict(), f_obj)
    except OSError as edata:
        rollback()
        RCTX.stderr.write(edata.strerror)
        return CmdResult.ERROR
    except Exception:
        rollback()
        raise
    return CmdResult.OK

# Wrappers for portable lock routines
if os.name == "nt" or os.name == "dos":
    import msvcrt # pylint: disable=import-error
    LOCK_EXCL = msvcrt.LK_LOCK
    LOCK_READ = msvcrt.LK_RLCK
    def lock_db(fd, mode):
        return msvcrt.locking(fd, mode, 1024)
    def unlock_db(fd):
        os.lseek(fd, 0, 0)
        return msvcrt.locking(fd, msvcrt.LK_UNLCK, 1024)
else:
    import fcntl
    LOCK_EXCL = fcntl.LOCK_EX
    LOCK_READ = fcntl.LOCK_SH
    def lock_db(fd, mode):
        return fcntl.lockf(fd, mode)
    def unlock_db(fd):
        return fcntl.lockf(fd, fcntl.LOCK_UN)

# Make a context manager for locking/opening/closing database
@contextmanager
def open_db(mutable=False):
    fd = os.open(_LOCK_FILE_PATH, os.O_RDWR if mutable else os.O_RDONLY)
    lock_db(fd, LOCK_EXCL if mutable else LOCK_READ)
    with open(_PATCHES_DATA_FILE_PATH, "rb") as f_obj:
        patches_data = pickle.load(f_obj)
    with open(_BLOB_REF_COUNT_FILE_PATH, "rb") as f_obj:
        blob_ref_counts = pickle.load(f_obj)
    try:
        yield DataBase(patches_data, blob_ref_counts, mutable)
    finally:
        if mutable:
            scount = os.read(fd, 255)
            os.lseek(fd, 0, 0)
            os.write(fd, str(int(scount) + 1).encode())
            with open(_PATCHES_DATA_FILE_PATH, "wb") as f_obj:
                pickle.dump(patches_data, f_obj)
            with open(_BLOB_REF_COUNT_FILE_PATH, "wb") as f_obj:
                pickle.dump(blob_ref_counts, f_obj)
        unlock_db(fd)
        os.close(fd)

### Helper commands
# The helper commands are wrappers for common functionality in the
# modules exported functions.  They may emit output to stderr and
# should only be used where that is a requirement.  Use DataBase
# methods otherwise.
def _get_patch(patch_name, db):
    """Return the named patch"""
    try:
        return db.get_named_patch(patch_name)
    except DarnItUnknownPatch:
        RCTX.stderr.write(_("{0}: patch is NOT known.\n").format(patch_name))
        return None

def _get_top_patch(db):
    if db.top_patch is None:
        RCTX.stderr.write(_("No patches applied.\n"))
    return db.top_patch

def _get_named_or_top_patch(patch_name, db):
    """Return the named or top applied patch"""
    return _get_patch(patch_name, db) if patch_name is not None else _get_top_patch(db)

# Main interface commands start here

# DOs

def do_add_files_to_top_patch(file_paths, absorb=False, force=False):
    assert not (absorb and force)
    with open_db(mutable=True) as DB:
        top_patch = _get_top_patch(DB)
        if top_patch is None:
            return CmdResult.ERROR
        if not force:
            overlaps = DB.get_overlap_data(iter_prepending_subdir(file_paths), top_patch)
            if not absorb and len(overlaps) > 0:
                return overlaps.report_and_abort()
        else:
            overlaps = OverlapData()
        top_patch_file_paths_set = top_patch.get_file_paths_set()
        issued_warning = False
        for file_path, file_path_rel_subdir in iter_with_subdir(file_paths):
            if file_path in top_patch_file_paths_set:
                RCTX.stderr.write(_("{0}: file already in patch \"{1}\". Ignored.\n").format(file_path_rel_subdir, top_patch.name))
                issued_warning = True
                continue
            elif os.path.isdir(file_path):
                RCTX.stderr.write(_("{0}: is a directory. Ignored.\n").format(file_path_rel_subdir))
                issued_warning = True
                continue
            top_patch_file_paths_set.add(file_path)
            top_patch.add_file(FileData.new(file_path, top_patch, overlaps=overlaps))
            RCTX.stdout.write(_("{0}: file added to patch \"{1}\".\n").format(file_path_rel_subdir, top_patch.name))
            if file_path in overlaps.uncommitted:
                RCTX.stderr.write(_("{0}: Uncommited SCM changes have been incorporated in patch \"{1}\".\n").format(file_path_rel_subdir, top_patch.name))
            elif file_path in overlaps.unrefreshed:
                RCTX.stderr.write(_("{0}: Unrefeshed changes in patch \"{2}\" incorporated in patch \"{1}\".\n").format(file_path_rel_subdir, top_patch.name, overlaps.unrefreshed[file_path].name))
        return CmdResult.WARNING if issued_warning else CmdResult.OK

def do_apply_next_patch(absorb=False, force=False):
    with open_db(mutable=True) as DB:
        try:
            ecode = DB.push_next_patch(absorb=absorb, force=force)
        except DarnItNoPushablePatches:
            if DB.top_patch_name:
                RCTX.stderr.write(_("No pushable patches. \"{0}\" is on top.\n").format(DB.top_patch_name))
            else:
                RCTX.stderr.write(_("No pushable patches.\n"))
            return CmdResult.ERROR
        except DarnItPatchOverlapsChanges as edata:
            return edata.overlaps.report_and_abort()
        if ecode & CmdResult.ERROR:
            RCTX.stderr.write(_("A refresh is required after issues are resolved.\n"))
        elif DB.top_patch.needs_refresh:
            RCTX.stderr.write(_("A refresh is required.\n"))
        RCTX.stdout.write(_("Patch \"{0}\" is now on top.\n").format(DB.top_patch.name))
        return CmdResult.ERROR if ecode > 1 else CmdResult.OK

def do_copy_file_to_top_patch(file_path, as_file_path, overwrite=False):
    with open_db(mutable=True) as DB:
        top_patch = _get_top_patch(DB)
        if top_patch is None:
            return CmdResult.ERROR
        file_path = rel_basedir(file_path)
        as_file_path = rel_basedir(as_file_path)
        if file_path == as_file_path:
            return CmdResult.OK
        if not os.path.exists(file_path):
            RCTX.stderr.write(_("{0}: file does not exist.\n").format(rel_subdir(file_path)))
            return CmdResult.ERROR
        if not overwrite:
            if top_patch.has_file_with_path(as_file_path):
                RCTX.stderr.write(_("{0}: file already in patch.\n").format(rel_subdir(as_file_path)))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME | CmdResult.Suggest.OVERWRITE
            if os.path.exists(as_file_path):
                RCTX.stderr.write(_("{0}: file already exists.\n").format(rel_subdir(as_file_path)))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME | CmdResult.Suggest.OVERWRITE
        try:
            try:
                top_patch.get_file(as_file_path).copy_contents_from(file_path)
            except KeyError:
                top_patch.add_file(FileData.new_as_copy(as_file_path, top_patch, file_path))
        except OSError as edata:
            RCTX.stderr.write(edata)
            return CmdResult.ERROR
        RCTX.stdout.write(_("{0}: file copied to \"{1}\" in patch \"{2}\".\n").format(rel_subdir(file_path), rel_subdir(as_file_path), top_patch.name))
        return CmdResult.OK

def do_create_new_patch(patch_name, description):
    """Create a new patch with the given name and description (after the top patch)"""
    with open_db(mutable=True) as DB:
        old_top = DB.top_patch
        try:
            DB.create_new_patch(patch_name, description)
        except DarnItPatchExists:
            RCTX.stderr.write(_("patch \"{0}\" already exists.\n").format(patch_name))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        if old_top and old_top.needs_refresh:
            RCTX.stderr.write(_("Previous top patch (\"{0}\") needs refreshing.\n").format(old_top.name))
            return CmdResult.WARNING
        return CmdResult.OK

def do_delete_files_in_top_patch(file_paths):
    with open_db(mutable=True) as DB:
        top_patch = _get_top_patch(DB)
        if top_patch is None:
            return CmdResult.ERROR
        nonexists = 0
        ioerrors = 0
        for file_path in iter_prepending_subdir(file_paths):
            if not os.path.exists(file_path):
                RCTX.stderr.write(_("{0}: file does not exist. Ignored.\n").format(rel_subdir(file_path)))
                nonexists += 1
                continue
            if not top_patch.has_file_with_path(file_path):
                top_patch.add_file(FileData.new(file_path, top_patch))
            try:
                os.remove(file_path)
            except OSError as edata:
                RCTX.stderr.write(edata)
                ioerrors += 1
                continue
            top_patch.get_file(file_path).do_refresh()
            RCTX.stdout.write(_("{0}: file deleted within patch \"{1}\".\n").format(rel_subdir(file_path), top_patch.name))
        return CmdResult.OK if (ioerrors == 0 and len(file_paths) > nonexists) else CmdResult.ERROR

def do_delete_kept_patches(patch_names):
    with open_db(mutable=True) as DB:
        retval = CmdResult.OK
        for patch_name in patch_names:
            try:
                DB.delete_kept_patch(patch_name)
            except DarnItUnknownPatch:
                retval = CmdResult.ERROR
                RCTX.stderr.write(_("{0}: unknown patch.\n").format(patch_name))
        return retval

def do_drop_files_fm_patch(patch_name, file_paths):
    """Drop the named file from the named patch"""
    with open_db(mutable=True) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if patch is None:
            return CmdResult.ERROR
        elif patch.is_applied and not patch.is_top_patch:
            RCTX.stderr.write("Patch \"{0}\" is a NON-top applied patch. Aborted.".format(patch.name))
            return CmdResult.ERROR
        issued_warning = False
        for file_path, file_path_rel_subdir in iter_with_subdir(file_paths):
            if patch.has_file_with_path(file_path):
                patch.drop_named_file(file_path)
                RCTX.stdout.write(_("{0}: file dropped from patch \"{1}\".\n").format(file_path_rel_subdir, patch.name))
            elif os.path.isdir(file_path):
                RCTX.stderr.write(_("{0}: is a directory: ignored.\n").format(file_path_rel_subdir))
                issued_warning = True
            else:
                RCTX.stderr.write(_("{0}: file not in patch \"{1}\": ignored.\n").format(file_path_rel_subdir, patch.name))
                issued_warning = True
        return CmdResult.WARNING if issued_warning else CmdResult.OK

def do_duplicate_patch(patch_name, as_patch_name, new_description):
    with open_db(mutable=True) as DB:
        if not is_valid_dir_name(as_patch_name):
            RCTX.stderr.write(_("\"{0}\" is not a valid name. {1}\n").format(as_patch_name, ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        try:
            new_patch = DB.duplicate_named_patch(patch_name, as_patch_name, new_description)
        except DarnItUnknownPatch:
            RCTX.stderr.write(_("{0}: patch is NOT known.\n").format(patch_name))
            return CmdResult.ERROR
        except DarnItPatchNeedsRefresh:
            RCTX.stderr.write(_("{0}: patch needs refresh.\n").format(patch_name))
            RCTX.stderr.write(_("Aborted.\n"))
            return CmdResult.ERROR | CmdResult.Suggest.REFRESH
        except DarnItPatchExists:
            RCTX.stderr.write(_("{0}: patch already in series.\n").format(as_patch_name))
            RCTX.stderr.write(_("Aborted.\n"))
            return CmdResult.ERROR | CmdResult.Suggest.RENAME
        RCTX.stdout.write(_("{0}: patch duplicated as \"{1}\".\n").format(patch_name, new_patch.name))
        return CmdResult.OK

def do_fold_epatch(epatch, absorb=False, force=False):
    assert not (force and absorb)
    with open_db(mutable=True) as DB:
        assert not (absorb and force)
        top_patch = _get_top_patch(DB)
        if not top_patch:
            return CmdResult.ERROR
        result = top_patch.do_fold_epatch(epatch, absorb=absorb, force=force)
        if top_patch.needs_refresh:
            RCTX.stdout.write(_("{0}: (top) patch needs refreshing.\n").format(top_patch.name))
            result = max(result, CmdResult.WARNING)
        return result

def do_fold_named_patch(patch_name, absorb=False, force=False, retain_copy=None):
    assert not (force and absorb)
    with open_db(mutable=True) as DB:
        patch = _get_patch(patch_name, DB)
        if not patch:
            return CmdResult.ERROR
        elif patch.is_applied:
            RCTX.stderr.write(_("{0}: patch is applied.\n").format(patch.name))
            return CmdResult.ERROR
        epatch = TextPatch(patch)
        top_patch = _get_top_patch(DB)
        if not top_patch:
            return CmdResult.ERROR
        result = top_patch.do_fold_epatch(epatch, absorb=absorb, force=force)
        if result == CmdResult.ERROR:
            retain_copy = True
        elif retain_copy is None: # value of True or False will override option
            retain_copy = options.get("remove", "keep_patch_backup")
        RCTX.stdout.write(_("\"{0}\": patch folded into patch \"{1}\".\n").format(patch_name, top_patch.name))
        if top_patch.needs_refresh:
            RCTX.stdout.write(_("{0}: (top) patch needs refreshing.\n").format(top_patch.name))
            result = max(result, CmdResult.WARNING)
        DB.remove_patch(patch, retain_copy=(result==CmdResult.ERROR) or retain_copy)
        if retain_copy:
            RCTX.stdout.write(_("Patch \"{0}\" is available for restoration.\n").format(patch_name))
        return result

def do_import_patch(epatch, patch_name, overwrite=False, absorb=False, force=False):
    with open_db(mutable=True) as DB:
        if DB.has_patch_with_name(patch_name):
            patch = DB.get_named_patch(patch_name)
            if not overwrite:
                RCTX.stderr.write(_("patch \"{0}\" already exists\n").format(patch_name))
                result = CmdResult.ERROR | CmdResult.Suggest.RENAME
                if not patch.is_applied:
                    result |= CmdResult.Suggest.OVERWRITE
                return result
            elif patch.is_applied:
                RCTX.stderr.write(_("patch \"{0}\" already exists and is applied. Cannot be overwritten.\n").format(patch_name))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME
            else:
                try:
                    DB.remove_patch(patch_name)
                except DarnItPatchError:
                    return CmdResult.ERROR
        elif not is_valid_dir_name(patch_name):
            RCTX.stderr.write(_("\"{0}\" is not a valid name. {1}\n").format(patch_name, ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        descr = utils.make_utf8_compliant(epatch.get_description())
        top_patch = DB.top_patch
        patch = DB.create_new_patch(patch_name, descr)
        if top_patch:
            RCTX.stdout.write(_("{0}: patch inserted after patch \"{1}\".\n").format(patch_name, top_patch.name))
        else:
            RCTX.stdout.write(_("{0}: patch inserted at start of series.\n").format(patch_name))
        result = patch.do_fold_epatch(epatch, absorb=absorb, force=force)
        if result & CmdResult.Suggest.FORCE_OR_ABSORB:
            DB.pop_top_patch()
            DB.remove_patch(patch)
        elif patch.needs_refresh:
            RCTX.stdout.write(_("{0}: (top) patch needs refreshing.\n").format(patch.name))
            result = max(result, CmdResult.WARNING)
        return result

def do_move_files_in_top_patch(file_paths, target_path, force=False, overwrite=False, make_dir=False):
    if len(file_paths) == 1:
        if os.path.isdir(rel_basedir(target_path)):
            new_file_path = os.path.join(target_path, os.path.basename(file_paths[0]))
            return do_rename_file_in_top_patch(file_paths[0], new_file_path, force=force, overwrite=overwrite)
        else:
            return do_rename_file_in_top_patch(file_paths[0], target_path, force=force, overwrite=overwrite)
    with open_db(mutable=True) as DB:
        top_patch = _get_top_patch(DB)
        if top_patch is None:
            return CmdResult.ERROR
        target_path = rel_basedir(target_path)
        if os.path.exists(target_path) and not os.path.isdir(target_path):
            RCTX.stderr.write(_("{0}: target must be a directory for multiple file move operation.\n").format(rel_subdir(target_path)))
            return CmdResult.ERROR
        file_paths = list(iter_prepending_subdir(file_paths))
        nonexistent_file_paths = [file_path for file_path in file_paths if not os.path.exists(file_path)]
        if nonexistent_file_paths:
            for file_path in nonexistent_file_paths:
                RCTX.stderr.write(_("{0}: file does not exist.\n").format(rel_subdir(file_path)))
            return CmdResult.ERROR
        target_file_paths = [os.path.join(target_path, os.path.basename(file_path)) for file_path in file_paths]
        if not overwrite:
            tfps_in_patch = [tfp for tfp in target_file_paths if top_patch.has_file_with_path(tfp)]
            tfps_exist = [tfp for tfp in target_file_paths if not top_patch.has_file_with_path(tfp) and os.path.exists(tfp)]
            if tfps_in_patch or tfps_exist:
                for target_file_path in tfps_in_patch:
                    RCTX.stderr.write(_("{0}: file already in patch.\n").format(rel_subdir(target_file_path)))
                for target_file_path in tfps_exist:
                    RCTX.stderr.write(_("{0}: file already exists.\n").format(rel_subdir(target_file_path)))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME | CmdResult.Suggest.OVERWRITE
        if not force:
            overlaps = DB.get_overlap_data(file_paths, top_patch)
            if len(overlaps) > 0:
                return overlaps.report_and_abort()
        if not os.path.isdir(target_path):
            if not make_dir:
                RCTX.stderr.write(_("{0}: does not exist. Use --mkdir to create it.\n").format(rel_subdir(target_path)))
                return CmdResult.ERROR
            else:
                try:
                    os.makedirs(target_path)
                except OSError as edata:
                    RCTX.stderr.write(str(edata))
                    return CmdResult.ERROR
        for file_path, target_file_path in zip(file_paths, target_file_paths):
            if file_path == target_file_path:
                continue
            try:
                top_patch.do_rename_file(file_path, target_file_path)
            except OSError as edata:
                RCTX.stderr.write(str(edata))
                return CmdResult.ERROR
            RCTX.stdout.write(_("{0}: file renamed to \"{1}\" in patch \"{2}\".\n").format(rel_subdir(file_path), rel_subdir(target_file_path), top_patch.name))
        return CmdResult.OK

def do_pop_top_patch(force=False):
    # TODO: implement non dummy version do_unapply_top_patch()
    with open_db(mutable=True) as DB:
        try:
            new_top_patch = DB.pop_top_patch(force=force)
        except DarnItNoPatchesApplied:
            RCTX.stderr.write(_("There are no applied patches to pop."))
            return CmdResult.ERROR
        except DarnItPatchNeedsRefresh:
            RCTX.stderr.write(_("Top patch (\"{0}\") needs to be refreshed.\n").format(DB.top_patch_name))
            return CmdResult.ERROR | CmdResult.Suggest.FORCE_OR_REFRESH
        if new_top_patch is None:
            RCTX.stdout.write(_("There are now no patches applied.\n"))
        else:
            RCTX.stdout.write(_("Patch \"{0}\" is now on top.\n").format(new_top_patch.name))
        return CmdResult.OK

def do_refresh_patch(patch_name=None):
    """Refresh the named (or top applied) patch"""
    with open_db(mutable=True) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if patch is None:
            return CmdResult.ERROR
        if not patch.is_applied:
            RCTX.stderr.write(_("Patch \"{0}\" is not applied\n").format(patch_name))
            return CmdResult.ERROR
        eflag = patch.do_refresh(stdout=RCTX.stdout)
        if eflag != CmdResult.OK:
            RCTX.stderr.write(_("Patch \"{0}\" requires another refresh after issues are resolved.\n").format(patch.name))
        else:
            RCTX.stdout.write(_("Patch \"{0}\" refreshed.\n").format(patch.name))
        return eflag

def do_remove_patch(patch_name, retain_copy=None):
    with open_db(mutable=True) as DB:
        if retain_copy is None: # value of True or False will override option
            retain_copy = options.get("remove", "keep_patch_backup")
        try:
            DB.remove_named_patch(patch_name, retain_copy=retain_copy)
        except DarnItUnknownPatch:
            RCTX.stderr.write(_("{0}: patch is NOT known.\n").format(patch_name))
            return CmdResult.ERROR
        except DarnItPatchIsApplied:
            RCTX.stderr.write(_("{0}: patch is applied and cannot be removed.\n").format(patch_name))
            return CmdResult.ERROR
        if retain_copy:
            RCTX.stdout.write(_("Patch \"{0}\" removed (but available for restoration).\n").format(patch_name))
        else:
            RCTX.stdout.write(_("Patch \"{0}\" removed.\n").format(patch_name))
        return CmdResult.OK

def do_rename_file_in_top_patch(file_path, new_file_path, force=False, overwrite=False):
    with open_db(mutable=True) as DB:
        top_patch = _get_top_patch(DB)
        if top_patch is None:
            return CmdResult.ERROR
        file_path = rel_basedir(file_path)
        new_file_path = rel_basedir(new_file_path)
        if file_path == new_file_path:
            return CmdResult.OK
        if not os.path.exists(file_path):
            RCTX.stderr.write(_("{0}: file does not exist.\n").format(rel_subdir(file_path)))
            return CmdResult.ERROR
        if not overwrite:
            if top_patch.has_file_with_path(new_file_path):
                RCTX.stderr.write(_("{0}: file already in patch.\n").format(rel_subdir(new_file_path)))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME | CmdResult.Suggest.OVERWRITE
            if os.path.exists(new_file_path):
                RCTX.stderr.write(_("{0}: file already exists.\n").format(rel_subdir(new_file_path)))
                return CmdResult.ERROR | CmdResult.Suggest.RENAME | CmdResult.Suggest.OVERWRITE
        if not force:
            overlaps = DB.get_overlap_data([file_path], top_patch)
            if len(overlaps) > 0:
                return overlaps.report_and_abort()
        try:
            top_patch.do_rename_file(file_path, new_file_path)
        except OSError as edata:
            RCTX.stderr.write(edata)
            return CmdResult.ERROR
        RCTX.stdout.write(_("{0}: file renamed to \"{1}\" in patch \"{2}\".\n").format(rel_subdir(file_path), rel_subdir(new_file_path), top_patch.name))
        return CmdResult.OK

def do_rename_patch(patch_name, new_name):
    with open_db(mutable=True) as DB:
        if DB.has_patch_with_name(new_name):
            RCTX.stderr.write(_("patch \"{0}\" already exists\n").format(new_name))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        elif not is_valid_dir_name(new_name):
            RCTX.stderr.write(_("\"{0}\" is not a valid name. {1}\n").format(new_name, ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        patch = _get_patch(patch_name, DB)
        if patch is None:
            return CmdResult.ERROR
        patch.name = new_name
        RCTX.stdout.write(_("{0}: patch renamed as \"{1}\".\n").format(patch_name, patch.name))
        return CmdResult.OK

def do_restore_patch(patch_name, as_patch_name):
    with open_db(mutable=True) as DB:
        if not is_valid_dir_name(as_patch_name):
            RCTX.stderr.write(_("\"{0}\" is not a valid name. {1}\n").format(as_patch_name, ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        try:
            DB.restore_named_patch(patch_name, as_patch_name)
        except DarnItUnknownPatch:
            RCTX.stderr.write(_("{0}: is NOT available for restoration\n").format(patch_name))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        except DarnItPatchExists:
            RCTX.stderr.write(_("{0}: Already exists in database\n").format(as_patch_name))
            return CmdResult.ERROR|CmdResult.Suggest.RENAME
        return CmdResult.OK

def do_scm_absorb_applied_patches(force=False, with_timestamps=False):
    with open_db(mutable=True) as DB:
        if not scm_ifce.get_current_ifce().in_valid_wspce:
            RCTX.stderr.write(_("Sources not under control of known SCM\n"))
            return CmdResult.ERROR
        if DB.applied_patch_count == 0:
            RCTX.stderr.write(_("There are no patches applied.\n"))
            return CmdResult.ERROR
        is_ready, msg = scm_ifce.get_current_ifce().is_ready_for_import()
        if not is_ready:
            RCTX.stderr.write(_(msg))
            return CmdResult.ERROR
        problem_count = 0
        for applied_patch in DB.iterate_applied_patches():
            if applied_patch.needs_refresh:
                problem_count += 1
                RCTX.stderr.write("{0}: requires refreshing\n".format(applied_patch.name))
            if not applied_patch.description:
                problem_count += 1
                RCTX.stderr.write("{0}: has no description\n".format(applied_patch.name))
        if problem_count > 0:
            return CmdResult.ERROR
        tempdir = tempfile.mkdtemp()
        patch_file_names = list()
        applied_patch_names = list()
        drop_atws = options.get("absorb", "drop_added_tws")
        has_atws = False
        empty_patch_count = 0
        for applied_patch in DB.iterate_applied_patches():
            fhandle, patch_file_name = tempfile.mkstemp(dir=tempdir)
            text_patch = TextPatch(applied_patch, with_timestamps=with_timestamps, with_stats=False)
            if drop_atws:
                atws_reports = text_patch.fix_trailing_whitespace()
                for file_path, atws_lines in atws_reports:
                    RCTX.stdout.write(_("\"{0}\": adds trailing white space to \"{1}\" at line(s) {{{2}}}: removed.\n").format(applied_patch.name, rel_subdir(file_path), ", ".join([str(line) for line in atws_lines])))
            else:
                atws_reports = text_patch.report_trailing_whitespace()
                for file_path, atws_lines in atws_reports:
                    RCTX.stderr.write(_("\"{0}\": adds trailing white space to \"{1}\" at line(s) {{{2}}}.\n").format(applied_patch.name, rel_subdir(file_path), ", ".join([str(line) for line in atws_lines])))
                has_atws = has_atws or len(atws_reports) > 0
            os.write(fhandle, str(text_patch).encode())
            os.close(fhandle)
            if len(text_patch.diff_pluses) == 0:
                RCTX.stderr.write(_("\"{0}\": has no absorbable content.\n").format(applied_patch.name))
                empty_patch_count += 1
            patch_file_names.append(patch_file_name)
            applied_patch_names.append(applied_patch.name)
        if not force and has_atws:
            shutil.rmtree(tempdir)
            return CmdResult.ERROR
        if empty_patch_count > 0:
            shutil.rmtree(tempdir)
            return CmdResult.ERROR
        while DB.applied_patch_count > 0:
            try:
                DB.pop_top_patch()
            except DarnItNoPatchesApplied:
                RCTX.stderr.write(_("There are no applied patches to pop."))
                return CmdResult.ERROR
            except DarnItPatchNeedsRefresh:
                RCTX.stderr.write(_("Top patch (\"{0}\") needs to be refreshed.\n").format(DB.top_patch_name))
                return CmdResult.ERROR | CmdResult.Suggest.FORCE_OR_REFRESH
        ret_code = CmdResult.OK
        count = 0
        for patch_file_name in patch_file_names:
            result = scm_ifce.get_current_ifce().do_import_patch(patch_file_name)
            RCTX.stdout.write(result.stdout)
            RCTX.stderr.write(result.stderr)
            if result.ecode != 0:
                RCTX.stderr.write("Aborting")
                ret_code = CmdResult.ERROR
                break
            count += 1
        retain_copy = options.get("remove", "keep_patch_backup")
        for patch_name in applied_patch_names[0:count]:
            try:
                DB.remove_named_patch(patch_name, retain_copy=retain_copy)
            except DarnItPatchIsApplied:
                RCTX.stderr.write(_("{0}: is applied and cannot be removed.\n").format(patch_name))
                ret_code = CmdResult.ERROR
                break
            if retain_copy:
                RCTX.stdout.write(_("Patch \"{0}\" removed (but available for restoration).\n").format(patch_name))
            else:
                RCTX.stdout.write(_("Patch \"{0}\" removed.\n").format(patch_name))
        while count < len(applied_patch_names):
            DB.push_next_patch()
            count += 1
        shutil.rmtree(tempdir)
        return ret_code

def do_select_guards(guards):
    with open_db(mutable=True) as DB:
        if guards is None:
            guards = []
        bad_guard_count = 0
        for guard in guards:
            if guard.startswith("+") or guard.startswith("-"):
                RCTX.stderr.write(_("{0}: guard names may NOT begin with \"+\" or \"-\".\n").format(guard))
                bad_guard_count += 1
        if bad_guard_count > 0:
            RCTX.stderr.write(_("Aborted.\n"))
            return CmdResult.ERROR|CmdResult.Suggest.EDIT
        DB.set_selected_guards(guards)
        RCTX.stdout.write(_("{{{0}}}: is now the set of selected guards.\n").format(", ".join(DB.get_selected_guards())))
        return CmdResult.OK

def do_set_patch_description(patch_name, text):
    with open_db(mutable=True) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if not patch:
            return CmdResult.ERROR
        old_description = patch.description
        patch.description = _tidy_text(text)
        if old_description != patch.description:
            change_lines = difflib.ndiff(old_description.splitlines(True), patch.description.splitlines(True))
            RCTX.stdout.write("".join(change_lines))
        return CmdResult.OK

def do_set_patch_guards(patch_name, pos_guards, neg_guards):
    with open_db(mutable=True) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if not patch:
            return CmdResult.ERROR
        patch.do_set_guards(pos_guards, neg_guards)
        pos_guard_set, neg_guard_set = patch.guards
        RCTX.stdout.write(_("{0}: patch positive guards = {{{1}}}\n").format(patch_name, ", ".join(sorted(pos_guard_set))))
        RCTX.stdout.write(_("{0}: patch negative guards = {{{1}}}\n").format(patch_name, ", ".join(sorted(neg_guard_set))))
        return CmdResult.OK

def do_set_patch_guards_fm_list(patch_name, guards_list):
    if guards_list is None:
        guards_list = []
    pos_guards = [grd[1:] for grd in guards_list if grd.startswith("+")]
    neg_guards = [grd[1:] for grd in guards_list if grd.startswith("-")]
    if len(guards_list) != (len(pos_guards) + len(neg_guards)):
        RCTX.stderr.write(_("Guards must start with \"+\" or \"-\" and contain no whitespace.\n"))
        RCTX.stderr.write( _("Aborted.\n"))
        return CmdResult.ERROR | CmdResult.Suggest.EDIT
    return do_set_patch_guards(patch_name, pos_guards, neg_guards)

def do_set_patch_guards_fm_str(patch_name, guards_str):
    return do_set_patch_guards_fm_list(patch_name, guards_str.split())

def do_set_series_description(description):
    try:
        with open(_DESCRIPTION_FILE_PATH, "w") as f_obj:
            f_obj.write(description)
    except IOError as edata:
        RCTX.stderr.write(edata)
        return CmdResult.ERROR
    return CmdResult.OK

def do_unapply_top_patch(force=False):
    return do_pop_top_patch(force=force)

# GETs

def all_applied_patches_refreshed():
    # NB: the exception handling is for the case we're not in a darning pgnd
    try:
        with open_db(mutable=False) as DB:
            if DB.applied_patch_count == 0:
                return False
            for applied_patch in DB.iterate_applied_patches():
                if applied_patch.needs_refresh:
                    return False
            return True
    except OSError:
        return False

def report_blobs_status():
    with open_db(mutable=False) as DB:
        content_check = DB.check_content()
        ref_count_check = DB.validate_ref_counts()
        retval = CmdResult.OK
        if content_check.orphans:
            retval = CmdResult.ERROR
            for orphan in content_check.orphans:
                RCTX.stderr.write("{0}: content is orphaned.\n".format(orphan))
        if content_check.missing:
            retval = CmdResult.ERROR
            for missing in content_check.missing:
                RCTX.stderr.write("{0}: content is missing.\n".format(missing))
        if content_check.bad_content:
            retval = CmdResult.ERROR
            for bad_content in content_check.bad_content:
                RCTX.stderr.write("{0}: content is invalid.\n".format(bad_content))
        for git_hex_hash, count in ref_count_check:
            retval = CmdResult.ERROR
            RCTX.stderr.write("{0}: reference count is out by {1}.\n".format(git_hex_hash, count))
        return retval

def get_applied_patch_count():
    # NB: the exception handling is for the case we're not in a darning pgnd
    try:
        with open_db(mutable=False) as DB:
            count = DB.applied_patch_count
    except OSError:
        count = 0
    return count

def get_combined_diff_for_files(file_paths, with_timestamps=False):
    with open_db(mutable=False) as DB:
        if DB.combined_patch is None:
            RCTX.stderr.write("No patches applied.\n")
            return ""
        if file_paths:
            file_paths = list(iter_prepending_subdir(file_paths))
            unknown_file_paths = [file_path for file_path in file_paths if not DB.combined_patch.has_file_with_path(file_path)]
            if unknown_file_paths:
                for file_path in unknown_file_paths:
                    RCTX.stderr.write("{0}: file is not in any applied patch.\n".format(rel_subdir(file_path)))
                return ""
        return DB.combined_patch.get_text_diff(file_paths, with_timestamps=with_timestamps)

def get_combined_diff_pluses_for_files(file_paths, with_timestamps=False):
    with open_db(mutable=False) as DB:
        if DB.combined_patch is None:
            RCTX.stderr.write("No patches applied.\n")
            return ""
        if file_paths:
            file_paths = list(iter_prepending_subdir(file_paths))
            unknown_file_paths = [file_path for file_path in file_paths if not DB.combined_patch.has_file_with_path(file_path)]
            if unknown_file_paths:
                for file_path in unknown_file_paths:
                    RCTX.stderr.write("{0}: file is not in any applied patch.\n".format(rel_subdir(file_path)))
                return ""
        return DB.combined_patch.get_diff_pluses(file_paths, with_timestamps=with_timestamps)

def get_combined_patch_file_table():
    """Get a table of file data for all applied patches"""
    with open_db(mutable=False) as DB:
        if DB.combined_patch is None:
            assert DB.applied_patch_count == 0
            return []
        return DB.combined_patch.get_files_table()

def get_combined_textpatch(with_timestamps=False):
    return NotImplemented

def get_diff_for_files(file_paths, patch_name, with_timestamps=False):
    with open_db(mutable=False) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if patch is None:
            return False
        if file_paths:
            base_file_paths = list(iter_prepending_subdir(file_paths))
            file_paths_set = patch.get_file_paths_set(base_file_paths)
            if len(base_file_paths) != len(file_paths_set):
                for file_path, base_file_path in zip(file_paths, base_file_paths):
                    if base_file_path not in file_paths_set:
                        RCTX.stderr.write("{0}: file is not in patch \"{1}\".\n".format(file_path, patch.name))
                return False
            file_iter = (patch.get_file(file_path) for file_path in base_file_paths)
        else:
            file_iter = patch.iterate_files_sorted()
        diffs = (file_data.get_diff_text(with_timestamps=with_timestamps) for file_data in file_iter)
        return "".join(diffs)

def get_diff_pluses_for_files(file_paths, patch_name, with_timestamps=False):
    with open_db(mutable=False) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        if patch is None:
            return False
        if file_paths:
            base_file_paths = list(iter_prepending_subdir(file_paths))
            file_paths_set = patch.get_file_paths_set(base_file_paths)
            if len(base_file_paths) != len(file_paths_set):
                for file_path, base_file_path in zip(file_paths, base_file_paths):
                    if base_file_path not in file_paths_set:
                        RCTX.stderr.write("{0}: file is not in patch \"{1}\".\n".format(file_path, patch.name))
                return False
            file_iter = (patch.get_file(file_path) for file_path in base_file_paths)
        else:
            file_iter = patch.iterate_files_sorted()
        return [file_data.get_diff_plus(with_timestamps=with_timestamps) for file_data in file_iter]

def get_extdiff_files_for(file_path, patch_name):
    with open_db(mutable=False) as DB:
        return DB.get_named_patch(patch_name).get_file(file_path).get_extdiff_paths()

def get_filepaths_not_in_patch(patch_name, file_paths):
    if not file_paths:
        return []
    with open_db(mutable=False) as DB:
        if patch_name:
            patch_file_paths_set = DB.get_named_patch(patch_name).get_file_paths_set()
        else:
            patch_file_paths_set = DB.top_patch.get_file_paths_set()
        return [file_path for file_path in file_paths if file_path not in patch_file_paths_set]

def get_kept_patch_names():
    with open_db(mutable=False) as DB:
        return DB.get_kept_patch_names()

def get_named_or_top_patch_name(patch_name):
    """Return the name of the named or top patch if patch_name is None or None if patch_name is not a valid patch_name"""
    with open_db(mutable=False) as DB:
        patch = _get_named_or_top_patch(patch_name, DB)
        return None if patch is None else patch.name

def get_outstanding_changes_below_top():
    with open_db(mutable=False) as DB:
        if DB.applied_patch_count == 0:
            return OverlapData()
        skip_set = DB.top_patch.get_file_paths_set()
        unrefreshed = {}
        for applied_patch in DB.iterate_applied_patches(stop=-1, backwards=True):
            apfiles = applied_patch.get_filepaths()
            if apfiles:
                apfiles_set = set(apfiles) - skip_set
                for apfile in apfiles_set:
                    if applied_patch.get_file(apfile).needs_refresh:
                        unrefreshed[apfile] = applied_patch
                skip_set |= apfiles_set
        uncommitted = set(scm_ifce.get_current_ifce().get_files_with_uncommitted_changes()) - skip_set
        return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

def get_patch_description(patch_name):
    with open_db(mutable=False) as DB:
        return DB.get_named_patch(patch_name).description

def get_patch_file_table(patch_name=None):
    with open_db(mutable=False) as DB:
        patch = DB.top_patch if patch_name is None else DB.get_named_patch(patch_name)
        return patch.get_files_table() if patch else []

def get_patch_guards(patch_name=None):
    with open_db(mutable=False) as DB:
        patch = DB.top_patch if patch_name is None else DB.get_named_patch(patch_name)
        return patch.guards if patch else None

def get_patch_table_data():
    with open_db(mutable=False) as DB:
        return [patch.get_table_row() for patch in DB.iterate_series()]

def get_reconciliation_paths(file_path):
    with open_db(mutable=False) as DB:
        return DB.top_patch.get_file(file_path).get_reconciliation_paths()

def get_selected_guards():
    with open_db(mutable=False) as DB:
        return DB.get_selected_guards()

def get_series_description():
    with open(_DESCRIPTION_FILE_PATH, "r") as f_obj:
        return f_obj.read()

def get_textpatch(patch_name, with_timestamps=False):
    with open_db(mutable=False) as DB:
        return TextPatch(DB.get_named_patch(patch_name), with_timestamps=with_timestamps)

def get_top_patch_for_file(file_path):
    with open_db(mutable=False) as DB:
        return DB.get_top_patch_for_file(file_path)

def is_blocked_by_guard(patch_name):
    with open_db(mutable=False) as DB:
        return DB.get_named_patch(patch_name).is_blocked_by_guard

def is_patch_applied(patch_name):
    """Is the named patch applied?"""
    with open_db(mutable=False) as DB:
        return DB.get_named_patch(patch_name).is_applied

def is_patch_refreshed(patch_name):
    """Is the named patch in need of refresh?"""
    with open_db(mutable=False) as DB:
        return not DB.get_named_patch(patch_name).needs_refresh

def is_pushable():
    with open_db(mutable=False) as DB:
        return DB.is_pushable

def is_top_patch(patch_name):
    with open_db(mutable=False) as DB:
        return DB.get_named_patch(patch_name).is_top_patch

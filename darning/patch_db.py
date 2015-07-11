### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>
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
Implement a patch stack management database
'''

import collections
import cPickle
import os
import stat
import copy
import shutil
import atexit
import time
import re
import difflib
import errno
import sys
import zlib
import tempfile

from contextlib import contextmanager

from .cmd_result import CmdResult

from . import rctx as RCTX
from . import i18n
from . import scm_ifce
from . import runext
from . import utils
from . import patchlib
from . import fsdb
from . import options
from . import gitbase85
from . import gitdelta

# A convenience tuple for sending an original and patched version of something
_O_IP_PAIR = collections.namedtuple('_O_IP_PAIR', ['original_version', 'patched_version'])
# A convenience tuple for sending original, patched and stashed versions of something
_O_IP_S_TRIPLET = collections.namedtuple('_O_IP_S_TRIPLET', ['original_version', 'patched_version', 'stashed_version'])

class Failure(object):
    '''Report failure'''
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
        return _('Failure({0})').format(self.msg)

def _do_apply_diff_to_file(filepath, diff, delete_empty=False):
    patch_cmd_hdr = ['patch', '--merge', '--force', '-p1', '--batch', ]
    patch_cmd = patch_cmd_hdr + (['--remove-empty-files', filepath] if delete_empty else [filepath])
    result = runext.run_cmd(patch_cmd, input_text=str(diff))
    # move all but the first line of stdout to stderr
    # drop first line so that reports can be made relative to subdir
    olines = result.stdout.splitlines(True)
    prefix = '{0}: '.format(rel_subdir(filepath))
    # Put file name at start of line so they make sense on their own
    if len(olines) > 1:
        stderr = prefix + prefix.join(olines[1:] + result.stderr.splitlines(True))
    elif result.stderr:
        stderr = prefix + prefix.join(result.stderr.splitlines(True))
    else:
        stderr = ''
    return CmdResult(result.ecode, '', stderr)

class PickeExtensibleObject(object):
    '''A base class for pickleable objects that can cope with modifications'''
    RENAMES = dict()
    NEW_FIELDS = dict()
    def __setstate__(self, state):
        self.__dict__ = state
        for old_field in self.RENAMES:
            if old_field in self.__dict__:
                self.__dict__[self.RENAMES[old_field]] = self.__dict__.pop(old_field)
    def __getstate__(self):
        return self.__dict__
    def __getattr__(self, attr):
        if attr in self.NEW_FIELDS:
            return self.NEW_FIELDS[attr]
        raise AttributeError

class ZippedData(object):
    ZLIB_COMPRESSION_LEVEL = 6
    def __init__(self, data):
        if data is not None:
            self.raw_len = len(data)
            self.zipped_data = zlib.compress(bytes(data), self.ZLIB_COMPRESSION_LEVEL)
        else:
            self.raw_len = None
            self.zipped_data = None
    def __bool__(self):
        return self.zipped_data is not None
    @property
    def raw_data(self):
        return zlib.decompress(self.zipped_data)
    @property
    def zipped_len(self):
        return len(self.zipped_data)

class BinaryDiff(patchlib.Diff):
    def __init__(self, fm_data, to_data):
        patchlib.Diff.__init__(self, 'binary', [], None, hunks=None)
        self.contents = ZippedData(to_data)
        self.orig_contents = ZippedData(fm_data)
    def __str__(self):
        text = 'GIT binary patch\n'
        text += self.binary_diff_body_text(self.orig_contents, self.contents)
        text += self.binary_diff_body_text(self.contents, self.orig_contents)
        return text
    def fix_trailing_whitespace(self):
        return []
    def report_trailing_whitespace(self):
        return []
    def get_diffstat_stats(self):
        return patchlib.DiffStat.Stats()
    def binary_diff_body_text(self, fm_data, to_data):
        text = ''
        delta = None
        if fm_data.raw_len and to_data.raw_len:
            delta = ZippedData(gitdelta.diff_delta(fm_data.raw_data, to_data.raw_data))
        if delta and delta.zipped_len < to_data.zipped_len:
            text += 'delta {0}\n{1}\n'.format(delta.raw_len, ''.join(gitbase85.encode_to_lines(delta.zipped_data)))
        else:
            text += 'literal {0}{1}\n\n'.format(to_data.raw_len, ''.join(gitbase85.encode_to_lines(to_data.zipped_data)))
        return text

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
            RCTX.stderr.write(_('{0}: file has uncommitted SCM changes.\n').format(rfilepath))
        for filepath in sorted(self.unrefreshed):
            rfilepath = rel_subdir(filepath)
            opatch = self.unrefreshed[filepath]
            RCTX.stderr.write(_('{0}: file has unrefreshed changes in (applied) patch "{1}".\n').format(rfilepath, opatch.name))
        RCTX.stderr.write(_('Aborted.\n'))
        return CmdResult.ERROR_SUGGEST_FORCE_ABSORB_OR_REFRESH if len(self.unrefreshed) > 0 else CmdResult.ERROR_SUGGEST_FORCE_OR_ABSORB

class GenericFileData(PickeExtensibleObject):
    def get_presence(self):
        if self.orig_mode is None:
            return FileData.Presence.ADDED
        elif self.after_mode is None:
            return FileData.Presence.REMOVED
        else:
            return FileData.Presence.EXTANT
    def _generate_diff_preamble(self, after_mode, after_hash, old_combined=False):
        if self.came_from_path:
            lines = ['diff --git {0} {1}\n'.format(os.path.join('a', self.came_from_path), os.path.join('b', self.path)), ]
        else:
            lines = ['diff --git {0} {1}\n'.format(os.path.join('a', self.path), os.path.join('b', self.path)), ]
        if self.before_mode is None:
            if after_mode is not None:
                lines.append('new file mode {0:07o}\n'.format(after_mode))
        elif after_mode is None:
            lines.append('deleted file mode {0:07o}\n'.format(self.before_mode))
        else:
            if self.before_mode != after_mode:
                lines.append('old mode {0:07o}\n'.format(self.before_mode))
                lines.append('new mode {0:07o}\n'.format(after_mode))
        if not old_combined and self.came_from_path:
            if self.came_as_rename:
                lines.append('rename from {0}\n'.format(self.came_from_path))
                lines.append('rename to {0}\n'.format(self.path))
            else:
                lines.append('copy from {0}\n'.format(self.came_from_path))
                lines.append('copy to {0}\n'.format(self.path))
        if self.binary:
            hash_line = 'index {0}'.format(self.before_hash if self.before_hash else '0' *48)
            hash_line += '..{0}'.format(after_hash if after_hash else '0' *48)
            hash_line += ' {0:07o}\n'.format(after_mode) if self.before_mode == after_mode else '\n'
            lines.append(hash_line)
        return patchlib.Preamble.parse_lines(lines)
    def _has_actionable_preamble(self, after_mode, old_combined=False):
        if self.before_mode is None and after_mode is not None:
            return True
        elif self.before_mode != after_mode:
            return True
        elif not old_combined and self.came_from_path:
            return True
        return False
    def _generate_diff(self, fm_file, to_file, with_timestamps=False):
        fm_exists = os.path.exists(fm_file)
        if os.path.exists(to_file):
            to_name_label = os.path.join('b', self.path)
            to_time_stamp = _pts_for_path(to_file) if with_timestamps else None
            with open(to_file, 'rb') as fobj:
                to_contents = fobj.read()
        else:
            to_name_label = '/dev/null'
            to_time_stamp = _PTS_ZERO if with_timestamps else None
            to_contents = ''
        if fm_exists:
            fm_name_label = os.path.join('a', self.came_from_path if self.came_from_path else self.path)
            fm_time_stamp = _pts_for_path(fm_file) if with_timestamps else None
            with open(fm_file, 'rb') as fobj:
                fm_contents = fobj.read()
        else:
            fm_name_label = '/dev/null'
            fm_time_stamp = _PTS_ZERO if with_timestamps else None
            fm_contents = ''
        if to_contents == fm_contents:
            return None
        if to_contents.find('\000') != -1 or fm_contents.find('\000') != -1:
            return BinaryDiff(fm_contents, to_contents)
        diffgen = difflib.unified_diff(fm_contents.splitlines(True), to_contents.splitlines(True),
            fromfile=fm_name_label, tofile=to_name_label, fromfiledate=fm_time_stamp, tofiledate=to_time_stamp)
        diff_lines = list()
        for diff_line in diffgen:
            if diff_line.endswith((os.linesep, '\n')):
                diff_lines.append(diff_line)
            else:
                diff_lines.append(diff_line + '\n')
                diff_lines.append('\ No newline at end of file\n')
        return patchlib.Diff.parse_lines(diff_lines)

class FileData(GenericFileData):
    '''Change data for a single file'''
    RENAMES = { 'before_sha1' : 'before_hash', 'after_sha1' : 'after_hash', }
    class Presence(object):
        ADDED = patchlib.FilePathPlus.ADDED
        REMOVED = patchlib.FilePathPlus.DELETED
        EXTANT = patchlib.FilePathPlus.EXTANT
    class Validity(object):
        REFRESHED, NEEDS_REFRESH, UNREFRESHABLE = range(3)
    class Status(collections.namedtuple('Status', ['presence', 'validity'])):
        def __str__(self): return ""
    MERGE_CRE = re.compile('^(<<<<<<<|>>>>>>>).*$')
    def __init__(self, filepath, patch, overlaps=OverlapData(), came_from_path=None, as_rename=False):
        self.path = filepath
        self.patch = patch
        self.came_from_path = came_from_path
        self.came_as_rename = as_rename
        self.renamed_to = None
        self.reset_reference_paths()
        self.diff = None
        if self.came_from_path:
            self.orig_mode = None
            came_from_data = self.patch.files.get(self.came_from_path, None)
            if came_from_data:
                self.before_mode = came_from_data.orig_mode
                self.before_hash = utils.get_git_hash_for_file(came_from_data.cached_orig_path)
            else:
                # self.came_from_path must exist so no need for "try"
                self.before_mode = utils.get_mode_for_file(self.came_from_path)
                self.before_hash = utils.get_git_hash_for_file(self.came_from_path)
        else:
            self.orig_mode = utils.get_mode_for_file(self.path)
            self.before_mode = self.orig_mode
            self.before_hash = utils.get_git_hash_for_file(self.path)
        self.after_hash = self.before_hash
        self.after_mode = self.before_mode
        if self.patch.is_applied():
            self.do_cache_original(overlaps)
            if came_from_path is None:
                # The file won't exist yet so "needs refresh" will be True
                self.do_stash_current(None)
    def clone_for_patch(self, patch):
        file_data = FileData(self.path, patch)
        file_data.came_from_path = self.came_from_path
        file_data.came_as_rename = self.came_as_rename
        file_data.renamed_to = self.renamed_to
        file_data.diff = self.diff
        file_data.orig_mode = self.orig_mode
        file_data.before_mode = self.before_mode
        file_data.before_hash = self.before_hash
        file_data.after_mode = self.after_mode
        file_data.after_hash = self.after_hash
        file_data.reset_reference_paths()
        return file_data
    def set_before_file_path(self):
        if self.came_from_path:
            if self.came_from_path in self.patch.files:
                # if we're in the middle of a patch rename we can't trust
                # came_from_path's cached_orig_path field so generate it
                self.before_file_path = self.patch.generate_cached_original_path(self.came_from_path)
            else:
                self.before_file_path = self.came_from_path
        elif self.renamed_to:
            self.before_file_path = '/dev/null'
        else:
            self.before_file_path = self.cached_orig_path
    def set_before_mode(self):
        # came_from has precedence over renamed_to
        if self.came_from_path is None:
            if self.renamed_to is None:
                self.before_mode = self.orig_mode
            else:
                self.before_mode = None
        elif self.came_from_path in self.patch.files:
            self.before_mode = self.patch.files[self.came_from_path].orig_mode
        else:
            self.before_mode = utils.get_mode_for_file(self.before_file_path)
    def reset_reference_paths(self):
        # have this as a function to make patch renaming easier
        self.cached_orig_path = self.patch.generate_cached_original_path(self.path)
        self.stashed_path = os.path.join(self.patch.stash_dir_path, self.path)
        self.set_before_file_path()
    def reset_renamed_to(self, renamed_to):
        self.renamed_to = renamed_to
        self.reset_reference_paths()
        self.set_before_mode()
        if self.patch.is_applied():
            self.do_refresh()
    def reset_came_from(self, came_from_path, came_as_rename):
        self.came_from_path = came_from_path
        self.came_as_rename = came_as_rename
        self.reset_reference_paths()
        self.set_before_mode()
        if self.patch.is_applied():
            self.do_refresh()
    def do_stash_current(self, overlapping_patch):
        '''Stash the current version of this file for later reference'''
        assert self.patch.is_applied()
        assert self.needs_refresh() is False
        self.do_delete_stash()
        source = self.path if overlapping_patch is None else overlapping_patch.files[self.path].cached_orig_path
        if os.path.exists(source):
            utils.ensure_file_dir_exists(self.stashed_path)
            shutil.copy2(source, self.stashed_path)
            utils.do_turn_off_write_for_file(self.stashed_path)
    def do_delete_stash(self):
        if os.path.exists(self.stashed_path):
            os.remove(self.stashed_path)
    def _copy_refreshed_version_to(self, target_name):
        if not self.needs_refresh():
            if os.path.exists(self.path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(self.path, target_name)
            return
        if self.binary:
            if os.path.exists(self.stashed_path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(self.stashed_path, target_name)
            return
        if os.path.exists(self.cached_orig_path):
            utils.ensure_file_dir_exists(target_name)
            shutil.copy2(self.cached_orig_path, target_name)
        elif self.diff:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write('')
        if self.diff:
            _do_apply_diff_to_file(target_name, self.diff)
    def do_cache_original(self, overlaps=OverlapData()):
        '''Cache the original of the named file for this patch'''
        assert self.patch.is_applied()
        assert self.get_overlapping_patch() is None
        olurpatch = overlaps.unrefreshed.get(self.path, None)
        if olurpatch:
            olurpatch.files[self.path]._copy_refreshed_version_to(self.cached_orig_path)
        elif self.path in overlaps.uncommitted:
            scm_ifce.get_ifce().copy_clean_version_to(self.path, self.cached_orig_path)
        elif os.path.exists(self.path):
            # We'll try to preserve links when we pop patches
            # so we move the file to the cached originals' directory and then make
            # a copy (without links) in the working directory
            utils.ensure_file_dir_exists(self.cached_orig_path)
            shutil.move(self.path, self.cached_orig_path)
            if not self.renamed_to:
                # Don't copy the file back if it's been renamed
                shutil.copy2(self.cached_orig_path, self.path)
        if os.path.exists(self.cached_orig_path):
            # Make the cached original read only to prevent accidental change
            # Save the original value as we need this so that we need to reset it on pop
            self.orig_mode = utils.do_turn_off_write_for_file(self.cached_orig_path)
        else:
            self.orig_mode = None
    def get_reconciliation_paths(self):
        assert self.patch.is_top_patch
        # make it hard for the user to (accidentally) create these files if they don't exist
        before = self.before_file_path if os.path.exists(self.before_file_path) else '/dev/null'
        stashed = self.stashed_path if os.path.exists(self.stashed_path) else '/dev/null'
        # The user has to be able to cope with the main file not existing (meld can)
        return _O_IP_S_TRIPLET(before, self.path, stashed)
    @property
    def binary(self):
        return isinstance(self.diff, BinaryDiff) or isinstance(self.diff, patchlib.GitBinaryDiff)
    def needs_refresh(self):
        '''Does this file need a refresh?'''
        if not self.patch.is_applied():
            # None means "undeterminable"
            return None
        olpatch = self.get_overlapping_patch()
        if olpatch is not None:
            olfd = olpatch.files[self.path]
            if self.after_mode != olfd.orig_mode:
                return True
            elif self.after_hash != utils.get_git_hash_for_file(olfd.cached_orig_path):
                return True
        else:
            if self.after_mode != utils.get_mode_for_file(self.path):
                return True
            elif self.after_hash != utils.get_git_hash_for_file(self.path):
                return True
            elif self.came_from_path and not self.came_as_rename:
                return self.before_hash != utils.get_git_hash_for_file(self.before_file_path)
        return False
    def _has_unresolved_merges(self, overlapping_patch):
        '''Does this file contain unresolved merge problems?'''
        def _file_has_unresolved_merges(filepath):
            if os.path.exists(filepath):
                for line in open(filepath).readlines():
                    if FileData.MERGE_CRE.match(line):
                        return True
            return False
        if overlapping_patch is not None:
            return _file_has_unresolved_merges(overlapping_patch.files[self.path].cached_orig_path)
        else:
            return _file_has_unresolved_merges(self.path)
    def has_unresolved_merges(self):
        '''Does this file contain unresolved merge problems?'''
        if not self.patch.is_applied():
            # None means "undeterminable"
            return None
        return self._has_unresolved_merges(overlapping_patch=self.get_overlapping_patch())
    def get_presence(self):
        if self.orig_mode is None:
            return FileData.Presence.ADDED
        elif self.after_mode is None:
            return FileData.Presence.REMOVED
        else:
            return FileData.Presence.EXTANT
    def get_applied_validity(self):
        assert self.patch.is_applied()
        if self.needs_refresh():
            if self._has_unresolved_merges(self.get_overlapping_patch()):
                return FileData.Validity.UNREFRESHABLE
            else:
                return FileData.Validity.NEEDS_REFRESH
        else:
            return FileData.Validity.REFRESHED
    def get_validity(self):
        if not self.patch.is_applied():
            return None
        return self.get_applied_validity()
    def get_overlapping_patch(self):
        '''Return the applied patch (if any) which overlaps the this file'''
        assert self.patch.is_applied()
        return self.patch.get_overlapping_patch_for_path(self.path)
    @property
    def related_file_data(self):
        if self.came_from_path:
            if self.came_as_rename:
                return fsdb.RFD(self.came_from_path, fsdb.Relation.MOVED_FROM)
            else:
                return fsdb.RFD(self.came_from_path, fsdb.Relation.COPIED_FROM)
        elif self.renamed_to:
            return fsdb.RFD(self.renamed_to, fsdb.Relation.MOVED_TO)
        return None
    def generate_diff_preamble(self, overlapping_patch, old_combined=False):
        if self.patch.is_applied():
            if overlapping_patch is not None:
                after_mode = overlapping_patch.files[self.path].before_mode
                after_hash = overlapping_patch.files[self.path].before_hash
            elif os.path.exists(self.path):
                after_mode = utils.get_mode_for_file(self.path)
                after_hash = utils.get_git_hash_for_file(self.path)
            else:
                after_mode = self.before_mode if self.renamed_to else None
                after_hash = None
        else:
            after_mode = self.after_mode
            after_hash = self.after_hash
        return self._generate_diff_preamble(after_mode, after_hash, old_combined=old_combined)
    def has_actionable_preamble(self, old_combined=False):
        if self.patch.is_applied():
            overlapping_patch = None if old_combined else self.get_overlapping_patch()
            if overlapping_patch is not None:
                after_mode = overlapping_patch.files[self.path].before_mode
            elif os.path.exists(self.path):
                after_mode = utils.get_mode_for_file(self.path)
            else:
                after_mode = self.before_mode if self.renamed_to else None
        else:
            after_mode = self.after_mode
        return self._has_actionable_preamble(after_mode, old_combined)
    def generate_diff(self, overlapping_patch, old_combined=False, with_timestamps=False):
        assert self.patch.is_applied()
        assert overlapping_patch is None or not old_combined
        to_file = self.path if overlapping_patch is None else overlapping_patch.files[self.path].cached_orig_path
        fm_file = self.cached_orig_path if old_combined else self.before_file_path
        return self._generate_diff(fm_file, to_file, with_timestamps=with_timestamps)
    def get_diff_plus(self, old_combined=False, as_refreshed=False, with_timestamps=False):
        assert not (old_combined and as_refreshed)
        overlapping_patch = None if (old_combined or not self.patch.is_applied()) else self.get_overlapping_patch()
        preamble = self.generate_diff_preamble(overlapping_patch=overlapping_patch, old_combined=old_combined)
        if self.patch.is_applied() and not as_refreshed:
            diff = self.generate_diff(overlapping_patch=overlapping_patch, old_combined=old_combined, with_timestamps=with_timestamps)
        else:
            diff = copy.deepcopy(self.diff)
        diff_plus = patchlib.DiffPlus([preamble], diff)
        if not old_combined and self.renamed_to and self.after_mode is None:
            diff_plus.trailing_junk.append(_('# Renamed to: {0}\n').format(self.renamed_to))
        return diff_plus
    def do_refresh(self, quiet=True, with_timestamps=False):
        '''Refresh the named file in this patch'''
        assert self.patch.is_applied()
        overlapping_patch = self.get_overlapping_patch()
        if self._has_unresolved_merges(overlapping_patch):
            # ensure this file shows up as needing refresh
            self.after_hash = False
            RCTX.stderr.write(_('"{0}": file has unresolved merge(s).\n').format(rel_subdir(self.path)))
            return CmdResult.ERROR
        overlapping_file_data = None if overlapping_patch is None else overlapping_patch.files[self.path]
        f_exists = os.path.exists(self.path if overlapping_file_data is None else overlapping_file_data.cached_orig_path)
        if f_exists or os.path.exists(self.before_file_path):
            self.diff = self.generate_diff(overlapping_patch, with_timestamps=with_timestamps)
            if f_exists:
                self.after_mode = utils.get_mode_for_file(self.path) if overlapping_file_data is None else overlapping_file_data.orig_mode
                if not quiet and self.before_mode is not None and self.before_mode != self.after_mode:
                    RCTX.stdout.write(_('"{0}": mode {1:07o} -> {2:07o}.\n').format(rel_subdir(self.path), self.before_mode, self.after_mode))
            else:
                self.after_mode = None
            if not quiet and self.diff is not None:
                RCTX.stdout.write(str(self.diff))
        else:
            self.diff = None
            self.after_mode = None
            if not quiet:
                RCTX.stdout.write(_('"{0}": file does not exist\n').format(rel_subdir(self.path)))
        self.before_hash = utils.get_git_hash_for_file(self.before_file_path)
        self.after_hash = utils.get_git_hash_for_file(self.path if overlapping_file_data is None else overlapping_file_data.cached_orig_path)
        self.do_stash_current(overlapping_patch)
        return CmdResult.OK

class CombinedFileData(GenericFileData):
    '''Store data for changes to a file as a combined patch'''
    def __init__(self, top, bottom=None):
        self.top = top
        self.bottom = bottom
        # For the time being, don't track copies and renames in combined patches
        self.renamed_to = None
        self.came_from_path = None
        self.came_as_rename = False
    @property
    def binary(self):
        return self.top.binary or self.bottom.binary
    @property
    def before_mode(self):
        return self.bottom.orig_mode
    def __getattr__(self, aname):
        if aname in ('before_hash', 'orig_mode', 'cached_orig_path'):
            return self.bottom.__dict__[aname]
        elif aname in ('after_mode', 'path',):
            return self.top.__dict__[aname]
        else:
            raise AttributeError(aname)
    def was_ephemeral(self):
        return self.orig_mode is None and not os.path.exists(self.path)
    def get_applied_validity(self):
        return self.top.get_applied_validity()
    def generate_diff_preamble(self):
        if os.path.exists(self.path):
            after_mode = utils.get_mode_for_file(self.path)
            after_hash = utils.get_git_hash_for_file(self.path)
        else:
            after_mode = self.before_mode if self.renamed_to else None
            after_hash = None
        return self._generate_diff_preamble(after_mode, after_hash)
    def has_actionable_preamble(self, old_combined=False):
        if os.path.exists(self.path):
            after_mode = utils.get_mode_for_file(self.path)
        else:
            after_mode = self.before_mode if self.renamed_to else None
        return self._has_actionable_preamble(after_mode, old_combined)
    def generate_diff(self, with_timestamps=False):
        to_file = self.path
        fm_file = self.cached_orig_path
        return self._generate_diff(fm_file, to_file, with_timestamps=with_timestamps)
    def get_diff_plus(self, with_timestamps=False):
        assert not self.was_ephemeral()
        preamble = self.generate_diff_preamble()
        diff = self.generate_diff(with_timestamps=with_timestamps)
        diff_plus = patchlib.DiffPlus([preamble], diff)
        if self.renamed_to and self.after_mode is None:
            diff_plus.trailing_junk.append(_('# Renamed to: {0}\n').format(self.renamed_to))
        return diff_plus

def _pts_tz_str(tz_seconds=None):
    '''Return the timezone as a string suitable for use in patch header'''
    if tz_seconds is None:
        tz_seconds = -time.timezone
    if tz_seconds > 0:
        hrs = tz_seconds / 3600
    else:
        hrs = -(-tz_seconds / 3600)
    mins = (abs(tz_seconds) % 3600) / 60
    return '{0:0=+3}{1:02}'.format(hrs, mins)

_PTS_TEMPL = '%Y-%m-%d %H:%M:%S.{0:09} ' + _pts_tz_str()

def _pts_str(secs=None):
    '''Return the "in patch" timestamp string for "secs" seconds'''
    ts_str = time.strftime(_PTS_TEMPL, time.localtime(secs))
    return ts_str.format(int((secs % 1) * 1000000000))

_PTS_ZERO = _pts_str(0)

def _pts_for_path(path):
    '''Return the "in patch" timestamp string for "secs" seconds'''
    return _pts_str(os.path.getmtime(path))

from .pm_ifce import PatchState

class PatchTable(object):
    Row = collections.namedtuple('Row', ['name', 'state', 'pos_guards', 'neg_guards'])

class PatchData(PickeExtensibleObject):
    '''Store data for changes to a number of files as a single patch'''
    NEW_FIELDS = { "_db" : None }
    Guards = collections.namedtuple('Guards', ['positive', 'negative'])
    def __init__(self, name, description, database=None):
        self._db = database
        self.files = dict()
        self.set_name(name, first=True)
        self.description = _tidy_text(description) if description is not None else ''
        self.pos_guards = set()
        self.neg_guards = set()
    def clone_as(self, name, description, database):
        patch_data = PatchData(name, description, database)
        for file_path, file_data in self.files.iteritems():
            patch_data.files[file_path] = file_data.clone_for_patch(patch_data)
        patch_data.pos_guards = self.pos_guards.copy()
        patch_data.neg_guards = self.neg_guards.copy()
        return patch_data
    def set_db(self, db):
        self._db = db
    def set_name(self, newname, first=False):
        if not first:
            old_cached_orig_dir_path = self.cached_orig_dir_path
            old_stash_dir_path = self.stash_dir_path
        self.name = newname
        self.cached_orig_dir_path = DataBase.cached_original_dir_path(self.name)
        self.stash_dir_path = DataBase.stash_dir_path(self.name)
        if not first and os.path.exists(old_cached_orig_dir_path):
            os.rename(old_cached_orig_dir_path, self.cached_orig_dir_path)
        if not first:
            #TODO: find out why this fires when restoring deleted patch
            assert os.path.exists(old_stash_dir_path)
            os.rename(old_stash_dir_path, self.stash_dir_path)
        else:
            os.mkdir(self.stash_dir_path)
        for file_data in self.files.values():
            file_data.reset_reference_paths()
    def generate_cached_original_path(self, filepath):
        '''Return the path of the cached original for the given file path'''
        return os.path.join(self.cached_orig_dir_path, filepath)
    def get_overlapping_patch_for_path(self, filepath):
        '''Return the applied patch above me (if any) which contains this file'''
        try:
            index = self._db.applied_patches.index(self) + 1
        except ValueError:
            return None
        while index < len(self._db.applied_patches):
            if filepath in self._db.applied_patches[index].files:
                return self._db.applied_patches[index]
            index += 1
        return None
    def add_file(self, file_data):
        assert not self.is_applied() or self._db.get_top_patch() == self
        assert file_data.path not in self.files
        self.files[file_data.path] = file_data
        if self.is_applied():
            self._db.add_to_combined_patch(file_data)
        for cf_fd in [fd for fd in self.files.values() if fd.came_from_path == file_data.path]:
            cf_fd.set_before_file_path()
    def drop_file(self, filepath):
        if self.is_applied():
            self._db.drop_fm_combined_patch(filepath)
        del self.files[filepath]
        for cf_fd in [fd for fd in self.files.values() if fd.came_from_path == filepath]:
            cf_fd.set_before_file_path()
    def do_drop_file(self, filepath):
        '''Drop the named file from this patch'''
        assert filepath in self.files
        renamed_from = self.files[filepath].came_from_path if self.files[filepath].came_as_rename else None
        self.files[filepath].do_delete_stash()
        if not self.is_applied():
            # not much to do here
            self.drop_file(filepath)
            if renamed_from is not None:
                self.files[renamed_from].reset_renamed_to(None)
            return
        assert self._db.applied_patches[-1] == self
        corig_f_path = self.files[filepath].cached_orig_path
        if os.path.exists(filepath):
            os.remove(filepath)
        if os.path.exists(corig_f_path):
            os.chmod(corig_f_path, self.files[filepath].orig_mode)
            shutil.move(corig_f_path, filepath)
        renamed_to = self.files[filepath].renamed_to
        renamed_from = self.files[filepath].came_from_path if self.files[filepath].came_as_rename else None
        self.drop_file(filepath)
        if renamed_to is not None and renamed_to in self.files:
            # Second check is necessary in the case where a renamed
            # file is dropped and the source is dropped as a result.
            self.files[renamed_to].reset_came_from(filepath, False)
        if renamed_from is not None and renamed_from in self.files:
            self.files[renamed_from].reset_renamed_to(None)
        if renamed_from is not None:
            self.files[renamed_from].reset_renamed_to(None)
    def get_filepaths(self, filepaths=None):
        '''
        Return the names of the files in this patch.
        If filepaths is not None restrict the returned list to names that
        are also in filepaths.
        '''
        if filepaths is None:
            return [filepath for filepath in self.files]
        else:
            return [filepath for filepath in self.files if filepath in filepaths]
    def get_filepaths_set(self, filepaths=None):
        '''Return the set of names for the files in this patch.
        If filepaths is not None restrict the returned set to names that
        are also in filepaths.
        '''
        return set(self.get_filepaths(filepaths=filepaths))
    def get_files_table(self):
        is_applied = self.is_applied()
        if is_applied:
            table = [fsdb.Data(fde.path, FileData.Status(fde.get_presence(), fde.get_applied_validity()), fde.related_file_data) for fde in self.files.values()]
        else:
            table = [fsdb.Data(fde.path, FileData.Status(fde.get_presence(), None), fde.related_file_data) for fde in self.files.values()]
        return table
    def get_table_row(self):
        if not self.is_applied():
            state = PatchState.NOT_APPLIED
        elif self.needs_refresh():
            if self.has_unresolved_merges():
                state = PatchState.APPLIED_UNREFRESHABLE
            else:
                state = PatchState.APPLIED_NEEDS_REFRESH
        else:
            state = PatchState.APPLIED_REFRESHED
        return PatchTable.Row(name=self.name, state=state, pos_guards=self.pos_guards, neg_guards=self.neg_guards)
    def is_applied(self):
        '''Is this patch applied?'''
        return self in self._db.applied_patches
    @property
    def is_top_patch(self):
        return self._db.applied_patches and self._db.applied_patches[-1] == self
    def is_blocked_by_guard(self):
        '''Is the this patch blocked from being applied by any guards?'''
        if (self.pos_guards & self._db.selected_guards) != self.pos_guards:
            return True
        if len(self.neg_guards & self._db.selected_guards) != 0:
            return True
        return False
    def is_overlapped(self):
        '''Are any files in this patch overlapped by applied patches?'''
        for filepath in self.files:
            if self.get_overlapping_patch_for_path(filepath) is not None:
                return True
        return False
    def is_pushable(self):
        '''Is this patch pushable?'''
        return not self.is_applied() and not self.is_blocked_by_guard()
    def needs_refresh(self):
        '''Does this patch need a refresh?'''
        for file_data in self.files.values():
            if file_data.needs_refresh():
                return True
        return False
    def has_unresolved_merges(self):
        '''Is this patch refreshable? i.e. no unresolved merges'''
        for file_data in self.files.values():
            if file_data.has_unresolved_merges():
                return True
        return False

class CombinedPatchData(PickeExtensibleObject):
    '''Store data for changes to a number of files as a combined patch'''
    def __init__(self, prev):
        self.files = dict()
        self.prev = prev
        if prev:
            for filepath in prev.files:
                self.files[filepath] = copy.copy(prev.files[filepath])
    def add_file(self, file_data):
        if self.prev:
            prev_fd = self.prev.files.get(file_data.path, None)
            bottom = prev_fd.bottom if prev_fd else file_data
        else:
            bottom = file_data
        self.files[file_data.path] = CombinedFileData(file_data, bottom)
    def drop_file(self, filepath):
        del self.files[filepath]
        if self.prev and filepath in self.prev.files:
            self.files[filepath] = copy.copy(self.prev.files[filepath])
    def get_files_table(self):
        table = []
        for file_data in self.files.values():
            if file_data.was_ephemeral():
                continue
            status = FileData.Status(file_data.get_presence(), file_data.get_applied_validity())
            table.append(fsdb.Data(file_data.path, status, None))
        return table
    def get_files_digest(self):
        return utils.get_digest_for_file_list(self.files.keys())

class DataBase(PickeExtensibleObject):
    '''Storage for an ordered sequence/series of patches'''
    NEW_FIELDS = { 'applied_patches' : None, 'combined_patch' : False, }
    _DIR = '.darning.dbd'
    _ORIGINALS_DIR = os.path.join(_DIR, 'orig')
    _STASH_DIR = os.path.join(_DIR, 'stash')
    _FILE = os.path.join(_DIR, 'database')
    _LOCK_FILE = os.path.join(_DIR, 'lock_db')
    def __init__(self, description, host_scm=None):
        self.description = _tidy_text(description) if description else ''
        self.selected_guards = set()
        self.series = list()
        self.applied_patches = list()
        self.combined_patch = None
        self.kept_patches = dict()
        self.host_scm = host_scm
    @staticmethod
    def cached_original_dir_path(patchname):
        '''Return the path of the cached originals' directory for the given patch name'''
        return os.path.join(DataBase._ORIGINALS_DIR, patchname)
    @staticmethod
    def stash_dir_path(patchname):
        '''Return the path of the cached originals' directory for the given patch name'''
        return os.path.join(DataBase._STASH_DIR, patchname)
    @staticmethod
    def exists():
        '''Does the current directory contain a patch database?'''
        return os.path.isfile(DataBase._FILE)
    def get_top_patch(self):
        return self.applied_patches[-1] if self.applied_patches else None
    def series_index_for_patchname(self, patchname):
        '''Get the series index for the patch with the given name'''
        index = 0
        for patch in self.series:
            if patch.name == patchname:
                return index
            index += 1
        return None
    def series_index_for_top(self):
        '''Get the index in series of the top applied patch'''
        return self.series.index(self.applied_patches[-1]) if len(self.applied_patches) > 0 else None
    def series_index_for_next(self):
        '''Get the index of the next patch to be applied'''
        top = self.series_index_for_top()
        index = 0 if top is None else top + 1
        while index < len(self.series):
            if self.series[index].is_blocked_by_guard():
                index += 1
                continue
            return index
        return None
    def patch_fm_name(self, patchname):
        '''Get the patch with the given name'''
        patch_index = self.series_index_for_patchname(patchname)
        if patch_index is not None:
            return self.series[patch_index]
        else:
            return None
    def has_patch_with_name(self, patchname):
        return self.series_index_for_patchname(patchname) is not None
    def is_named_patch_applied(self, patchname):
        '''Is the named patch currently applied?'''
        return self.patch_fm_name(patchname) in self.applied_patches
    def insert_patch(self, patch, after=None):
        '''Insert given patch into series after the top or nominated patch'''
        assert self.series_index_for_patchname(patch.name) is None
        if after is not None:
            index = self.series_index_for_patchname(after) + 1
            assert self.patches[index] not in self.applied_patches or self.applied_patches[-1] == self.patches[index]
        else:
            top_index = self.series_index_for_top()
            index = top_index + 1 if top_index is not None else 0
        patch.set_db(self)
        self.series.insert(index, patch)
    def append_to_applied(self, patch):
        self.applied_patches.append(patch)
        if self.combined_patch is not False:
            # Using new mechanism
            self.combined_patch = CombinedPatchData(self.combined_patch)
    def add_to_combined_patch(self, file_data):
        if self.combined_patch is not False:
            # Using new mechanism
            self.combined_patch.add_file(file_data)
    def drop_fm_combined_patch(self, filepath):
        if self.combined_patch is not False:
            # Using new mechanism
            self.combined_patch.drop_file(filepath)
    def pop_top_patch(self):
        del self.applied_patches[-1]
        if self.combined_patch is not False:
            # Using new mechanism
            self.combined_patch = self.combined_patch.prev

_SUB_DIR = None

def rel_subdir(filepath):
    return filepath if _SUB_DIR is None else os.path.relpath(filepath, _SUB_DIR)

def rel_basedir(filepath):
    if os.path.isabs(filepath):
        filepath = os.path.relpath(filepath)
    elif _SUB_DIR is not None:
        filepath = os.path.join(_SUB_DIR, filepath)
    return filepath

def prepend_subdir(filepaths):
    for findex in range(len(filepaths)):
        filepaths[findex] = rel_basedir(filepaths[findex])
    return filepaths

def find_base_dir(dir_path=None, remember_sub_dir=False):
    '''Find the nearest directory above that contains a database'''
    global _SUB_DIR
    if dir_path is None:
        dir_path = os.getcwd()
    subdir_parts = []
    while True:
        if os.path.isdir(os.path.join(dir_path, DataBase._DIR)):
            _SUB_DIR = None if not subdir_parts else os.path.join(*subdir_parts)
            return dir_path
        else:
            dir_path, basename = os.path.split(dir_path)
            if not basename:
                break
            if remember_sub_dir:
                subdir_parts.insert(0, basename)
    return None

def do_create_db(description):
    '''Create a patch database in the current directory?'''
    def rollback():
        '''Undo steps that were completed before failure occured'''
        for filnm in [DataBase._FILE, DataBase._LOCK_FILE ]:
            if os.path.exists(filnm):
                os.remove(filnm)
        for dirnm in [DataBase._ORIGINALS_DIR, DataBase._DIR]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    root = find_base_dir(remember_sub_dir=False)
    if root is not None:
        RCTX.stderr.write(_('Inside existing playground: "{0}".\n').format(os.path.relpath(root)))
        return CmdResult.ERROR
    elif os.path.exists(DataBase._DIR):
        if os.path.exists(DataBase._ORIGINALS_DIR) and os.path.exists(DataBase._FILE):
            RCTX.stderr.write(_('Database already exists.\n'))
        else:
            RCTX.stderr.write(_('Database directory exists.\n'))
        return CmdResult.ERROR
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(DataBase._DIR, dir_mode)
        os.mkdir(DataBase._ORIGINALS_DIR, dir_mode)
        os.mkdir(DataBase._STASH_DIR, dir_mode)
        open(DataBase._LOCK_FILE, "w").write("0")
        db_obj = DataBase(description, None)
        fobj = open(DataBase._FILE, 'wb', stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        try:
            cPickle.dump(db_obj, fobj)
        finally:
            fobj.close()
    except OSError as edata:
        rollback()
        RCTX.stderr.write(edata.strerror)
        return CmdResult.ERROR
    except Exception:
        rollback()
        raise
    return CmdResult.OK

def _set_of_dirs_in_dir(dir_path):
    return {item for item in os.listdir(dir_path) if os.path.isdir(os.path.join(dir_path, item))}

def _generate_applied_patch_list():
    '''Get an ordered list of applied patches'''
    applied = list()
    applied_set = _set_of_dirs_in_dir(DataBase._ORIGINALS_DIR)
    if len(applied_set) == 0:
        return []
    for patch in _DB.series:
        if patch.name in applied_set:
            applied.append(patch)
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                break
    assert len(applied_set) == 0, 'Series/applied patches discrepency'
    return applied

def _verify_applied_patch_list(applied):
    '''Verify that the applied list is consistent with DataBase._ORIGINALS_DIR.'''
    applied_set = _set_of_dirs_in_dir(DataBase._ORIGINALS_DIR)
    assert len(applied_set) == len(applied), 'Series/applied patches discrepency'
    for patch in applied:
        assert patch.name in applied_set, 'Series/applied patches discrepency'

# Make a context manager locking/opening/closing database
@contextmanager
def open_db(mutable=False):
    assert DataBase.exists()
    import fcntl
    # Cater for the case where we're in an old playground
    try:
        fobj = os.open(DataBase._LOCK_FILE, os.O_RDWR if mutable else os.O_RDONLY)
    except OSError as edata:
        if edata.errno != errno.ENOENT:
            raise
        open(DataBase._LOCK_FILE, "w").write("0")
        fobj = os.open(DataBase._LOCK_FILE, os.O_RDWR if mutable else os.O_RDONLY)
    fcntl.lockf(fobj, fcntl.LOCK_EX if mutable else fcntl.LOCK_SH)
    db = cPickle.load(open(DataBase._FILE, 'rb'))
    # TODO: get rid of this code when version upgraded
    for patch in db.series:
        patch.set_db(db)
    if db.applied_patches is None:
        db.applied_patches = _generate_applied_patch_list()
    else:
        _verify_applied_patch_list(db.applied_patches)
    try:
        yield db
    finally:
        if mutable:
            cPickle.dump(db, open(DataBase._FILE, 'wb'))
        fcntl.lockf(fobj, fcntl.LOCK_UN)
        os.close(fobj)

# The next three functions are wrappers for common functionality in
# modules exported functions.  They may emit output to stderr and
# should only be used where that is a requirement.  Use DataBase
# methods otherwise.
def _get_patch(patchname, db):
    '''Return the named patch'''
    patch_index = db.series_index_for_patchname(patchname)
    if patch_index is None:
        RCTX.stderr.write(_('{0}: patch is NOT known.\n').format(patchname))
        return None
    return  db.series[patch_index]

def _get_top_patch(db):
    '''Return the top applied patch'''
    top_patch = db.get_top_patch()
    if top_patch is None:
        RCTX.stderr.write(_('No patches applied.\n'))
        return None
    return top_patch

def _get_named_or_top_patch(patchname, db):
    '''Return the named or top applied patch'''
    return _get_patch(patchname, db) if patchname is not None else _get_top_patch(db)

def get_kept_patch_names():
    '''Get a list of names for patches that have been kept on removal'''
    with open_db(mutable=False) as _DB:
        return [kept_patch_name for kept_patch_name in sorted(_DB.kept_patches)]

def get_patch_file_table(patchname=None):
    with open_db(mutable=False) as _DB:
        if len(_DB.series) == 0:
            return []
        if patchname is None:
            top_patch = _DB.get_top_patch()
            return top_patch.get_files_table() if top_patch else []
        else:
            index = _DB.series_index_for_patchname(patchname)
            return _DB.series[index].get_files_table()

def _get_combined_patch_file_table_old(_DB):
    '''Get a table of file data for all applied patches'''
    class _Data(object):
        __slots__ = ['presence', 'validity', 'related_file_data']
        def __init__(self, presence, validity, related_file_data=None):
            self.presence = presence
            self.validity = validity
            self.related_file_data = related_file_data
    if len(_DB.applied_patches) == 0:
        return []
    file_map = {}
    for patch in _DB.applied_patches:
        for fde in patch.files.values():
            if fde.needs_refresh():
                if fde.has_unresolved_merges():
                    validity = FileData.Validity.UNREFRESHABLE
                else:
                    validity = FileData.Validity.NEEDS_REFRESH
            else:
                validity = FileData.Validity.REFRESHED
            if fde.path in file_map:
                file_map[fde.path].validity = validity
            else:
                file_map[fde.path] = _Data(fde.get_presence(), validity)
    table = []
    for filepath in sorted(file_map):
        data = file_map[filepath]
        table.append(fsdb.Data(filepath, FileData.Status(data.presence, data.validity), data.related_file_data))
    return table

def get_combined_patch_file_table():
    '''Get a table of file data for all applied patches'''
    with open_db(mutable=False) as _DB:
        if _DB.combined_patch is False:
            # the database is still using the old mechanism
            return _get_combined_patch_file_table_old(_DB)
        elif _DB.combined_patch is None:
            assert len(_DB.applied_patches) == 0
            return []
        return _DB.combined_patch.get_files_table()

def is_top_patch(patchname):
    '''Is the named patch the top applied patch?'''
    with open_db(mutable=False) as _DB:
        top_patch = _DB.get_top_patch()
        return top_patch and top_patch.name == patchname

def do_create_new_patch(patchname, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    with open_db(mutable=True) as _DB:
        if _DB.series_index_for_patchname(patchname) is not None:
            RCTX.stderr.write(_('patch "{0}" already exists.\n').format(patchname))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        elif not utils.is_valid_dir_name(patchname):
            RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        patch = PatchData(patchname, description, _DB)
        _DB.insert_patch(patch)
        old_top = _DB.get_top_patch()
        # Ignore result of apply as it cannot fail with no files in the patch
        _do_apply_next_patch(_DB)
        if old_top and old_top.needs_refresh():
            RCTX.stderr.write(_('Previous top patch ("{0}") needs refreshing.\n').format(old_top.name))
            return CmdResult.WARNING
        return CmdResult.OK

def do_rename_patch(patchname, newname):
    '''Rename an existing patch.'''
    with open_db(mutable=True) as _DB:
        if _DB.series_index_for_patchname(newname) is not None:
            RCTX.stderr.write(_('patch "{0}" already exists\n').format(newname))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        elif not utils.is_valid_dir_name(newname):
            RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(newname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        patch = _get_patch(patchname, _DB)
        if patch is None:
            return CmdResult.ERROR
        patch.set_name(newname)
        RCTX.stdout.write(_('{0}: patch renamed as "{1}".\n').format(patchname, patch.name))
        return CmdResult.OK

def do_import_patch(epatch, patchname, overwrite=False):
    '''Import an external patch with the given name (after the top patch)'''
    with open_db(mutable=True) as _DB:
        if _DB.has_patch_with_name(patchname):
            if not overwrite:
                RCTX.stderr.write(_('patch "{0}" already exists\n').format(patchname))
                result = CmdResult.ERROR | CmdResult.SUGGEST_RENAME
                if not _DB.is_named_patch_applied(patchname):
                    result |= CmdResult.SUGGEST_OVERWRITE
                return result
            elif _DB.is_named_patch_applied(patchname):
                RCTX.stderr.write(_('patch "{0}" already exists and is applied. Cannot be overwritten.\n').format(patchname))
                return CmdResult.ERROR | CmdResult.SUGGEST_RENAME
            else:
                result = _do_remove_patch(_DB, patchname)
                if result != CmdResult.OK:
                    return result
        elif not utils.is_valid_dir_name(patchname):
            RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        descr = utils.make_utf8_compliant(epatch.get_description())
        patch = PatchData(patchname, descr, _DB)
        renames = dict()
        for diff_plus in epatch.diff_pluses:
            filepath_plus = diff_plus.get_file_path_plus(epatch.num_strip_levels)
            filepath = filepath_plus.path
            came_from = None
            as_rename = False
            git_preamble = diff_plus.get_preamble_for_type('git')
            if isinstance(diff_plus.diff, patchlib.GitBinaryDiff) and (not git_preamble or 'index' not in git_preamble.extras):
                RCTX.stderr.write(_('git binary patch for file "{0}" has no index data.\n').format(filepath))
                return CmdResult.ERROR
            if git_preamble:
                bad_strip_level = False
                if 'copy from' in git_preamble.extras:
                    came_from = git_preamble.extras['copy from']
                    bad_strip_level = git_preamble.extras.get('copy to', None) != filepath
                elif 'rename from' in git_preamble.extras:
                    came_from = git_preamble.extras['rename from']
                    as_rename = True
                    renames[came_from] = filepath
                    bad_strip_level = preamble.extras.get('rename to', None) != filepath
                if bad_strip_level:
                    RCTX.stderr.write(_('git data for file "{0}" incompatible with strip level {1}.\n').format(rel_subdir(filepath), epatch.num_strip_levels))
                    return CmdResult.ERROR
            file_data = FileData(filepath, patch, came_from_path=came_from, as_rename=as_rename)
            file_data.diff = diff_plus.diff
            # let push know it may need to set this.
            file_data.after_mode = False if filepath_plus.status != patchlib.FilePathPlus.DELETED else None
            file_data.after_hash = False
            file_data.before_hash = False # make it clear this is an imported patch
            if git_preamble:
                for key in ['new mode', 'new file mode']:
                    if key in git_preamble.extras:
                        file_data.after_mode = int(git_preamble.extras[key], 8)
                        break
                index_str = git_preamble.extras.get('index', None)
                if index_str:
                    # If there's hash data in the patch we'll use it
                    get_hash = lambda text: None if int(text, 16) == 0 else text
                    match = re.match('^([a-fA-F0-9]+)..([a-fA-F0-9]+)( (\d*))?$', index_str)
                    file_data.before_hash = get_hash(match.group(1))
                    file_data.after_hash = get_hash(match.group(2))
            patch.add_file(file_data)
            RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(rel_subdir(file_data.path), patchname))
        for old_path in renames:
            if old_path not in patch.files:
                patch.add_file(FileData(old_path, patch))
                RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(rel_subdir(old_path), patchname))
            patch.files[old_path].renamed_to = renames[old_path]
            patch.files[old_path].set_before_file_path()
        _DB.insert_patch(patch)
        if _DB.applied_patches:
            RCTX.stdout.write(_('{0}: patch inserted after patch "{1}".\n').format(patchname, _DB.get_top_patch().name))
        else:
            RCTX.stdout.write(_('{0}: patch inserted at start of series.\n').format(patchname))
        return CmdResult.OK

def _do_fold_epatch(_DB, epatch, absorb=False, force=False):
    '''Fold an external patch into the top patch.'''
    assert not (absorb and force)
    top_patch = _get_top_patch(_DB)
    if not top_patch:
        return CmdResult.ERROR
    def _apply_diff_plus(diff_plus):
        filepath = diff_plus.get_file_path(epatch.num_strip_levels)
        RCTX.stdout.write(_('Patching file "{0}".\n').format(rel_subdir(filepath)))
        if drop_atws:
            atws_lines = diff_plus.fix_trailing_whitespace()
            if atws_lines:
                RCTX.stdout.write(_('Added trailing white space to "{0}" at line(s) {{{1}}}: removed before application.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in atws_lines])))
        else:
            atws_lines = diff_plus.report_trailing_whitespace()
            if atws_lines:
                RCTX.stderr.write(_('Added trailing white space to "{1}" at line(s) {{{2}}}.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in atws_lines])))
        if diff_plus.diff:
            result = _do_apply_diff_to_file(filepath, diff_plus.diff)
            if result.ecode == 0:
                RCTX.stderr.write(result.stdout)
            else:
                RCTX.stdout.write(result.stdout)
            RCTX.stderr.write(result.stderr)
        if os.path.exists(filepath):
            git_preamble = diff_plus.get_preamble_for_type('git')
            if git_preamble is not None:
                for key in ['new mode', 'new file mode']:
                    if key in git_preamble.extras:
                        os.chmod(filepath, int(git_preamble.extras[key], 8))
                        break
    if not force:
        new_file_list = []
        for diff_plus in epatch.diff_pluses:
            filepath = diff_plus.get_file_path(epatch.num_strip_levels)
            if filepath in top_patch.files:
                continue
            git_preamble = diff_plus.get_preamble_for_type('git')
            if git_preamble and ('copy from' in git_preamble.extras or 'rename from' in git_preamble.extras):
                continue
            new_file_list.append(filepath)
        overlaps = _get_overlap_data(_DB, new_file_list, top_patch)
        if not absorb and len(overlaps) > 0:
            return overlaps.report_and_abort()
    else:
        overlaps = OverlapData()
    drop_atws = options.get('push', 'drop_added_tws')
    copies = []
    renames = []
    creates = []
    # Do the caching of existing files first to obviate copy/rename problems
    for diff_plus in epatch.diff_pluses:
        filepath = diff_plus.get_file_path(epatch.num_strip_levels)
        git_preamble = diff_plus.get_preamble_for_type('git')
        copied_from = git_preamble.extras.get('copy from', None) if git_preamble else None
        renamed_from = git_preamble.extras.get('rename from', None) if git_preamble else None
        file_data = top_patch.files.get(filepath, None)
        if file_data is None:
            file_data = FileData(filepath, top_patch, overlaps=overlaps)
            top_patch.add_file(file_data)
        if renamed_from is not None:
            if renamed_from not in top_patch.files:
                top_patch.add_file(FileData(renamed_from, top_patch, overlaps=overlaps))
            renames.append((diff_plus, renamed_from))
        elif copied_from is not None:
            copies.append((diff_plus, copied_from))
        elif not os.path.exists(filepath):
            creates.append(diff_plus)
    # Now use patch to create any file created by the fold
    for diff_plus in creates:
        _apply_diff_plus(diff_plus)
    # Do any copying
    for diff_plus, came_from_path in copies:
        new_file_path = diff_plus.get_file_path(epatch.num_strip_levels)
        new_file_data = top_patch.files[new_file_path]
        record_copy = True
        src_file_path = came_from_path
        if src_file_path in top_patch.files:
            src_file_data = top_patch.files[src_file_path]
            if src_file_data.came_from_path:
                # this file was a copy or rename so refer to the original
                came_from_path = src_file_data.came_from_path
            else:
                # if this file was created by the patch we don't record the copy
                record_copy = os.path.exists(src_file_data.cached_orig_path)
        # We copy the current version here not the original
        # TODO: think about force/absorb ramifications HERE
        if os.path.exists(src_file_path):
            try:
                shutil.copy2(src_file_path, new_file_path)
            except OSError as edata:
                RCTX.stderr.write(edata)
        else:
            RCTX.stderr.write(_('{0}: failed to copy {1}.\n').format(rel_subdir(new_file_data.path), rel_subdir(new_file_data.came_from_path)))
        new_file_data.reset_came_from(came_from_path if record_copy else None, False)
    # Do any renaming
    for diff_plus, came_from_path in renames:
        new_file_path = diff_plus.get_file_path(epatch.num_strip_levels)
        new_file_data = top_patch.files[new_file_path]
        src_file_path = came_from_path
        as_rename = True
        is_boomerang = False
        src_file_data = top_patch.files.get(src_file_path, None)
        if src_file_data.came_from_path:
            if src_file_data.came_from_path == new_file_path:
                came_from_path = None
                as_rename = False
                is_boomerang = True
            else:
                came_from_path = src_file_data.came_from_path
                as_rename = src_file_data.came_as_rename
            if as_rename:
                top_patch.files[came_from_path].renamed_to = new_file_path
            if not os.path.exists(src_file_data.cached_orig_path):
                # Never existed so just forget about it
                if os.path.exists(src_file_data.stashed_path):
                    os.remove(src_file_data.stashed_path)
                top_patch.drop_file(src_file_path)
            else:
                # Becomes a deleted file unless user restores it (their choice)
                src_file_data.reset_came_from(None, False)
        elif not os.path.exists(src_file_data.cached_orig_path):
            # we're just renaming a file that was created in the top patch
            came_from_path = None
            as_rename = False
            if os.path.exists(src_file_data.stashed_path):
                os.remove(src_file_data.stashed_path)
            top_patch.drop_file(filepath)
        if not os.path.exists(src_file_path):
            RCTX.stderr.write(_('{0}: failed to rename {1}.\n').format(rel_subdir(new_file_data.path), rel_subdir(new_file_data.came_from_path)))
        else:
            try:
                os.rename(src_file_path, new_file_path)
            except OSError as edata:
                RCTX.stderr.write(edata)
        if came_from_path:
            new_file_data.reset_came_from(came_from_path, as_rename)
            top_patch.files[came_from_path].reset_renamed_to(new_file_path if as_rename else None)
        elif is_boomerang:
            new_file_data.reset_renamed_to(None)
    # Apply the remaining changes
    for diff_plus in epatch.diff_pluses:
        if diff_plus not in creates:
            _apply_diff_plus(diff_plus)
    # Make sure the before_file_path fields are all correct
    for file_data in top_patch.files.values():
        # This is necessary because renamed files may have been overwritten
        file_data.set_before_file_path()
    if top_patch.needs_refresh():
        RCTX.stdout.write(_('{0}: (top) patch needs refreshing.\n').format(top_patch.name))
        return CmdResult.WARNING
    return CmdResult.OK

def do_fold_epatch(epatch, absorb=False, force=False):
    with open_db(mutable=True) as _DB:
        return _do_fold_epatch(_DB, epatch, absorb=absorb, force=force)

def do_fold_named_patch(patchname, absorb=False, force=False):
    '''Fold a name internal patch into the top patch.'''
    with open_db(mutable=True) as _DB:
        assert not (absorb and force)
        patch = _get_patch(patchname, _DB)
        if not patch:
            return CmdResult.ERROR
        elif patch.is_applied():
            RCTX.stderr.write(_('{0}: patch is applied.\n').format(patch.name))
            return CmdResult.ERROR
        epatch = TextPatch(patch)
        result = _do_fold_epatch(_DB, epatch, absorb=absorb, force=force)
        if result not in [CmdResult.OK, CmdResult.WARNING]:
            return result
        _DB.series.remove(patch)
        RCTX.stdout.write(_('"{0}": patch folded into patch "{1}".\n').format(patchname, _DB.get_top_patch().name))
        return result

def get_outstanding_changes_below_top():
    '''Get the data detailing unfrefreshed/uncommitted files below the
    top patch.  I.e. outstanding changes.
    '''
    with open_db(mutable=False) as _DB:
        if not _DB.applied_patches:
            return OverlapData()
        top_patch = _DB.applied_patches[-1]
        skip_set = set([filepath for filepath in top_patch.files])
        unrefreshed = {}
        for applied_patch in reversed(_DB.applied_patches[:-1]):
            apfiles = applied_patch.get_filepaths()
            if apfiles:
                apfiles_set = set(apfiles) - skip_set
                for apfile in apfiles_set:
                    if applied_patch.files[apfile].needs_refresh():
                        unrefreshed[apfile] = applied_patch
                skip_set |= apfiles_set
        uncommitted = set(scm_ifce.get_ifce().get_files_with_uncommitted_changes()) - skip_set
        return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

def _get_overlap_data(_DB, filepaths, patch=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the files in filelist if they are added to the named
    (or next, if patchname is None) patch.
    '''
    assert patch is None or patch.is_applied()
    if not filepaths:
        return OverlapData()
    applied_patches = _DB.applied_patches if patch is None else _DB.applied_patches[:_DB.applied_patches.index(patch)]
    uncommitted = set(scm_ifce.get_ifce().get_files_with_uncommitted_changes(filepaths))
    remaining_files = set(filepaths)
    unrefreshed = {}
    for applied_patch in reversed(applied_patches):
        if len(uncommitted) + len(remaining_files) == 0:
            break
        apfiles = applied_patch.get_filepaths(remaining_files)
        if apfiles:
            apfiles_set = set(apfiles)
            remaining_files -= apfiles_set
            uncommitted -= apfiles_set
            for apfile in apfiles:
                if applied_patch.files[apfile].needs_refresh():
                    unrefreshed[apfile] = applied_patch
    return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

def get_file_diff(filepath, patchname, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_patchname(patchname)
        assert patch_index is not None
        patch = _DB.series[patch_index]
        assert filepath in patch.files
        return patch.files[filepath].get_diff_plus(with_timestamps=with_timestamps)

def get_diff_for_files(filepaths, patchname, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        patch = _get_named_or_top_patch(patchname, _DB)
        if patch is None:
            return False
        if filepaths:
            is_ok = True
            file_list = []
            prepend_subdir(filepaths)
            for filepath in filepaths:
                if filepath in patch.files:
                    file_list.append(patch.files[filepath])
                else:
                    is_ok = False
                    RCTX.stderr.write('{0}: file is not in patch "{1}".\n'.format(rel_subdir(filepath), patch.name))
            if not is_ok:
                return False
        else:
            file_list = [patch.files[filepath] for filepath in sorted(patch.files)]
        diff = ''
        for file_data in file_list:
            diff += str(file_data.get_diff_plus(with_timestamps=with_timestamps))
        return diff

def _get_file_combined_diff_old(_DB, filepath, with_timestamps=False):
    patch = None
    for applied_patch in _DB.applied_patches:
        if filepath in applied_patch.files:
            patch = applied_patch
            break
    assert patch is not None
    return patch.files[filepath].get_diff_plus(combined=True, with_timestamps=with_timestamps)

def get_file_combined_diff(filepath, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        if _DB.combined_patch is False:
            # Still using old DB
            return get_file_combined_diff_old(_DB, filepath, with_timestamps=with_timestamps)
        elif _DB.combined_patch is None or _DB.combined_patch.files[filepath].was_ephemeral():
            return None
        return _DB.combined_patch.files[filepath].get_diff_plus(with_timestamps=with_timestamps)

def _get_combined_diff_for_files_old(_DB, filepaths, with_timestamps=False):
    file_list = []
    if filepaths:
        is_ok = True
        prepend_subdir(filepaths)
        for filepath in filepaths:
            found = False
            for applied_patch in _DB.applied_patches:
                if filepath in applied_patch.files:
                    file_list.append(applied_patch.files[filepath])
                    found = True
                    break
            if not found:
                is_ok = False
                RCTX.stderr.write('{0}: file is not in any applied patch.\n'.format(rel_subdir(filepath)))
        if not is_ok:
            return False
    else:
        file_set = set()
        for applied_patch in _DB.applied_patches:
            for filepath in sorted(applied_patch.files):
                if filepath in file_set:
                    continue
                file_set.add(filepath)
                file_list.append(applied_patch.files[filepath])
    diff = ''
    for file_data in file_list:
        diff += str(file_data.get_diff_plus(combined=True, with_timestamps=with_timestamps))
    return diff

def get_combined_diff_for_files(filepaths, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        if _DB.combined_patch is False:
            # Still using old DB
            return get_combined_diff_for_files_old(_DB, filepaths, with_timestamps=with_timestamps)
        elif _DB.combined_patch is None:
            for filepath in filepaths:
                RCTX.stderr.write('{0}: file is not in any applied patch.\n'.format(filepath))
            return False
        elif filepaths:
            is_ok = True
            prepend_subdir(filepaths)
            for filepath in filepaths:
                if filepath not in _DB.combined_patch.files or _DB.combined_patch.files[filepath].was_ephemeral():
                    is_ok = False
                    RCTX.stderr.write('{0}: file is not in any applied patch.\n'.format(rel_subdir(filepath)))
            if not is_ok:
                return False
            diff = ''
            # send the diffs in the order the files were specified
            for filepath in filepaths:
                diff += str(_DB.combined_patch.files[filepath].get_diff_plus(with_timestamps=with_timestamps))
            return diff
        diff = ''
        for filepath in sorted(_DB.combined_patch.files):
            file_data = _DB.combined_patch.files[filepath]
            if file_data.was_ephemeral():
                continue
            diff += str(file_data.get_diff_plus(with_timestamps=with_timestamps))
        return diff

def _do_apply_next_patch(_DB, absorb=False, force=False):
    '''Apply the next patch in the series'''
    assert not (absorb and force)
    def _apply_file_data_patch(file_data, biggest_ecode):
        patch_ok = True
        if isinstance(file_data.diff, BinaryDiff):
            RCTX.stdout.write(_('Processing binary file "{0}".\n').format(rel_subdir(file_data.path)))
            if file_data.before_hash != utils.get_git_hash_for_file(file_data.path):
                RCTX.stderr.write(_('"{0}": binary file original has changed.\n').format(rel_subdir(file_data.path)))
            if file_data.after_mode is not None:
                try:
                    open(file_data.path, 'wb').write(file_data.diff.contents.raw_data)
                except TypeError, AttributeError:
                    # Handle patches in old database format
                    open(file_data.path, 'wb').write(file_data.diff.contents)
            elif os.path.exists(file_data.path):
                os.remove(file_data.path)
        elif isinstance(file_data.diff, patchlib.GitBinaryDiff):
            RCTX.stdout.write(_('Processing binary file "{0}" with imported patch.\n').format(rel_subdir(file_data.path)))
            if file_data.after_mode is None:
                # it was a delete
                if os.path.exists(file_data.path):
                    os.remove(file_data.path)
            elif file_data.diff.forward.method == patchlib.GitBinaryDiffData.LITERAL:
                # if it's literal just apply it.
                open(file_data.path, 'wb').write(file_data.diff.forward.data_raw)
            else:
                if file_data.before_hash != utils.get_git_hash_for_file(file_data.path):
                    # the original file has changed and it would be unwise to apply the delta
                    biggest_ecode = max(biggest_ecode, 2)
                    RCTX.stderr.write(_('"{0}": imported binary delta can not be applied.\n').format(rel_subdir(file_data.path)))
                else:
                    contents = open(file_data.path, 'rb').read()
                    try:
                        new_contents = gitdelta.patch_delta(contents, file_data.diff.forward.data_raw)
                    except gitdelta.PatchError as edata:
                        biggest_ecode = max(biggest_ecode, 2)
                        RCTX.stderr.write(_('"{0}": imported binary delta failed to apply: {1}.\n').format(rel_subdir(file_data.path), edata))
                    else:
                        open(file_data.path, 'wb').write(new_contents)
        elif file_data.diff:
            RCTX.stdout.write(_('Patching file "{0}".\n').format(rel_subdir(file_data.path)))
            if drop_atws:
                atws_lines = file_data.diff.fix_trailing_whitespace()
                if atws_lines:
                    RCTX.stdout.write(_('"{0}": added trailing white space to "{1}" at line(s) {{{2}}}: removed before application.\n').format(next_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in atws_lines])))
            else:
                atws_lines = file_data.diff.report_trailing_whitespace()
                if atws_lines:
                    RCTX.stderr.write(_('"{0}": added trailing white space to "{1}" at line(s) {{{2}}}.\n').format(next_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in atws_lines])))
            result = _do_apply_diff_to_file(file_data.path, file_data.diff, delete_empty=file_data.after_mode is None)
            biggest_ecode = max(biggest_ecode, result.ecode)
            patch_ok = result.ecode == 0 and not result.stderr
            if result.ecode != 0:
                RCTX.stderr.write(result.stdout)
            else:
                RCTX.stdout.write(result.stdout)
            RCTX.stderr.write(result.stderr)
        else:
            RCTX.stdout.write(_('Processing file "{0}".\n').format(rel_subdir(file_data.path)))
        if os.path.exists(file_data.path):
            if file_data.after_mode is False:
                # First push on an imported patch
                file_data.after_mode = utils.get_mode_for_file(file_data.path)
            elif file_data.after_mode is None:
                # This means we expect the file to be deleted but it wasn't
                # probably because it wasn't empty after the patch was applied.
                file_data.after_mode = utils.get_mode_for_file(file_data.path)
                patch_ok = False
            else:
                os.chmod(file_data.path, file_data.after_mode)
        elif file_data.after_mode is not None:
            # A non None after_mode means that the file existed when
            # the diff was made so a refresh will be required
            patch_ok = False
            biggest_ecode = max(biggest_ecode, 1)
            RCTX.stderr.write(_('Expected file not found.\n'))
            # set after mode to None so it shows up as a delete
            file_data.after_mode = None
        if not patch_ok:
            # Make sure it shows up as needing a refresh
            file_data.after_hash = False
        elif file_data.before_hash is False:
            # An imported patch (without hash data) applied cleanly so mark it up to date
            file_data.before_hash = utils.get_git_hash_for_file(file_data.before_file_path)
            file_data.after_hash = utils.get_git_hash_for_file(file_data.path)
            file_data.do_stash_current(None)
        elif os.path.exists(file_data.path) != os.path.exists(file_data.stashed_path):
            # probably an imported patch without hash data
            if not file_data.needs_refresh():
                # if it's up to date stash a copy
                file_data.do_stash_current(None)
        if file_data.path in overlaps.unrefreshed:
            RCTX.stdout.write(_('Unrefreshed changes incorporated.\n'))
        elif file_data.path in overlaps.uncommitted:
            RCTX.stdout.write(_('Uncommited changes incorporated.\n'))
        return biggest_ecode
    next_index = _DB.series_index_for_next()
    if next_index is None:
        top_patch = _DB.get_top_patch()
        if top_patch:
            RCTX.stderr.write(_('No pushable patches. "{0}" is on top.\n').format(top_patch.name))
        else:
            RCTX.stderr.write(_('No pushable patches.\n'))
        return CmdResult.ERROR
    next_patch = _DB.series[next_index]
    if force:
        overlaps = OverlapData()
    else:
        # We don't worry about overlaps for files that came from a copy or rename
        overlaps = _get_overlap_data(_DB, [fpth for fpth in next_patch.files if next_patch.files[fpth].came_from_path is None])
        if not absorb and len(overlaps):
            return overlaps.report_and_abort()
    os.mkdir(next_patch.cached_orig_dir_path)
    _DB.append_to_applied(next_patch)
    if len(next_patch.files) == 0:
        return CmdResult.OK
    drop_atws = options.get('push', 'drop_added_tws')
    copies = []
    renames = []
    creates = []
    # Do the caching of existing files first to obviate copy/rename problems
    for file_data in next_patch.files.values():
        file_data.do_cache_original(overlaps)
        if file_data.came_from_path:
            if file_data.came_as_rename:
                renames.append(file_data)
            else:
                copies.append(file_data)
        elif not os.path.exists(file_data.path):
            creates.append(file_data)
        file_data.set_before_mode()
        _DB.add_to_combined_patch(file_data)
    biggest_ecode = 0
    # Next do the files that are created by this patch as they may have been copied
    for file_data in creates:
        biggest_ecode = _apply_file_data_patch(file_data, biggest_ecode)
    # Now do the copying
    for file_data in copies:
        if not os.path.exists(file_data.before_file_path):
            RCTX.stderr.write(_('{0}: failed to copy {1}.\n').format(rel_subdir(file_data.path), rel_subdir(file_data.came_from_path)))
        else:
            try:
                shutil.copy2(file_data.before_file_path, file_data.path)
                # In case we're copying the cached version of the file.
                os.chmod(file_data.path, file_data.before_mode)
            except OSError as edata:
                RCTX.stderr.write(edata)
    # and renaming
    for file_data in renames:
        if not os.path.exists(next_patch.files[file_data.came_from_path].cached_orig_path):
            RCTX.stderr.write(_('{0}: failed to rename {1} (not found).\n').format(rel_subdir(file_data.path), rel_subdir(file_data.came_from_path)))
        else:
            try:
                shutil.copy2(file_data.before_file_path, file_data.path)
                os.chmod(file_data.path, file_data.before_mode)
            except OSError as edata:
                RCTX.stderr.write(edata)
    # and finally apply any patches
    for file_data in next_patch.files.values():
        if file_data in creates:
            continue
        biggest_ecode = _apply_file_data_patch(file_data, biggest_ecode)
    if biggest_ecode > 1:
        RCTX.stderr.write(_('A refresh is required after issues are resolved.\n'))
    elif biggest_ecode > 0:
        RCTX.stderr.write(_('A refresh is required.\n'))
    RCTX.stdout.write(_('Patch "{0}" is now on top.\n').format(next_patch.name))
    return CmdResult.ERROR if biggest_ecode > 1 else CmdResult.OK

def do_apply_next_patch(absorb=False, force=False):
    with open_db(mutable=True) as _DB:
        return _do_apply_next_patch(_DB, absorb=absorb, force=force)

def get_applied_patch_count():
    # NB: the exception handling is for the case we're not in a darning pgnd
    try:
        with open_db(mutable=False) as _DB:
            count = len(_DB.applied_patches)
    except OSError:
        count = 0
    return count

def all_applied_patches_refreshed():
    # NB: the exception handling is for the case we're not in a darning pgnd
    try:
        with open_db(mutable=False) as _DB:
            if len(_DB.applied_patches) == 0:
                return False
            for applied_patch in _DB.applied_patches:
                if applied_patch.needs_refresh():
                    return False
            return True
    except OSError:
        return False

def get_top_patch_for_file(filepath):
    with open_db(mutable=False) as _DB:
        for applied_patch in reversed(_DB.applied_patches):
            if filepath in applied_patch.files:
                return applied_patch.name
        return None

def is_blocked_by_guard(patchname):
    '''Is the named patch blocked from being applied by any guards?'''
    with open_db(mutable=False) as _DB:
        assert _DB.series_index_for_patchname(patchname) is not None
        return _DB.patch_fm_name(patchname).is_blocked_by_guard()

def is_pushable():
    '''Is there a pushable patch?'''
    with open_db(mutable=False) as _DB:
        return _DB.series_index_for_next() is not None

def is_patch_pushable(patchname):
    '''Is the named patch pushable?'''
    with open_db(mutable=False) as _DB:
        return _DB.patch_fm_name(patchname).is_pushable()

def _do_unapply_top_patch(_DB):
    '''Unapply the top applied patch'''
    top_patch = _get_top_patch(_DB)
    if not top_patch:
        return CmdResult.ERROR
    if top_patch.needs_refresh():
        RCTX.stderr.write(_('Top patch ("{0}") needs to be refreshed.\n').format(top_patch.name))
        return CmdResult.ERROR_SUGGEST_REFRESH
    drop_atws = options.get('pop', 'drop_added_tws')
    for file_data in top_patch.files.values():
        if os.path.exists(file_data.path):
            os.remove(file_data.path)
        if os.path.exists(file_data.cached_orig_path):
            os.chmod(file_data.cached_orig_path, file_data.orig_mode)
            shutil.move(file_data.cached_orig_path, file_data.path)
            os.utime(file_data.path, None)
        if file_data.diff:
            if drop_atws:
                atws_lines = file_data.diff.fix_trailing_whitespace()
                if atws_lines:
                    RCTX.stdout.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}: removed.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in atws_lines])))
            else:
                atws_lines = file_data.diff.report_trailing_whitespace()
                if atws_lines:
                    RCTX.stderr.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in atws_lines])))
    shutil.rmtree(top_patch.cached_orig_dir_path)
    _DB.pop_top_patch()
    new_top_patch= _DB.get_top_patch()
    if new_top_patch is None:
        RCTX.stdout.write(_('There are now no patches applied.\n'))
    else:
         RCTX.stdout.write(_('Patch "{0}" is now on top.\n').format(new_top_patch.name))
    return CmdResult.OK

def do_unapply_top_patch():
    with open_db(mutable=True) as _DB:
        return _do_unapply_top_patch(_DB)

def get_filepaths_in_patch(patchname, filepaths=None):
    '''
    Return the names of the files in the named patch.
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_patchname(patchname) if patchname else _DB.series_index_for_top()
        assert patch_index is not None
        return _DB.series[patch_index].get_filepaths(filepaths)

def get_filepaths_in_next_patch(filepaths=None):
    '''
    Return the names of the files in the next patch (to be applied).
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_next()
        assert patch_index is not None
        return _DB.series[patch_index].get_filepaths(filepaths)

def get_named_or_top_patch_name(arg):
    '''Return the name of the named or top patch if arg is None or None if arg is not a valid patchname'''
    with open_db(mutable=False) as _DB:
        patch = _get_named_or_top_patch(arg, _DB)
        return None if patch is None else patch.name

def _do_add_files_to_top_patch(_DB, filepaths, absorb=False, force=False):
    '''Add the named files to the named patch'''
    assert not (absorb and force)
    top_patch = _get_top_patch(_DB)
    if top_patch is None:
        return CmdResult.ERROR
    prepend_subdir(filepaths)
    if not force:
        overlaps = _get_overlap_data(_DB, filepaths, top_patch)
        if not absorb and len(overlaps) > 0:
            return overlaps.report_and_abort()
    else:
        overlaps = OverlapData()
    already_in_patch = set(top_patch.get_filepaths(filepaths))
    issued_warning = False
    for filepath in filepaths:
        if filepath in already_in_patch:
            RCTX.stderr.write(_('{0}: file already in patch "{1}". Ignored.\n').format(rel_subdir(filepath), top_patch.name))
            issued_warning = True
            continue
        elif os.path.isdir(filepath):
            RCTX.stderr.write(_('{0}: is a directory. Ignored.\n').format(rel_subdir(filepath)))
            issued_warning = True
            continue
        already_in_patch.add(filepath)
        rfilepath = rel_subdir(filepath)
        top_patch.add_file(FileData(filepath, top_patch, overlaps=overlaps))
        RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(rfilepath, top_patch.name))
        if filepath in overlaps.uncommitted:
            RCTX.stderr.write(_('{0}: Uncommited SCM changes have been incorporated in patch "{1}".\n').format(rfilepath, top_patch.name))
        elif filepath in overlaps.unrefreshed:
            RCTX.stderr.write(_('{0}: Unrefeshed changes in patch "{2}" incorporated in patch "{1}".\n').format(rfilepath, top_patch.name, overlaps.unrefreshed[filepath].name))
    return CmdResult.WARNING if issued_warning else CmdResult.OK

def do_add_files_to_top_patch(filepaths, absorb=False, force=False):
    with open_db(mutable=True) as _DB:
        return _do_add_files_to_top_patch(_DB, filepaths, absorb=absorb, force=force)

def do_delete_files_in_top_patch(filepaths):
    with open_db(mutable=True) as _DB:
        top_patch = _get_top_patch(_DB)
        if top_patch is None:
            return CmdResult.ERROR
        nonexists = 0
        ioerrors = 0
        for filepath in prepend_subdir(filepaths):
            if not os.path.exists(filepath):
                RCTX.stderr.write(_('{0}: file does not exist. Ignored.\n').format(rel_subdir(filepath)))
                nonexists += 1
                continue
            if filepath not in top_patch.files:
                top_patch.add_file(FileData(filepath, top_patch))
            try:
                os.remove(filepath)
            except OSError as edata:
                RCTX.stderr.write(edata)
                ioerrors += 1
                continue
            RCTX.stdout.write(_('{0}: file deleted within patch "{1}".\n').format(rel_subdir(filepath), top_patch.name))
        return CmdResult.OK if (ioerrors == 0 and len(filepaths) > nonexists) else CmdResult.ERROR

def do_copy_file_to_top_patch(filepath, as_filepath, overwrite=False):
    with open_db(mutable=True) as _DB:
        top_patch = _get_top_patch(_DB)
        if top_patch is None:
            return CmdResult.ERROR
        filepath = rel_basedir(filepath)
        as_filepath = rel_basedir(as_filepath)
        if filepath == as_filepath:
            return CmdResult.OK
        if not os.path.exists(filepath):
            RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
            return CmdResult.ERROR
        if not overwrite and as_filepath in top_patch.files:
            RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(as_filepath)))
            return CmdResult.ERROR | CmdResult.SUGGEST_RENAME
        needs_refresh = False
        record_copy = True
        came_from_path = filepath
        if filepath in top_patch.files:
            if top_patch.files[filepath].came_from_path:
                # this file was a copy or rename so refer to the original
                came_from_path = top_patch.files[filepath].came_from_path
            else:
                # if this file was created by the patch we don't record the copy
                record_copy = os.path.exists(top_patch.files[filepath].cached_orig_path)
        if as_filepath in top_patch.files:
            needs_refresh = True
        elif record_copy:
            top_patch.add_file(FileData(as_filepath, top_patch, came_from_path=came_from_path))
        else:
            top_patch.add_file(FileData(as_filepath, top_patch))
        try:
            shutil.copy2(filepath, as_filepath)
        except OSError as edata:
            RCTX.stderr.write(edata)
            return CmdResult.ERROR
        if needs_refresh:
            top_patch.files[as_filepath].reset_came_from(came_from_path if record_copy else None, False)
        RCTX.stdout.write(_('{0}: file copied to "{1}" in patch "{2}".\n').format(rel_subdir(filepath), rel_subdir(as_filepath), top_patch.name))
        return CmdResult.OK

def do_rename_file_in_top_patch(filepath, new_filepath, force=False, overwrite=False):
    with open_db(mutable=True) as _DB:
        def _delete_original():
            if os.path.exists(top_patch.files[filepath].stashed_path):
                os.remove(top_patch.files[filepath].stashed_path)
            top_patch.drop_file(filepath)
        top_patch = _get_top_patch(_DB)
        if top_patch is None:
            return CmdResult.ERROR
        filepath = rel_basedir(filepath)
        new_filepath = rel_basedir(new_filepath)
        if filepath == new_filepath:
            return CmdResult.OK
        if not os.path.exists(filepath):
            RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
            return CmdResult.ERROR
        if not overwrite:
            if new_filepath in top_patch.files:
                RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(new_filepath)))
                return CmdResult.ERROR | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
            elif os.path.exists(new_filepath):
                RCTX.stderr.write(_('{0}: file already exists.\n').format(rel_subdir(new_filepath)))
                return CmdResult.ERROR | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
        needs_refresh = False
        as_rename = True
        came_from_path = filepath
        is_boomerang = False
        if not filepath in top_patch.files:
            result = _do_add_files_to_top_patch(_DB, [rel_subdir(filepath)], absorb=False, force=force)
            result &= ~CmdResult.SUGGEST_ABSORB
            if result != CmdResult.OK:
                return result
        elif top_patch.files[filepath].came_from_path:
            if top_patch.files[filepath].came_from_path == new_filepath:
                came_from_path = None
                as_rename = False
                is_boomerang = new_filepath in top_patch.files and top_patch.files[new_filepath].came_as_rename
            else:
                came_from_path = top_patch.files[filepath].came_from_path
                as_rename = top_patch.files[filepath].came_as_rename
            if as_rename:
                top_patch.files[came_from_path].renamed_to = new_filepath
            if not os.path.exists(top_patch.files[filepath].cached_orig_path):
                _delete_original()
        elif not os.path.exists(top_patch.files[filepath].cached_orig_path):
            as_rename = False
            came_from_path = None
            _delete_original()
        if new_filepath in top_patch.files:
            needs_refresh = True
        else:
            top_patch.add_file(FileData(new_filepath, top_patch, came_from_path=came_from_path, as_rename=as_rename))
        try:
            os.rename(filepath, new_filepath)
        except OSError as edata:
            RCTX.stderr.write(edata)
            return CmdResult.ERROR
        if came_from_path and as_rename:
            top_patch.files[came_from_path].reset_renamed_to(new_filepath)
        if needs_refresh:
            if is_boomerang:
                top_patch.files[new_filepath].renamed_to = None
            top_patch.files[new_filepath].reset_came_from(came_from_path, as_rename)
        RCTX.stdout.write(_('{0}: file renamed to "{1}" in patch "{2}".\n').format(rel_subdir(filepath), rel_subdir(new_filepath), top_patch.name))
        return CmdResult.OK

def do_drop_files_fm_patch(patchname, filepaths):
    '''Drop the named file from the named patch'''
    with open_db(mutable=True) as _DB:
        patch = _get_named_or_top_patch(patchname, _DB)
        if patch is None:
            return CmdResult.ERROR
        elif patch.is_applied() and _DB.get_top_patch() != patch:
            RCTX.stderr.write('Patch "{0}" is a NON-top applied patch. Aborted.'.format(patch.name))
            return CmdResult.ERROR
        prepend_subdir(filepaths)
        issued_warning = False
        for filepath in filepaths:
            if filepath in patch.files:
                patch.do_drop_file(filepath)
                RCTX.stdout.write(_('{0}: file dropped from patch "{1}".\n').format(rel_subdir(filepath), patch.name))
            elif os.path.isdir(filepath):
                RCTX.stderr.write(_('{0}: is a directory: ignored.\n').format(rel_subdir(filepath)))
                issued_warning = True
            else:
                RCTX.stderr.write(_('{0}: file not in patch "{1}": ignored.\n').format(rel_subdir(filepath), patch.name))
                issued_warning = True
        return CmdResult.WARNING if issued_warning else CmdResult.OK

def do_duplicate_patch(patchname, as_patchname, newdescription):
    '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
    with open_db(mutable=True) as _DB:
        patch = _get_patch(patchname, _DB)
        if patch is None:
            return CmdResult.ERROR
        if patch.needs_refresh():
            RCTX.stderr.write(_('{0}: patch needs refresh.\n').format(patch.name))
            RCTX.stderr.write(_('Aborted.\n'))
            return CmdResult.ERROR_SUGGEST_REFRESH
        if _DB.has_patch_with_name(as_patchname):
            RCTX.stderr.write(_('{0}: patch already in series.\n').format(as_patchname))
            RCTX.stderr.write(_('Aborted.\n'))
            return CmdResult.ERROR | CmdResult.SUGGEST_RENAME
        elif not utils.is_valid_dir_name(as_patchname):
            RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(as_patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        newpatch = patch.clone_as(as_patchname, _tidy_text(newdescription), _DB)
        _DB.insert_patch(newpatch)
        RCTX.stdout.write(_('{0}: patch duplicated as "{1}"\n').format(patch.name, as_patchname))
        return CmdResult.OK

def do_refresh_overlapped_files(file_list):
    '''Refresh any files in the list which are in an applied patch
    (within the topmost such patch).'''
    with open_db(mutable=True) as _DB:
        assert len(_DB.applied_patches) > 0
        file_set = set(file_list)
        eflags = 0
        for applied_patch in reversed(_DB.applied_patches):
            for file_data in applied_patch.files.values():
                if file_data.path in file_set:
                    eflags |= file_data.do_refresh(quiet=False)
                    file_set.remove(file_data.path)
                    if len(file_set) == 0:
                        break
            if len(file_set) == 0:
                break
        return eflags

def do_refresh_patch(patchname=None):
    '''Refresh the named (or top applied) patch'''
    with open_db(mutable=True) as _DB:
        patch = _get_named_or_top_patch(patchname, _DB)
        if patch is None:
            return CmdResult.ERROR
        if not patch.is_applied():
            RCTX.stderr.write(_('Patch "{0}" is not applied\n').format(patchname))
            return CmdResult.ERROR
        eflags = 0
        for file_data in patch.files.values():
            eflags |= file_data.do_refresh(quiet=False)
        if eflags > 0:
            RCTX.stderr.write(_('Patch "{0}" requires another refresh after issues are resolved.\n').format(patch.name))
        else:
            RCTX.stdout.write(_('Patch "{0}" refreshed.\n').format(patch.name))
        return eflags

def _do_remove_patch(_DB, patchname):
    '''Remove the named patch from the series'''
    # assert is_writeable()
    assert patchname
    patch = _get_patch(patchname, _DB)
    if patch is None:
        return CmdResult.ERROR
    if patch.is_applied():
        RCTX.stderr.write(_('{0}: patch is applied and cannot be removed.\n').format(patchname))
        return CmdResult.ERROR
    if options.get('remove', 'keep_patch_backup'):
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    shutil.rmtree(patch.stash_dir_path)
    RCTX.stdout.write(_('Patch "{0}" removed (but available for restoration).\n').format(patchname))
    return CmdResult.OK

def do_remove_patch(patchname):
    '''Remove the named patch from the series'''
    with open_db(mutable=True) as _DB:
        return _do_remove_patch(_DB, patchname)

def do_restore_patch(patchname, as_patchname):
    '''Restore the named patch from back up with the specified name'''
    with open_db(mutable=True) as _DB:
        if not patchname in _DB.kept_patches:
            RCTX.stderr.write(_('{0}: is NOT available for restoration\n').format(patchname))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        if _DB.has_patch_with_name(as_patchname):
            RCTX.stderr.write(_('{0}: Already exists in database\n').format(as_patchname))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        elif not utils.is_valid_dir_name(as_patchname):
            RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(as_patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
            return CmdResult.ERROR|CmdResult.SUGGEST_RENAME
        patch = _DB.kept_patches[patchname]
        if as_patchname:
            patch.set_name(as_patchname)
        _DB.insert_patch(patch)
        del _DB.kept_patches[patchname]
        return CmdResult.OK

def _tidy_text(text):
    '''Return the given text with any trailing white space removed.
    Also ensure there is a new line at the end of the lastline.'''
    tidy_text = ''
    for line in text.splitlines():
        tidy_text += re.sub('[ \t]+$', '', line) + '\n'
    return tidy_text

def do_set_patch_description(patchname, text):
    with open_db(mutable=True) as _DB:
        patch = _get_named_or_top_patch(patchname, _DB)
        if not patch:
            return CmdResult.ERROR
        old_description = patch.description
        if text:
            text = _tidy_text(text)
        patch.description = text if text is not None else ''
        if old_description != patch.description:
            change_lines = difflib.ndiff(old_description.splitlines(True), patch.description.splitlines(True))
            RCTX.stdout.write(''.join(change_lines))
        return CmdResult.OK

def get_patch_description(patchname):
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_patchname(patchname)
        assert patch_index is not None
        return _DB.series[patch_index].description

def do_set_series_description(text):
    with open_db(mutable=True) as _DB:
        old_description = _DB.description
        if text:
            text = _tidy_text(text)
        _DB.description = text if text is not None else ''
        if old_description != _DB.description:
            change_lines = difflib.ndiff(old_description.splitlines(True), _DB.description.splitlines(True))
            RCTX.stdout.write(''.join(change_lines))
        return CmdResult.OK

def get_series_description():
    with open_db(mutable=False) as _DB:
        return _DB.description

def get_patch_table_data():
    with open_db(mutable=False) as _DB:
        return [patch.get_table_row() for patch in _DB.series]

def get_selected_guards():
    with open_db(mutable=False) as _DB:
        return _DB.selected_guards

def get_patch_guards(patchname):
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_patchname(patchname)
        assert patch_index is not None
        patch_data = _DB.series[patch_index]
        return PatchData.Guards(positive=patch_data.pos_guards, negative=patch_data.neg_guards)

def _do_set_patch_guards(_DB, patchname, guards):
    patch = _get_named_or_top_patch(patchname, _DB)
    if not patch:
        return CmdResult.ERROR
    patch.pos_guards = set(guards.positive)
    patch.neg_guards = set(guards.negative)
    RCTX.stdout.write(_('{0}: patch positive guards = {{{1}}}\n').format(patchname, ', '.join(sorted(patch.pos_guards))))
    RCTX.stdout.write(_('{0}: patch negative guards = {{{1}}}\n').format(patchname, ', '.join(sorted(patch.neg_guards))))
    return CmdResult.OK

def do_set_patch_guards(patchname, guards):
    with open_db(mutable=True) as _DB:
        return _do_set_patch_guards(_DB, patchname, guards)

def do_set_patch_guards_fm_str(patchname, guards_str):
    with open_db(mutable=True) as _DB:
        guards_list = guards_str.split()
        pos_guards = [grd[1:] for grd in guards_list if grd.startswith('+')]
        neg_guards = [grd[1:] for grd in guards_list if grd.startswith('-')]
        if len(guards_list) != (len(pos_guards) + len(neg_guards)):
            RCTX.stderr.write(_('Guards must start with "+" or "-" and contain no whitespace.\n'))
            RCTX.stderr.write( _('Aborted.\n'))
            return CmdResult.ERROR | CmdResult.SUGGEST_EDIT
        guards = PatchData.Guards(positive=pos_guards, negative=neg_guards)
        return _do_set_patch_guards(_DB, patchname, guards)

def do_select_guards(guards):
    with open_db(mutable=True) as _DB:
        bad_guard_count = 0
        for guard in guards:
            if guard.startswith('+') or guard.startswith('-'):
                RCTX.stderr.write(_('{0}: guard names may NOT begin with "+" or "-".\n').format(guard))
                bad_guard_count += 1
        if bad_guard_count > 0:
            RCTX.stderr.write(_('Aborted.\n'))
            return CmdResult.ERROR|CmdResult.SUGGEST_EDIT
        _DB.selected_guards = set(guards)
        RCTX.stdout.write(_('{{{0}}}: is now the set of selected guards.\n').format(', '.join(sorted(_DB.selected_guards))))
        return CmdResult.OK

def get_extdiff_files_for(filepath, patchname):
    with open_db(mutable=False) as _DB:
        assert _DB.is_named_patch_applied(patchname)
        patch =  _DB.series[_DB.series_index_for_patchname(patchname)]
        assert filepath in patch.files
        assert patch.get_overlapping_patch_for_path(filepath) is None
        before = patch.files[filepath].before_file_path
        return _O_IP_PAIR(original_version=before if os.path.exists(before) else "/dev/null", patched_version=filepath if os.path.exists(filepath) else "/dev/null")

def get_reconciliation_paths(filepath):
    with open_db(mutable=False) as _DB:
        top_patch = _get_top_patch(_DB)
        if not top_patch:
            return None
        assert filepath in top_patch.files
        return top_patch.files[filepath].get_reconciliation_paths()

class TextDiffPlus(patchlib.DiffPlus):
    def __init__(self, file_data, with_timestamps=False):
        diff_plus = file_data.get_diff_plus(as_refreshed=True, with_timestamps=with_timestamps)
        patchlib.DiffPlus.__init__(self, preambles=diff_plus.preambles, diff=diff_plus.diff)
        self.validity = file_data.get_validity()

class TextPatch(patchlib.Patch):
    def __init__(self, patch, with_timestamps=False, with_stats=True):
        patchlib.Patch.__init__(self, num_strip_levels=1)
        self.source_name = patch.name
        self.state = PatchState.APPLIED_REFRESHED if patch.is_applied() else PatchState.NOT_APPLIED
        self.set_description(patch.description)
        for filepath in sorted(patch.files):
            if patch.files[filepath].diff is None and not patch.files[filepath].has_actionable_preamble():
                continue
            edp = TextDiffPlus(patch.files[filepath], with_timestamps=with_timestamps)
            if edp.diff is None and (patch.files[filepath].renamed_to and not patch.files[filepath].came_from_path):
                continue
            self.diff_pluses.append(edp)
            if self.state == PatchState.NOT_APPLIED:
                continue
            if self.state == PatchState.APPLIED_REFRESHED and edp.validity != FileData.Validity.REFRESHED:
                self.state = PatchState.APPLIED_NEEDS_REFRESH if edp.validity == FileData.Validity.NEEDS_REFRESH else PatchState.APPLIED_UNREFRESHABLE
            elif self.state == PatchState.APPLIED_NEEDS_REFRESH and edp.validity == FileData.Validity.UNREFRESHABLE:
                self.state = PatchState.APPLIED_UNREFRESHABLE
        if with_stats:
            self.set_header_diffstat(strip_level=self.num_strip_levels)

def get_textpatch(patchname, with_timestamps=False):
    with open_db(mutable=False) as _DB:
        patch_index = _DB.series_index_for_patchname(patchname)
        assert patch_index is not None
        patch = _DB.series[patch_index]
        return TextPatch(patch, with_timestamps=with_timestamps)

def do_export_patch_as(patchname, export_filename, force=False, overwrite=False, with_timestamps=False):
    with open_db(mutable=True) as _DB:
        patch = _get_named_or_top_patch(patchname, _DB)
        if not patch:
            return CmdResult.ERROR
        textpatch = TextPatch(patch, with_timestamps=with_timestamps)
        if not force:
            if textpatch.state == PatchState.APPLIED_NEEDS_REFRESH:
                RCTX.stderr.write(_('Patch needs to be refreshed.\n'))
                return CmdResult.ERROR_SUGGEST_FORCE_OR_REFRESH
            elif textpatch.state == PatchState.APPLIED_UNREFRESHABLE:
                RCTX.stderr.write(_('Patch needs to be refreshed but has problems which prevent refresh.\n'))
                return CmdResult.ERROR_SUGGEST_FORCE
        if not export_filename:
            export_filename = utils.convert_patchname_to_filename(patch.name)
        if not overwrite and os.path.exists(export_filename):
            RCTX.stderr.write(_('{0}: file already exists.\n').format(export_filename))
            return CmdResult.ERROR | CmdResult.SUGGEST_RENAME
        try:
            open(export_filename, 'wb').write(str(textpatch))
        except IOError as edata:
            RCTX.stderr.write(str(edata) + '\n')
            return CmdResult.ERROR
        return CmdResult.OK

def do_scm_absorb_applied_patches(force=False, with_timestamps=False):
    with open_db(mutable=True) as _DB:
        if not scm_ifce.get_ifce().in_valid_pgnd:
            RCTX.stderr.write(_('Sources not under control of known SCM\n'))
            return CmdResult.ERROR
        if not _DB.applied_patches:
            RCTX.stderr.write(_('There are no patches applied.\n'))
            return CmdResult.ERROR
        is_ready, msg = scm_ifce.get_ifce().is_ready_for_import()
        if not is_ready:
            RCTX.stderr.write(_(msg))
            return CmdResult.ERROR
        problem_count = 0
        for applied_patch in _DB.applied_patches:
            if applied_patch.needs_refresh():
                problem_count += 1
                RCTX.stderr.write('{0}: requires refreshing\n'.format(applied_patch.name))
            if not applied_patch.description:
                problem_count += 1
                RCTX.stderr.write('{0}: has no description\n'.format(applied_patch.name))
        if problem_count > 0:
            return CmdResult.ERROR
        tempdir = tempfile.mkdtemp()
        patch_file_names = list()
        applied_patch_names = list()
        drop_atws = options.get('absorb', 'drop_added_tws')
        has_atws = False
        empty_patch_count = 0
        for applied_patch in _DB.applied_patches:
            fhandle, patch_file_name = tempfile.mkstemp(dir=tempdir)
            text_patch = TextPatch(applied_patch, with_timestamps=with_timestamps, with_stats=False)
            if drop_atws:
                atws_reports = text_patch.fix_trailing_whitespace()
                for file_path, atws_lines in atws_reports:
                    RCTX.stdout.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}: removed.\n').format(applied_patch.name, rel_subdir(file_path), ', '.join([str(line) for line in atws_lines])))
            else:
                atws_reports = text_patch.report_trailing_whitespace()
                for file_path, atws_lines in atws_reports:
                    RCTX.stderr.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}.\n').format(applied_patch.name, rel_subdir(file_path), ', '.join([str(line) for line in atws_lines])))
                has_atws = has_atws or len(atws_reports) > 0
            os.write(fhandle, str(text_patch))
            os.close(fhandle)
            if len(text_patch.diff_pluses) == 0:
                RCTX.stderr.write(_('"{0}": has no absorbable content.\n').format(applied_patch.name))
                empty_patch_count += 1
            patch_file_names.append(patch_file_name)
            applied_patch_names.append(applied_patch.name)
        if not force and has_atws:
            shutil.rmtree(tempdir)
            return CmdResult.ERROR
        if empty_patch_count > 0:
            shutil.rmtree(tempdir)
            return CmdResult.ERROR
        while len(_DB.applied_patches) > 0:
            if _do_unapply_top_patch(_DB) != CmdResult.OK:
                return CmdResult.ERROR
        ret_code = CmdResult.OK
        count = 0
        for patch_file_name in patch_file_names:
            result = scm_ifce.get_ifce().do_import_patch(patch_file_name)
            RCTX.stdout.write(result.stdout)
            RCTX.stderr.write(result.stderr)
            if result.ecode != 0:
                RCTX.stderr.write('Aborting')
                ret_code = CmdResult.ERROR
                break
            count += 1
        for patch_name in applied_patch_names[0:count]:
            ret_code = _do_remove_patch(_DB, patch_name)
            if ret_code != CmdResult.OK:
                break
        while count < len(applied_patch_names):
            _do_apply_next_patch(_DB)
            count += 1
        shutil.rmtree(tempdir)
        return ret_code

class CombinedTextPatch(patchlib.Patch):
    def __init__(self, with_timestamps=False):
        patchlib.Patch.__init__(self, _DB, num_strip_levels=1)
        if _DB.combined_patch is False:
            # Still using old DB
            description = _DB.description
            file_first_patch = {}
            for applied_patch in _DB.applied_patches:
                description += applied_patch.description
                for filepath in applied_patch.files:
                    if filepath not in file_first_patch:
                        file_first_patch[filepath] = applied_patch
            self.set_description(description)
            for filepath in sorted(file_first_patch):
                file_data = file_first_patch[filepath].files[filepath]
                self.diff_pluses.append(file_data.get_diff_plus(old_combined=True, with_timestamps=with_timestamps))
            self.set_header_diffstat(strip_level=self.num_strip_levels)
        elif _DB.combined_patch is not None:
            self.set_description(''.join([obj.description for obj in [_DB] + _DB.applied_patches]))
            for filepath in sorted(_DB.combined_patch.files):
                file_data = _DB.combined_patch.files[filepath]
                if file_data.was_ephemeral():
                    continue
                self.diff_pluses.append(file_data.get_diff_plus(with_timestamps=with_timestamps))
            self.set_header_diffstat(strip_level=self.num_strip_levels)

def get_combined_textpatch(with_timestamps=False):
    with open_db(mutable=False) as _DB:
        if _DB.series_index_for_top() is None:
            return None
        return CombinedTextPatch(_DB, with_timestamps=with_timestamps)

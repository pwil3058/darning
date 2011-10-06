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

from darning import rctx as RCTX
from darning import i18n
from darning import scm_ifce
from darning import runext
from darning import cmd_result
from darning import utils
from darning import patchlib
from darning import fsdb
from darning import options

options.define('pop', 'drop_added_tws', options.Defn(options.str_to_bool, True, _('Remove added trailing white space (TWS) from patch after pop')))
options.define('push', 'drop_added_tws', options.Defn(options.str_to_bool, True, _('Remove added trailing white space (TWS) from patch before push')))
options.define('remove', 'keep_patch_backup', options.Defn(options.str_to_bool, True, _('Keep back up copies of removed patches.  Facilitates restoration at a later time.')))

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

class BinaryDiff(patchlib.Diff):
    def __init__(self, file_data):
        Diff.__init__(self, 'binary', [], file_data, hunks=None)
        if os.path.exists(file_data.after):
            self.contents = open(file_data.after).read()
        else:
            self.contents = None
    def __str__(self):
        return _('Binary files "{0}" and "{1}" differ.\n').format(self.file_data.before, self.file_data.after)
    def fix_trailing_whitespace(self):
        return []
    def report_trailing_whitespace(self):
        return []
    def get_diffstat_stats(self):
        return DiffStat.Stats()

def _do_apply_diff_to_file(filepath, diff, delete_empty=False):
    patch_cmd_hdr = ['patch', '--merge', '--force', '-p1', '--batch', '--quiet']
    patch_cmd = patch_cmd_hdr + (['--remove-empty-files', filepath] if delete_empty else [filepath])
    return runext.run_cmd(patch_cmd, str(diff))

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
        return self.NEW_FIELDS[attr]

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
        return cmd_result.ERROR_SUGGEST_FORCE_ABSORB_OR_REFRESH if len(self.unrefreshed) > 0 else cmd_result.ERROR_SUGGEST_FORCE_OR_ABSORB

class FileData(PickeExtensibleObject):
    '''Change data for a single file'''
    class Presence(object):
        ADDED = patchlib.FilePathPlus.ADDED
        REMOVED = patchlib.FilePathPlus.DELETED
        EXTANT = patchlib.FilePathPlus.EXTANT
    class Validity(object):
        REFRESHED, NEEDS_REFRESH, UNREFRESHABLE = range(3)
    Status = collections.namedtuple('Status', ['presence', 'validity'])
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
                self.before_sha1 = utils.get_sha1_for_file(came_from_data.cached_orig_path)
            else:
                # self.came_from_path must exist so no need for "try"
                self.before_mode = utils.get_mode_for_file(self.came_from_path)
                self.before_sha1 = utils.get_sha1_for_file(self.came_from_path)
        else:
            self.orig_mode = utils.get_mode_for_file(self.path)
            self.before_mode = self.orig_mode
            self.before_sha1 = utils.get_sha1_for_file(self.path)
        self.after_sha1 = self.before_sha1
        self.after_mode = self.before_mode
        if self.patch.is_applied():
            self.do_cache_original(overlaps)
            if came_from_path is None:
                # The file won't exist yet so "needs refresh" will be True
                self.do_stash_current(None)
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
    def reset_reference_paths(self):
        # have this as a function to make patch renaming easier
        self.cached_orig_path = self.patch.generate_cached_original_path(self.path)
        self.stashed_path = os.path.join(self.patch.stash_dir_path, self.path)
        self.set_before_file_path()
    def reset_renamed_to(self, renamed_to):
        self.renamed_to = renamed_to
        self.reset_reference_paths()
        self.do_refresh()
    def reset_came_from(self, came_from_path, came_as_rename):
        self.came_from_path = came_from_path
        self.came_as_rename = came_as_rename
        self.reset_reference_paths()
        self.do_refresh()
    def do_stash_current(self, overlapping_patch):
        '''Stash the current version of this file for later reference'''
        assert is_writable()
        assert self.patch.is_applied()
        assert self.needs_refresh() is False
        self.do_delete_stash()
        source = self.path if overlapping_patch is None else overlapping_patch.files[self.path].cached_orig_path
        if os.path.exists(source):
            utils.ensure_file_dir_exists(self.stashed_path)
            shutil.copy2(source, self.stashed_path)
            utils.do_turn_off_write_for_file(self.stashed_path)
    def do_delete_stash(self):
        assert is_writable()
        if os.path.exists(self.stashed_path):
            os.remove(self.stashed_path)
    def _copy_refreshed_version_to(self, target_name):
        if not self.needs_refresh():
            if os.path.exists(self.path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(self.path, target_name)
            return
        if self.binary is not False:
            if os.path.exists(self.cached_orig_path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(self.cached_orig_path, target_name)
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
        assert is_writable()
        assert self.patch.is_applied()
        assert self.get_overlapping_patch() is None
        olurpatch = overlaps.unrefreshed.get(self.path, None)
        if olurpatch:
            olurpatch.files[self.path]._copy_refreshed_version_to(self.cached_orig_path)
        elif self.path in overlaps.uncommitted:
            scm_ifce.copy_clean_version_to(self.path, self.cached_orig_path)
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
        assert is_readable()
        assert self.patch.is_top_applied_patch()
        # make it hard for the user to (accidentally) create these files if they don't exist
        before = self.before_file_path if os.path.exists(self.before_file_path) else '/dev/null'
        stashed = self.stashed_path if os.path.exists(self.stashed_path) else '/dev/null'
        # The user has to be able to cope with the main file not existing (meld can)
        return _O_IP_S_TRIPLET(before, self.path, stashed)
    @property
    def binary(self):
        return isinstance(self.diff, BinaryDiff)
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
            elif self.after_sha1 != utils.get_sha1_for_file(olfd.cached_orig_path):
                return True
        else:
            if self.after_mode != utils.get_mode_for_file(self.path):
                return True
            elif self.after_sha1 != utils.get_sha1_for_file(self.path):
                return True
            elif self.came_from_path and not self.came_as_rename:
                return self.before_sha1 != utils.get_sha1_for_file(self.before_file_path)
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
        assert is_readable()
        assert self.patch.is_applied()
        after = False
        for apatch in _APPLIED_PATCHES:
            if after:
                if self.path in apatch.files:
                    return apatch
            else:
                after = apatch.name == self.patch.name
        return None
    @property
    def related_file(self):
        if self.came_from_path:
            if self.came_as_rename:
                return fsdb.RFD(self.came_from_path, fsdb.Relation.RENAMED_FROM)
            else:
                return fsdb.RFD(self.came_from_path, fsdb.Relation.COPIED_FROM)
        elif self.renamed_to:
            return fsdb.RFD(self.renamed_to, fsdb.Relation.RENAMED_TO)
        return None
    def generate_diff_preamble(self, overlapping_patch, combined=False):
        assert is_readable()
        if self.patch.is_applied():
            if overlapping_patch is not None:
                after_mode = overlapping_patch.files[self.path].before_mode
            elif os.path.exists(self.path):
                after_mode = utils.get_mode_for_file(self.path)
            else:
                after_mode = self.before_mode if self.renamed_to else None
        else:
            after_mode = self.after_mode
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
        if not combined and self.came_from_path:
            if self.came_as_rename:
                lines.append('rename from {0}\n'.format(self.came_from_path))
                lines.append('rename to {0}\n'.format(self.path))
            else:
                lines.append('copy from {0}\n'.format(self.came_from_path))
                lines.append('copy to {0}\n'.format(self.path))
        return patchlib.Preamble.parse_lines(lines)
    def generate_diff(self, overlapping_patch, combined=False, with_timestamps=True):
        assert is_readable()
        assert self.patch.is_applied()
        assert overlapping_patch is None or not combined
        to_file = self.path if overlapping_patch is None else overlapping_patch.files[self.path].cached_orig_path
        fm_file = self.cached_orig_path if combined else self.before_file_path
        fm_exists = os.path.exists(fm_file)
        if os.path.exists(to_file):
            to_name_label = os.path.join('b' if fm_exists else 'a', self.path)
            to_time_stamp = _pts_for_path(to_file) if with_timestamps else None
            with open(to_file) as fobj:
                to_contents = fobj.read()
        else:
            to_name_label = '/dev/null'
            to_time_stamp = _PTS_ZERO if with_timestamps else None
            to_contents = ''
        if fm_exists:
            fm_name_label = os.path.join('a', self.path)
            fm_time_stamp = _pts_for_path(fm_file) if with_timestamps else None
            with open(fm_file) as fobj:
                fm_contents = fobj.read()
        else:
            fm_name_label = '/dev/null'
            fm_time_stamp = _PTS_ZERO if with_timestamps else None
            fm_contents = ''
        if to_contents == fm_contents:
            return None
        if to_contents.find('\000') != -1 or fm_contents.find('\000') != -1:
            return BinaryDiff(patchlib._PAIR(fm_name_label, to_name_label))
        diffgen = difflib.unified_diff(fm_contents.splitlines(True), to_contents.splitlines(True),
            fromfile=fm_name_label, tofile=to_name_label, fromfiledate=fm_time_stamp, tofiledate=to_time_stamp)
        return patchlib.Diff.parse_lines(list(diffgen))
    def get_diff_plus(self, combined=False, as_refreshed=False, with_timestamps=True):
        assert is_readable()
        assert not (combined and as_refreshed)
        overlapping_patch = None if combined else self.get_overlapping_patch()
        preamble = self.generate_diff_preamble(overlapping_patch=overlapping_patch, combined=combined)
        if self.patch.is_applied() and not as_refreshed:
            diff = self.generate_diff(overlapping_patch=overlapping_patch, combined=combined, with_timestamps=with_timestamps)
        else:
            diff = copy.deepcopy(self.diff)
        diff_plus = patchlib.DiffPlus([preamble], diff)
        if not combined and self.renamed_to:
            diff_plus.trailing_junk.append(_('# Renamed to: {0}\n').format(self.renamed_to))
        return diff_plus
    def do_refresh(self, quiet=True, with_timestamps=True):
        '''Refresh the named file in this patch'''
        assert is_writable()
        assert self.patch.is_applied()
        overlapping_patch = self.get_overlapping_patch()
        if self._has_unresolved_merges(overlapping_patch):
            # ensure this file shows up as needing refresh
            self.after_sha1 = False
            dump_db()
            RCTX.stderr.write(_('"{0}": file has unresolved merge(s).\n').format(rel_subdir(self.path)))
            return cmd_result.ERROR
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
        self.before_sha1 = utils.get_sha1_for_file(self.before_file_path)
        self.after_sha1 = utils.get_sha1_for_file(self.path if overlapping_file_data is None else overlapping_file_data.cached_orig_path)
        self.do_stash_current(overlapping_patch)
        dump_db()
        return cmd_result.OK

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

class PatchState(object):
    UNAPPLIED = ' '
    APPLIED_REFRESHED = '+'
    APPLIED_NEEDS_REFRESH = '?'
    APPLIED_UNREFRESHABLE = '!'

class PatchTable(object):
    Row = collections.namedtuple('Row', ['name', 'state', 'pos_guards', 'neg_guards'])

class PatchData(PickeExtensibleObject):
    '''Store data for changes to a number of files as a single patch'''
    Guards = collections.namedtuple('Guards', ['positive', 'negative'])
    def __init__(self, name, description):
        self.files = dict()
        self.set_name(name, first=True)
        self.description = _tidy_text(description) if description is not None else ''
        self.pos_guards = set()
        self.neg_guards = set()
    def set_name(self, newname, first=False):
        if not first:
            old_cached_orig_dir_path = self.cached_orig_dir_path
            old_stash_dir_path = self.stash_dir_path
        self.name = newname
        self.cached_orig_dir_path = _cached_original_dir_path(self.name)
        self.stash_dir_path = _stash_dir_path(self.name)
        if not first and os.path.exists(old_cached_orig_dir_path):
            os.rename(old_cached_orig_dir_path, self.cached_orig_dir_path)
        if not first:
            assert os.path.exists(old_stash_dir_path)
            os.rename(old_stash_dir_path, self.stash_dir_path)
        else:
            os.mkdir(self.stash_dir_path)
        for file_data in self.files.values():
            file_data.reset_reference_paths()
    def generate_cached_original_path(self, filepath):
        '''Return the path of the cached original for the given file path'''
        return os.path.join(self.cached_orig_dir_path, filepath)
    def do_drop_file(self, filepath):
        '''Drop the named file from this patch'''
        assert is_writable()
        assert filepath in self.files
        renamed_from = self.files[filepath].came_from_path if self.files[filepath].came_as_rename else None
        self.files[filepath].do_delete_stash()
        if not self.is_applied():
            # not much to do here
            del self.files[filepath]
            dump_db()
            if renamed_from is not None:
                self.files[renamed_from].reset_renamed_to(None)
            return
        corig_f_path = self.files[filepath].cached_orig_path
        overlapped_by = self.files[filepath].get_overlapping_patch()
        if overlapped_by is None:
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists(corig_f_path):
                os.chmod(corig_f_path, self.files[filepath].orig_mode)
                shutil.move(corig_f_path, filepath)
        else:
            overlapping_corig_f_path = overlapped_by.files[filepath].cached_orig_path
            if os.path.exists(corig_f_path):
                shutil.move(corig_f_path, overlapping_corig_f_path)
                overlapped_by.files[filepath].before_mode = self.files[filepath].before_mode
            else:
                if os.path.exists(overlapping_corig_f_path):
                    os.remove(overlapping_corig_f_path)
                overlapped_by.files[filepath].before_mode = None
            # Make sure that the overlapping file gets refreshed
            overlapped_by.files[filepath].after_sha1 = False
        renamed_to = self.files[filepath].renamed_to
        renamed_from = self.files[filepath].came_from_path if self.files[filepath].came_as_rename else None
        del self.files[filepath]
        if renamed_to is not None and renamed_to in self.files:
            # Second check is necessary in the case where a renamed
            # file is dropped and the source is dropped as a result.
            self.files[renamed_to].reset_came_from(filepath, False)
        if renamed_from is not None and renamed_from in self.files:
            self.files[renamed_from].reset_renamed_to(None)
        for file_data in self.files.values():
            if file_data.came_from_path == filepath:
                assert file_data.came_as_rename == False
                file_data.before_file_path = filepath
        dump_db()
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
            table = [fsdb.Data(fde.path, FileData.Status(fde.get_presence(), fde.get_applied_validity()), fde.related_file) for fde in self.files.values()]
        else:
            table = [fsdb.Data(fde.path, FileData.Status(fde.get_presence(), None), fde.related_file) for fde in self.files.values()]
        return table
    def get_table_row(self):
        if not self.is_applied():
            state = PatchState.UNAPPLIED
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
        return self in _APPLIED_PATCHES
    def is_top_applied_patch(self):
        return False if not _APPLIED_PATCHES else (self == _APPLIED_PATCHES[-1])
    def is_blocked_by_guard(self):
        '''Is the this patch blocked from being applied by any guards?'''
        if (self.pos_guards & _DB.selected_guards) != self.pos_guards:
            return True
        if len(self.neg_guards & _DB.selected_guards) != 0:
            return True
        return False
    def is_overlapped(self):
        '''Are any files in this patch overlapped by applied patches?'''
        for file_data in self.files.values():
            if file_data.get_overlapping_patch() is not None:
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

class DataBase(PickeExtensibleObject):
    '''Storage for an ordered sequence/series of patches'''
    def __init__(self, description, host_scm=None):
        self.description = _tidy_text(description) if description else ''
        self.selected_guards = set()
        self.series = list()
        self.kept_patches = dict()
        self.host_scm = host_scm

_DB_DIR = '.darning.dbd'
_ORIGINALS_DIR = os.path.join(_DB_DIR, 'orig')
_STASH_DIR = os.path.join(_DB_DIR, 'stash')
_DB_FILE = os.path.join(_DB_DIR, 'database')
_DB_LOCK_FILE = os.path.join(_DB_DIR, 'lock')
_DB = None
_SUB_DIR = None
_APPLIED_PATCHES = None

def _cached_original_dir_path(patchname):
    '''Return the path of the cached originals' directory for the given patch name'''
    return os.path.join(_ORIGINALS_DIR, patchname)

def _stash_dir_path(patchname):
    '''Return the path of the cached originals' directory for the given patch name'''
    return os.path.join(_STASH_DIR, patchname)

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

def find_base_dir(remember_sub_dir=False):
    '''Find the nearest directory above that contains a database'''
    global _SUB_DIR
    dirpath = os.getcwd()
    subdir_parts = []
    while True:
        if os.path.isdir(os.path.join(dirpath, _DB_DIR)):
            _SUB_DIR = None if not subdir_parts else os.path.join(*subdir_parts)
            return dirpath
        else:
            dirpath, basename = os.path.split(dirpath)
            if not basename:
                break
            if remember_sub_dir:
                subdir_parts.insert(0, basename)
    return None

def exists():
    '''Does the current directory contain a patch database?'''
    return os.path.isfile(_DB_FILE)

def is_readable():
    '''Is the database open for reading?'''
    return exists() and _DB is not None

def is_my_lock():
    '''Am I the process holding the lock?'''
    try:
        lock_pid = open(_DB_LOCK_FILE).read()
    except IOError:
        lock_pid = False
    return lock_pid and lock_pid == str(os.getpid())

def is_writable():
    '''Is the databas modifiable?'''
    if not is_readable():
        return False
    return is_my_lock()

def _lock_db():
    '''Lock the database in the given (or current) directory'''
    try:
        lf_fd = os.open(_DB_LOCK_FILE, os.O_WRONLY|os.O_EXCL|os.O_CREAT, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    except OSError as edata:
        if edata.errno == errno.EEXIST:
            return False
        else:
            return Failure('%s: %s' % (_DB_LOCK_FILE, edata.strerror))
    if lf_fd == -1:
        return Failure(_('{0}: Unable to open').format(_DB_LOCK_FILE))
    os.write(lf_fd, str(os.getpid()))
    os.close(lf_fd)
    return True

def _unlock_db():
    '''Unock the database in the given (or current) directory'''
    assert is_my_lock()
    os.remove(_DB_LOCK_FILE)

def do_create_db(description):
    '''Create a patch database in the current directory?'''
    def rollback():
        '''Undo steps that were completed before failure occured'''
        for filnm in [_DB_FILE, _DB_LOCK_FILE ]:
            if os.path.exists(filnm):
                os.remove(filnm)
        for dirnm in [_ORIGINALS_DIR, _DB_DIR]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    root = find_base_dir(remember_sub_dir=False)
    if root is not None:
        RCTX.stderr.write(_('Inside existing playground: "{0}".\n').format(os.path.relpath(root)))
        return cmd_result.ERROR
    elif os.path.exists(_DB_DIR):
        if os.path.exists(_ORIGINALS_DIR) and os.path.exists(_DB_FILE):
            RCTX.stderr.write(_('Database already exists.\n'))
        else:
            RCTX.stderr.write(_('Database directory exists.\n'))
        return cmd_result.ERROR
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(_DB_DIR, dir_mode)
        os.mkdir(_ORIGINALS_DIR, dir_mode)
        os.mkdir(_STASH_DIR, dir_mode)
        lock_state = _lock_db()
        assert lock_state is True
        db_obj = DataBase(description, None)
        fobj = open(_DB_FILE, 'wb', stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
        try:
            cPickle.dump(db_obj, fobj)
        finally:
            fobj.close()
            _unlock_db()
    except OSError as edata:
        rollback()
        RCTX.stderr.write(edata.strerror)
        return cmd_result.ERROR
    except Exception:
        rollback()
        raise
    return cmd_result.OK

def release_db():
    '''Release access to the database'''
    assert is_readable()
    global _DB
    global _APPLIED_PATCHES
    writeable = is_writable()
    _DB = None
    _APPLIED_PATCHES = None
    if writeable:
        _unlock_db()

def load_db(lock=True):
    '''Load the database for access (read only unless lock is True)'''
    global _DB
    global _APPLIED_PATCHES
    assert exists()
    assert not is_readable()
    while lock:
        lock_state = _lock_db()
        if isinstance(lock_state, Failure):
            return lock_state
        elif lock_state is False:
            try:
                holder = open(_DB_LOCK_FILE).read()
            except OSError as edata:
                if edata.errno == errno.ENOENT:
                    continue
        break
    fobj = open(_DB_FILE, 'rb')
    try:
        _DB = cPickle.load(fobj)
    except Exception:
        # Just in case higher level code catches and handles
        _DB = None
        raise
    finally:
        fobj.close()
    if lock and lock_state is not True:
        return Failure(_('Database is read only. Lock held by: {0}').format(holder))
    _APPLIED_PATCHES = _generate_applied_patch_list()
    return True

def dump_db():
    '''Dump in memory database to file'''
    assert is_writable()
    fobj = open(_DB_FILE, 'wb')
    try:
        cPickle.dump(_DB, fobj)
    finally:
        fobj.close()

def get_series_index(patchname):
    '''Get the series index for the patch with the given name'''
    assert is_readable()
    index = 0
    for patch in _DB.series:
        if patch.name == patchname:
            return index
        index += 1
    return None

def get_series_index_for_top():
    '''Get the index in series of the top applied patch'''
    assert is_readable()
    applied_set = _get_applied_patch_names_set()
    if len(applied_set) == 0:
        return None
    index = 0
    for patch in _DB.series:
        if patch.name in applied_set:
            applied_set.remove(patch.name)
            if len(applied_set) == 0:
                return index
        index += 1
    return None

def get_series_index_for_next():
    '''Get the index of the next patch to be applied'''
    assert is_readable()
    top = get_series_index_for_top()
    index = 0 if top is None else top + 1
    while index < len(_DB.series):
        if _DB.series[index].is_blocked_by_guard():
            index += 1
            continue
        return index
    return None

def get_patch(patchname):
    '''Get the patch with the given name'''
    assert is_readable()
    patch_index = get_series_index(patchname)
    if patch_index is not None:
        return _DB.series[patch_index]
    else:
        return None

def get_patch_series_names():
    '''Get a list of patch names in series order (names only)'''
    assert is_readable()
    return [patch.name for patch in _DB.series]

def get_kept_patch_names():
    '''Get a list of names for patches that have been kept on removal'''
    assert is_readable()
    return [kept_patch_name for kept_patch_name in sorted(_DB.kept_patches)]

def _get_applied_patch_names_set():
    '''Get the set of applied patches' names'''
    def isdir(item):
        '''Is item a directory?'''
        return os.path.isdir(os.path.join(_ORIGINALS_DIR, item))
    return set([item for item in os.listdir(_ORIGINALS_DIR) if isdir(item)])

def _generate_applied_patch_list():
    '''Get an ordered list of applied patches'''
    assert is_readable()
    applied = list()
    applied_set = _get_applied_patch_names_set()
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

def get_applied_patch_name_list():
    '''Get an ordered list of applied patch names'''
    assert is_readable()
    return [patch.name for patch in _APPLIED_PATCHES]

def get_patch_series_index(patchname):
    '''Get the index in series for the patch with the given name'''
    assert is_readable()
    return get_series_index(patchname)

def get_patch_file_table(patchname):
    assert is_readable()
    if len(_DB.series) == 0:
        return []
    index = get_series_index(patchname)
    return _DB.series[index].get_files_table()

def get_combined_patch_file_table():
    '''Get a table of file data for all applied patches'''
    class _Data(object):
        __slots__ = ['presence', 'validity', 'related_file']
        def __init__(self, presence, validity, related_file=None):
            self.presence = presence
            self.validity = validity
            self.related_file = related_file
    assert is_readable()
    if len(_DB.series) == 0:
        return []
    file_map = {}
    for patch in _DB.series:
        if not patch.is_applied():
            continue
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
        table.append(fsdb.Data(filepath, FileData.Status(data.presence, data.validity), data.related_file))
    return table

def patch_is_in_series(patchname):
    '''Is there a patch with the given name in the series?'''
    return get_patch_series_index(patchname) is not None

def is_applied(patchname):
    '''Is the named patch currently applied?'''
    return get_patch(patchname).is_applied()

def is_top_applied_patch(patchname):
    '''Is the named patch the top applied patch?'''
    if not _APPLIED_PATCHES:
        return False
    return _APPLIED_PATCHES[-1].name == patchname

def patch_needs_refresh(patchname):
    '''Does the named patch need to be refreshed?'''
    assert is_readable()
    assert get_patch_series_index(patchname) is not None
    return get_patch(patchname).needs_refresh()

def _insert_patch(patch, after=None):
    '''Insert given patch into series after the top or nominated patch'''
    assert is_writable()
    assert get_series_index(patch.name) is None
    assert after is None or get_series_index(after) is not None
    if after is not None:
        assert not is_applied(after) or is_top_applied_patch(after)
        index = get_series_index(after) + 1
    else:
        top_index = get_series_index_for_top()
        index = top_index + 1 if top_index is not None else 0
    _DB.series.insert(index, patch)
    dump_db()

def do_create_new_patch(patchname, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    assert is_writable()
    if get_patch_series_index(patchname) is not None:
        RCTX.stderr.write(_('patch "{0}" already exists.\n').format(patchname))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    elif not utils.is_valid_dir_name(patchname):
        RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    patch = PatchData(patchname, description)
    _insert_patch(patch)
    dump_db()
    warn = top_patch_needs_refresh()
    if warn:
        old_top = get_top_patch_name()
    # Ignore result of apply as it cannot fail
    do_apply_next_patch()
    if warn:
        RCTX.stderr.write(_('Previous top patch ("{0}") needs refreshing.\n').format(old_top))
    return cmd_result.OK

def do_rename_patch(patchname, newname):
    '''Rename an existing patch.'''
    assert is_writable()
    if get_patch_series_index(newname) is not None:
        RCTX.stderr.write(_('patch "{0}" already exists\n').format(newname))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    elif not utils.is_valid_dir_name(newname):
        RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(newname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    patch = _get_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    patch.set_name(newname)
    RCTX.stdout.write(_('{0}: patch renamed as "{1}".\n').format(patchname, patch.name))
    dump_db()
    return cmd_result.OK

def do_import_patch(epatch, patchname, overwrite=False):
    '''Import an external patch with the given name (after the top patch)'''
    assert is_writable()
    if patch_is_in_series(patchname):
        if not overwrite:
            RCTX.stderr.write(_('patch "{0}" already exists\n').format(patchname))
            result = cmd_result.ERROR | cmd_result.SUGGEST_RENAME
            if not is_applied(patchname):
                result |= cmd_result.SUGGEST_FORCE
            return result
        elif is_applied(patchname):
            RCTX.stderr.write(_('patch "{0}" already exists and is applied. Cannot be overwritten.\n').format(patchname))
            return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
        else:
            result = do_remove_patch(patchname)
            if result != cmd_result.OK:
                return result
    elif not utils.is_valid_dir_name(patchname):
        RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    descr = utils.make_utf8_compliant(epatch.get_description())
    patch = PatchData(patchname, descr)
    renames = dict()
    for diff_plus in epatch.diff_pluses:
        filepath_plus = diff_plus.get_file_path_plus(epatch.num_strip_levels)
        filepath = filepath_plus.path
        came_from = None
        as_rename = False
        git_preamble = diff_plus.get_preamble_for_type('git')
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
                RCTX.stderr.write(_('git data for file "{0}" incompatible with strip level {1}.\n').format(filepath, epatch.num_strip_levels))
                return cmd_result.ERROR
        file_data = FileData(filepath, patch, came_from_path=came_from, as_rename=as_rename)
        file_data.diff = diff_plus.diff
        # let push know it may need to set this.
        file_data.after_mode = False if filepath_plus.status != patchlib.FilePathPlus.DELETED else None
        if git_preamble:
            for key in ['new mode', 'new file mode']:
                if key in git_preamble.extras:
                    file_data.after_mode = int(git_preamble.extras[key], 8)
                    break
        patch.files[file_data.path] = file_data
        RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(file_data.path, patchname))
    for old_path in renames:
        if old_path not in patch.files:
            patch.files[old_path] = FileData(old_path, patch)
            RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(old_path, patchname))
        patch.files[old_path].renamed_to = renames[old_path]
        patch.files[old_path].set_before_file_path()
    _insert_patch(patch)
    dump_db()
    top_patchname = get_top_patch_name()
    if top_patchname:
        RCTX.stdout.write(_('{0}: patch inserted after patch "{1}".\n').format(patchname, top_patchname))
    else:
        RCTX.stdout.write(_('{0}: patch inserted at start of series.\n').format(patchname))
    return cmd_result.OK

def do_fold_epatch(epatch, absorb=False, force=False):
    '''Fold an external patch into the top patch.'''
    assert is_writable()
    assert not (absorb and force)
    top_patch = _get_top_patch()
    if not top_patch:
        return cmd_result.ERROR
    def _apply_diff_plus(diff_plus):
        filepath = diff_plus.get_file_path(epatch.num_strip_levels)
        dump_db()
        RCTX.stdout.write(_('Patching file "{0}".\n').format(rel_subdir(filepath)))
        if drop_atws:
            aws_lines = diff_plus.fix_trailing_whitespace()
            if aws_lines:
                RCTX.stdout.write(_('Added trailing white space to "{0}" at line(s) {{{1}}}: removed before application.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in aws_lines])))
        else:
            aws_lines = diff_plus.report_trailing_whitespace()
            if aws_lines:
                RCTX.stderr.write(_('Added trailing white space to "{1}" at line(s) {{{2}}}.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in aws_lines])))
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
                    if key in preamble.extras:
                        os.chmod(filepath, int(preamble.extras[key], 8))
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
        overlaps = get_overlap_data(new_file_list, top_patch)
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
        came_from_path = copied_from if copied_from else renamed_from
        file_data = top_patch.files.get(filepath, None)
        if file_data is None:
            file_data = FileData(filepath, top_patch, overlaps=overlaps, came_from_path=came_from_path, as_rename=renamed_from is not None)
            top_patch.files[filepath] = file_data
        elif came_from_path:
            file_data.came_from_path = came_from_path
            file_data.came_as_rename = renamed_from is not None
            file_data.reset_reference_paths()
        if renamed_from is not None:
            if renamed_from not in top_patch.files:
                top_patch.files[renamed_from] = FileData(renamed_from, top_patch, overlaps=overlaps)
            renames.append(diff_plus)
        elif copied_from is not None:
            copies.append(diff_plus)
        elif not os.path.exists(filepath):
            creates.append(diff_plus)
    # Now use patch to create any file created by the fold
    for diff_plus in epatch.diff_pluses:
        if diff_plus in creates:
            _apply_diff_plus(diff_plus)
    # Do any copying
    for diff_plus in epatch.diff_pluses:
        if diff_plus in copies:
            filepath = diff_plus.get_file_path(epatch.num_strip_levels)
            file_data = top_patch.files.get(filepath, None)
            assert file_data is not None
            copied_file_data = top_patch.files.get(file_data.came_from_path, None)
            if copied_file_data is None:
                file_data.before_file_path = file_data.came_from_path
                file_data.before_mode = utils.get_mode_for_file(file_data.came_from_path)
            else:
                file_data.before_file_path = copied_file_data.cached_orig_path
                file_data.before_mode = copied_file_data.orig_mode
            if not os.path.exists(file_data.before_file_path):
                RCTX.stderr.write(_('{0}: failed to copy {1}.\n').format(rel_subdir(file_data.path), rel_subdir(file_data.came_from_path)))
            else:
                try:
                    shutil.copy2(file_data.before_file_path, file_data.path)
                    os.chmod(file_data.path, file_data.before_mode)
                except OSError as edata:
                    RCTX.stderr.write(edata)
    # Do any renaming
    for diff_plus in epatch.diff_pluses:
        if diff_plus in renames:
            filepath = diff_plus.get_file_path(epatch.num_strip_levels)
            file_data = top_patch.files.get(filepath, None)
            assert file_data is not None
            renamed_file_data = top_patch.files.get(file_data.came_from_path, None)
            file_data.before_mode = renamed_file_data.orig_mode
            file_data.before_file_path = renamed_file_data.cached_orig_path
            renamed_file_data.renamed_to = file_data.path
            if not os.path.exists(file_data.before_file_path):
                RCTX.stderr.write(_('{0}: failed to rename {1}.\n').format(rel_subdir(file_data.path), rel_subdir(file_data.came_from_path)))
            else:
                try:
                    shutil.copy2(file_data.before_file_path, file_data.path)
                    os.chmod(file_data.path, file_data.before_mode)
                except OSError as edata:
                    RCTX.stderr.write(edata)
    # Apply the remaining changes
    for diff_plus in epatch.diff_pluses:
        if diff_plus not in creates:
            _apply_diff_plus(diff_plus)
    # Make sure the before_file_path fields are all correct
    for file_data in top_patch.files.values():
        # This is necessary because renamed files may have been overwritten
        file_data.set_before_file_path()
    if top_patch_needs_refresh():
        RCTX.stdout.write(_('{0}: patch needs refreshing.\n').format(top_patch.name))
    return cmd_result.OK

def do_fold_named_patch(patchname, absorb=False, force=False):
    '''Fold a name internal patch into the top patch.'''
    assert is_writable()
    assert not (absorb and force)
    patch = _get_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    elif patch.is_applied():
        RCTX.stderr.write(_('{0}: patch is applied.\n').format(patch.name))
        return cmd_result.ERROR
    epatch = TextPatch(patch)
    result = do_fold_epatch(epatch, absorb=absorb, force=force)
    if result != cmd_result.OK:
        return result
    _DB.series.remove(patch)
    dump_db()
    RCTX.stdout.write(_('"{0}": patch folded into patch "{0}".\n').format(patchname, get_top_patch_name()))
    return cmd_result.OK

def top_patch_needs_refresh():
    '''Does the top applied patch need a refresh?'''
    assert is_readable()
    top = get_series_index_for_top()
    if top is not None:
        return _DB.series[top].needs_refresh()
    return False

def _get_next_patch_index():
    '''Get the next patch to be applied'''
    assert is_readable()
    return get_series_index_for_next()

def get_outstanding_changes_below_top():
    '''Get the data detailing unfrefreshed/uncommitted files below the
    top patch.  I.e. outstanding changes.
    '''
    assert is_readable()
    if not _APPLIED_PATCHES:
        return OverlapData()
    top_patch = _APPLIED_PATCHES[-1]
    skip_set = set([filepath for filepath in top_patch.files])
    unrefreshed = {}
    for applied_patch in reversed(_APPLIED_PATCHES[:-1]):
        apfiles = applied_patch.get_filepaths()
        if apfiles:
            apfiles_set = set(apfiles) - skip_set
            for apfile in apfiles_set:
                if applied_patch.files[apfile].needs_refresh():
                    unrefreshed[apfile] = applied_patch
            skip_set |= apfiles_set
    uncommitted = set(scm_ifce.get_files_with_uncommitted_changes()) - skip_set
    return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

def get_overlap_data(filepaths, patch=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the files in filelist if they are added to the named
    (or next, if patchname is None) patch.
    '''
    assert is_readable()
    assert patch is None or patch.is_applied()
    if not filepaths:
        return OverlapData()
    applied_patches = _APPLIED_PATCHES if patch is None else _APPLIED_PATCHES[:_APPLIED_PATCHES.index(patch)]
    uncommitted = set(scm_ifce.get_files_with_uncommitted_changes(filepaths))
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

def get_file_diff(filepath, patchname, with_timestamps=True):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filepath in patch.files
    return patch.files[filepath].get_diff_plus(with_timestamps=with_timestamps)

def get_file_combined_diff(filepath, with_timestamps=True):
    assert is_readable()
    patch = None
    for applied_patch in _APPLIED_PATCHES:
        if filepath in applied_patch.files:
            patch = applied_patch
            break
    assert patch is not None
    return patch.files[filepath].get_diff_plus(combined=True, with_timestamps=with_timestamps)

def do_apply_next_patch(absorb=False, force=False):
    '''Apply the next patch in the series'''
    assert is_writable()
    assert not (absorb and force)
    def _apply_file_data_patch(file_data, biggest_ecode):
        patch_ok = True
        if file_data.binary is not False:
            RCTX.stdout.write(_('Processing binary file "{0}".\n').format(rel_subdir(file_data.path)))
            if file_data.after_mode is not None:
                open(file_data.path, 'wb').write(file_data.diff.contents)
            elif os.path.exists(file_data.path):
                os.remove(file_data.path)
        elif file_data.diff:
            RCTX.stdout.write(_('Patching file "{0}".\n').format(rel_subdir(file_data.path)))
            if drop_atws:
                aws_lines = file_data.diff.fix_trailing_whitespace()
                if aws_lines:
                    RCTX.stdout.write(_('"{0}": added trailing white space to "{1}" at line(s) {{{2}}}: removed before application.\n').format(next_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
            else:
                aws_lines = file_data.diff.report_trailing_whitespace()
                if aws_lines:
                    RCTX.stderr.write(_('"{0}": added trailing white space to "{1}" at line(s) {{{2}}}.\n').format(next_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
            result = _do_apply_diff_to_file(file_data.path, file_data.diff, delete_empty=file_data.after_mode is None)
            biggest_ecode = max(biggest_ecode, result.ecode)
            if result.ecode != 0:
                patch_ok = False
                file_data.diff = None
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
        if patch_ok:
            file_data.before_sha1 = utils.get_sha1_for_file(file_data.before_file_path)
            file_data.after_sha1 = utils.get_sha1_for_file(file_data.path)
            file_data.do_stash_current(None)
        else:
            file_data.before_sha1 = False
            file_data.after_sha1 = False
        if file_data.path in overlaps.unrefreshed:
            RCTX.stdout.write(_('Unrefreshed changes incorporated.\n'))
        elif file_data.path in overlaps.uncommitted:
            RCTX.stdout.write(_('Uncommited changes incorporated.\n'))
        dump_db()
        return biggest_ecode
    next_index = _get_next_patch_index()
    if next_index is None:
        top_patch = get_top_patch_name()
        if top_patch:
            RCTX.stderr.write(_('No pushable patches. "{0}" is on top.\n').format(top_patch))
        else:
            RCTX.stderr.write(_('No pushable patches.\n'))
        return cmd_result.ERROR
    next_patch = _DB.series[next_index]
    if force:
        overlaps = OverlapData()
    else:
        # We don't worry about overlaps for files that came from a copy or rename
        overlaps = get_overlap_data([fpth for fpth in next_patch.files if next_patch.files[fpth].came_from_path is None])
        if not absorb and len(overlaps):
            return overlaps.report_and_abort()
    os.mkdir(next_patch.cached_orig_dir_path)
    _APPLIED_PATCHES.append(next_patch)
    if len(next_patch.files) == 0:
        return cmd_result.OK
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
        elif os.path.exists(file_data.path):
            file_data.before_mode = file_data.orig_mode
        else:
            creates.append(file_data)
            file_data.before_mode = None
    biggest_ecode = 0
    # Next do the files that are created by this patch as they may have been copied
    for file_data in creates:
        biggest_ecode = _apply_file_data_patch(file_data, biggest_ecode)
    # Now do the copying
    for file_data in copies:
        copied_file_data = next_patch.files.get(file_data.came_from_path, None)
        if copied_file_data is not None:
            file_data.before_mode = copied_file_data.orig_mode
        else:
            file_data.before_mode = utils.get_mode_for_file(file_data.before_file_path)
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
            file_data.before_mode = next_patch.files[file_data.came_from_path].orig_mode
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
    RCTX.stdout.write(_('Patch "{0}" is now on top\n').format(next_patch.name))
    return cmd_result.OK

def get_top_applied_patch_for_file(filepath):
    assert is_readable()
    for applied_patch in reversed(_APPLIED_PATCHES):
        if filepath in applied_patch.files:
            return applied_patch.name
    return None

def _get_top_patch():
    '''Return the top applied patch'''
    assert is_readable()
    if not _APPLIED_PATCHES:
        RCTX.stderr.write(_('No patches applied.\n'))
        return None
    return _APPLIED_PATCHES[-1]

def get_top_patch_name():
    '''Return the name of the top applied patch'''
    assert is_readable()
    return None if not _APPLIED_PATCHES else _APPLIED_PATCHES[-1].name

def is_blocked_by_guard(patchname):
    '''Is the named patch blocked from being applied by any guards?'''
    assert is_readable()
    assert get_patch_series_index(patchname) is not None
    return get_patch(patchname).is_blocked_by_guard()

def is_pushable():
    '''Is there a pushable patch?'''
    assert is_readable()
    return _get_next_patch_index() is not None

def is_patch_pushable(patchname):
    '''Is the named patch pushable?'''
    assert is_readable()
    return get_patch(patchname).is_pushable()

def do_unapply_top_patch():
    '''Unapply the top applied patch'''
    assert is_writable()
    top_patch = _get_top_patch()
    if not top_patch:
        return cmd_result.ERROR
    if top_patch.needs_refresh():
        RCTX.stderr.write(_('Top patch ("{0}") needs to be refreshed.\n').format(top_patch.name))
        return cmd_result.ERROR_SUGGEST_REFRESH
    drop_atws = options.get('pop', 'drop_added_tws')
    for file_data in top_patch.files.values():
        if os.path.exists(file_data.path):
            os.remove(file_data.path)
        if os.path.exists(file_data.cached_orig_path):
            os.chmod(file_data.cached_orig_path, file_data.orig_mode)
            shutil.move(file_data.cached_orig_path, file_data.path)
        if file_data.diff:
            if drop_atws:
                aws_lines = file_data.diff.fix_trailing_whitespace()
                if aws_lines:
                    RCTX.stdout.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}: removed.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
            else:
                aws_lines = file_data.diff.report_trailing_whitespace()
                if aws_lines:
                    RCTX.stderr.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
    shutil.rmtree(top_patch.cached_orig_dir_path)
    _APPLIED_PATCHES.remove(top_patch)
    new_top_patch_name = get_top_patch_name()
    if new_top_patch_name is None:
        RCTX.stdout.write(_('There are now no patches applied.\n'))
    else:
         RCTX.stdout.write(_('Patch "{0}" is now on top.\n').format(new_top_patch_name))
    return cmd_result.OK

def get_filepaths_in_patch(patchname, filepaths=None):
    '''
    Return the names of the files in the named patch.
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(patchname) if patchname else get_series_index_for_top()
    assert patch_index is not None
    return _DB.series[patch_index].get_filepaths(filepaths)

def get_filepaths_in_next_patch(filepaths=None):
    '''
    Return the names of the files in the next patch (to be applied).
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    assert is_readable()
    patch_index = _get_next_patch_index()
    assert patch_index is not None
    return _DB.series[patch_index].get_filepaths(filepaths)

def _get_patch(patchname):
    patch_index = get_patch_series_index(patchname)
    if patch_index is None:
        RCTX.stderr.write(_('{0}: patch is NOT known.\n').format(patchname))
        return None
    return  _DB.series[patch_index]

def _get_named_or_top_patch(patchname):
    return _get_patch(patchname) if patchname is not None else _get_top_patch()

def get_patch_name(arg):
    patch = _get_named_or_top_patch(arg)
    return None if patch is None else patch.name

def do_add_files_to_top_patch(filepaths, absorb=False, force=False):
    '''Add the named files to the named patch'''
    assert not (absorb and force)
    top_patch = _get_top_patch()
    if top_patch is None:
        return cmd_result.ERROR
    prepend_subdir(filepaths)
    if not force:
        overlaps = get_overlap_data(filepaths, top_patch)
        if not absorb and len(overlaps) > 0:
            return overlaps.report_and_abort()
    else:
        overlaps = OverlapData()
    already_in_patch = set(top_patch.get_filepaths(filepaths))
    for filepath in filepaths:
        if filepath in already_in_patch:
            RCTX.stderr.write(_('{0}: file already in patch "{1}". Ignored.\n').format(rel_subdir(filepath), top_patch.name))
            continue
        elif os.path.isdir(filepath):
            RCTX.stderr.write(_('{0}: is a directory. Ignored.\n').format(rel_subdir(filepath)))
            continue
        already_in_patch.add(filepath)
        rfilepath = rel_subdir(filepath)
        top_patch.files[filepath] = FileData(filepath, top_patch, overlaps=overlaps)
        RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(rfilepath, top_patch.name))
        if filepath in overlaps.uncommitted:
            RCTX.stderr.write(_('{0}: Uncommited SCM changes have been incorporated in patch "{1}".\n').format(rfilepath, top_patch.name))
        elif filepath in overlaps.unrefreshed:
            RCTX.stderr.write(_('{0}: Unrefeshed changes in patch "{2}" incorporated in patch "{1}".\n').format(rfilepath, top_patch.name, overlaps.unrefreshed[filepath].name))
        dump_db() # do this now to minimize problems if interrupted
    return cmd_result.OK

def do_delete_files_in_top_patch(filepaths):
    assert is_writable()
    top_patch = _get_top_patch()
    if top_patch is None:
        return cmd_result.ERROR
    nonexists = 0
    ioerrors = 0
    for filepath in prepend_subdir(filepaths):
        if not os.path.exists(filepath):
            RCTX.stderr.write(_('{0}: file does not exist. Ignored.\n').format(rel_subdir(filepath)))
            nonexists += 1
            continue
        if filepath not in top_patch.files:
            top_patch.files[filepath] = FileData(filepath, top_patch)
        dump_db()
        try:
            os.remove(filepath)
        except OSError as edata:
            RCTX.stderr.write(edata)
            ioerrors += 1
            continue
        RCTX.stdout.write(_('{0}: file deleted within patch "{1}".\n').format(rel_subdir(filepath), top_patch.name))
    return cmd_result.OK if (ioerrors == 0 and len(filepaths) > nonexists) else cmd_result.ERROR

def do_copy_file_to_top_patch(filepath, as_filepath, overwrite=False):
    assert is_writable()
    top_patch = _get_top_patch()
    if top_patch is None:
        return cmd_result.ERROR
    filepath = rel_basedir(filepath)
    as_filepath = rel_basedir(as_filepath)
    if filepath == as_filepath:
        return cmd_result.OK
    if not os.path.exists(filepath):
        RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
        return cmd_result.ERROR
    if not overwrite and as_filepath in top_patch.files:
        RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(as_filepath)))
        return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    needs_refresh = False
    record_copy = True
    came_from_path = filepath
    if filepath in top_patch.files:
        if top_patch.files[filepath].came_from_path:
            # this file was a copy or rename so refer to the original
            came_from_path = top_patch.files[filepath].came_from_path
        else:
            # if this file was created by the patch so don't record the copy
            record_copy = os.path.exists(top_patch.files[filepath].cached_orig_path)
    if as_filepath in top_patch.files:
        needs_refresh = True
    elif record_copy:
        top_patch.files[as_filepath] = FileData(as_filepath, top_patch, came_from_path=came_from_path)
    else:
        top_patch.files[as_filepath] = FileData(as_filepath, top_patch)
    dump_db()
    try:
        shutil.copy2(filepath, as_filepath)
    except OSError as edata:
        RCTX.stderr.write(edata)
        return cmd_result.ERROR
    if needs_refresh:
        top_patch.files[as_filepath].reset_came_from(came_from_path if record_copy else None, False)
    dump_db()
    RCTX.stdout.write(_('{0}: file copied to "{1}" in patch "{2}".\n').format(rel_subdir(filepath), rel_subdir(as_filepath), top_patch.name))
    return cmd_result.OK

def do_rename_file_in_top_patch(filepath, new_filepath, force=False, overwrite=False):
    assert is_writable()
    def _delete_original():
        if os.path.exists(top_patch.files[filepath].stashed_path):
            os.remove(top_patch.files[filepath].stashed_path)
        del top_patch.files[filepath]
    top_patch = _get_top_patch()
    if top_patch is None:
        return cmd_result.ERROR
    filepath = rel_basedir(filepath)
    new_filepath = rel_basedir(new_filepath)
    if filepath == new_filepath:
        return cmd_result.OK
    if not os.path.exists(filepath):
        RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
        return cmd_result.ERROR
    if not overwrite and new_filepath in top_patch.files:
        RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(new_filepath)))
        return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    needs_refresh = False
    as_rename = True
    came_from_path = filepath
    is_boomerang = False
    if not filepath in top_patch.files:
        result = do_add_files_to_top_patch([rel_subdir(filepath)], absorb=False, force=force)
        result &= ~cmd_result.SUGGEST_ABSORB
        if result != cmd_result.OK:
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
        top_patch.files[new_filepath] = FileData(new_filepath, top_patch, came_from_path=came_from_path, as_rename=as_rename)
    dump_db()
    try:
        os.rename(filepath, new_filepath)
    except OSError as edata:
        RCTX.stderr.write(edata)
        return cmd_result.ERROR
    if came_from_path:
        top_patch.files[came_from_path].reset_renamed_to(new_filepath if as_rename else None)
    if needs_refresh:
        if is_boomerang:
            top_patch.files[new_filepath].renamed_to = None
        top_patch.files[new_filepath].reset_came_from(came_from_path, as_rename)
    dump_db()
    RCTX.stdout.write(_('{0}: file renamed to "{1}" in patch "{2}".\n').format(rel_subdir(filepath), rel_subdir(new_filepath), top_patch.name))
    return cmd_result.OK

def do_drop_files_fm_patch(patchname, filepaths):
    '''Drop the named file from the named patch'''
    assert is_writable()
    patch = _get_named_or_top_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    prepend_subdir(filepaths)
    for filepath in filepaths:
        if filepath in patch.files:
            patch.do_drop_file(filepath)
            RCTX.stdout.write(_('{0}: file dropped from patch "{1}".\n').format(rel_subdir(filepath), patch.name))
        elif os.path.isdir(filepath):
            RCTX.stderr.write(_('{0}: is a directory: ignored.\n').format(rel_subdir(filepath)))
        else:
            RCTX.stderr.write(_('{0}: file not in patch "{1}": ignored.\n').format(rel_subdir(filepath), patch.name))
    return cmd_result.OK

def do_duplicate_patch(patchname, as_patchname, newdescription):
    '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
    assert is_writable()
    patch = _get_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    if patch.needs_refresh():
        RCTX.stderr.write(_('{0}: patch needs refresh.\n').format(patch.name))
        RCTX.stderr.write(_('Aborted.\n'))
        return cmd_result.ERROR_SUGGEST_REFRESH
    if patch_is_in_series(as_patchname):
        RCTX.stderr.write(_('{0}: patch already in series.\n').format(as_patchname))
        RCTX.stderr.write(_('Aborted.\n'))
        return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    elif not utils.is_valid_dir_name(as_patchname):
        RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(as_patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    newpatch = copy.deepcopy(patch)
    newpatch.set_name(as_patchname)
    newpatch.description = _tidy_text(newdescription)
    _insert_patch(newpatch)
    dump_db()
    RCTX.stdout.write(_('{0}: patch duplicated as "{1}"\n').format(patch.name, as_patchname))
    return cmd_result.OK

def do_refresh_overlapped_files(file_list):
    '''Refresh any files in the list which are in an applied patch
    (within the topmost such patch).'''
    assert is_writable()
    assert len(_APPLIED_PATCHES) > 0
    file_set = set(file_list)
    eflags = 0
    for applied_patch in reversed(_APPLIED_PATCHES):
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
    assert is_writable()
    patch = _get_named_or_top_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    if not patch.is_applied():
        RCTX.stderr.write(_('Patch "{0}" is not applied\n').format(patchname))
        return cmd_result.ERROR
    eflags = 0
    for file_data in patch.files.values():
        eflags |= file_data.do_refresh(quiet=False)
    if eflags > 0:
        RCTX.stderr.write(_('Patch "{0}" requires another refresh after issues are resolved.\n').format(patch.name))
    else:
        RCTX.stdout.write(_('Patch "{0}" refreshed.\n').format(patch.name))
    return eflags

def do_remove_patch(patchname):
    '''Remove the named patch from the series'''
    assert is_writable()
    assert patchname
    patch = _get_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    if patch.is_applied():
        RCTX.stderr.write(_('{0}: patch is applied and cannot be removed.\n').format(patchname))
        return cmd_result.ERROR
    if options.get('remove', 'keep_patch_backup'):
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    dump_db()
    shutil.rmtree(patch.stash_dir_path)
    RCTX.stdout.write(_('Patch "{0}" removed (but available for restoration).\n').format(patchname))
    return cmd_result.OK

def do_restore_patch(patchname, as_patchname):
    '''Restore the named patch from back up with the specified name'''
    assert is_writable()
    if not patchname in _DB.kept_patches:
        RCTX.stderr.write(_('{0}: is NOT available for restoration\n').format(patchname))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    if patch_is_in_series(as_patchname):
        RCTX.stderr.write(_('{0}: Already exists in database\n').format(as_patchname))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    elif not utils.is_valid_dir_name(as_patchname):
        RCTX.stderr.write(_('"{0}" is not a valid name. {1}\n').format(as_patchname, utils.ALLOWED_DIR_NAME_CHARS_MSG))
        return cmd_result.ERROR|cmd_result.SUGGEST_RENAME
    patch = _DB.kept_patches[patchname]
    if as_patchname:
        patch.set_name(as_patchname)
    _insert_patch(patch)
    del _DB.kept_patches[patchname]
    dump_db()
    return cmd_result.OK

def _tidy_text(text):
    '''Return the given text with any trailing white space removed.
    Also ensure there is a new line at the end of the lastline.'''
    tidy_text = ''
    for line in text.splitlines():
        tidy_text += re.sub('[ \t]+$', '', line) + '\n'
    return tidy_text

def do_set_patch_description(patchname, text):
    assert is_writable()
    patch = _get_named_or_top_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    old_description = patch.description
    if text:
        text = _tidy_text(text)
    patch.description = text if text is not None else ''
    dump_db()
    if old_description != patch.description:
        change_lines = difflib.ndiff(old_description.splitlines(True), patch.description.splitlines(True))
        RCTX.stdout.write(''.join(change_lines))
    return cmd_result.OK

def get_patch_description(patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return _DB.series[patch_index].description

def do_set_series_description(text):
    assert is_writable()
    old_description = _DB.description
    if text:
        text = _tidy_text(text)
    _DB.description = text if text is not None else ''
    dump_db()
    if old_description != _DB.description:
        change_lines = difflib.ndiff(old_description.splitlines(True), _DB.description.splitlines(True))
        RCTX.stdout.write(''.join(change_lines))
    return cmd_result.OK

def get_series_description():
    assert is_readable()
    return _DB.description

def get_patch_table_data():
    assert is_readable()
    return [patch.get_table_row() for patch in _DB.series]

def get_selected_guards():
    assert is_readable()
    return _DB.selected_guards

def get_patch_guards(patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch_data = _DB.series[patch_index]
    return PatchData.Guards(positive=patch_data.pos_guards, negative=patch_data.neg_guards)

def do_set_patch_guards(patchname, guards):
    assert is_writable()
    patch = _get_named_or_top_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    patch.pos_guards = set(guards.positive)
    patch.neg_guards = set(guards.negative)
    dump_db()
    RCTX.stdout.write(_('{0}: patch positive guards = {{{1}}}\n').format(patchname, ', '.join(sorted(patch.pos_guards))))
    RCTX.stdout.write(_('{0}: patch negative guards = {{{1}}}\n').format(patchname, ', '.join(sorted(patch.neg_guards))))
    return cmd_result.OK

def do_set_patch_guards_fm_str(patchname, guards_str):
    assert is_writable()
    guards_list = guards_str.split()
    pos_guards = [grd[1:] for grd in guards_list if grd.startswith('+')]
    neg_guards = [grd[1:] for grd in guards_list if grd.startswith('-')]
    if len(guards_list) != (len(pos_guards) + len(neg_guards)):
        RCTX.stderr.write(_('Guards must start with "+" or "-" and contain no whitespace.\n'))
        RCTX.stderr.write( _('Aborted.\n'))
        return cmd_result.ERROR | cmd_result.SUGGEST_EDIT
    guards = PatchData.Guards(positive=pos_guards, negative=neg_guards)
    return do_set_patch_guards(patchname, guards)

def do_select_guards(guards):
    assert is_writable()
    bad_guard_count = 0
    for guard in guards:
        if guard.startswith('+') or guard.startswith('-'):
            RCTX.stderr.write(_('{0}: guard names may NOT begin with "+" or "-".\n').format(guard))
            bad_guard_count += 1
    if bad_guard_count > 0:
        RCTX.stderr.write(_('Aborted.\n'))
        return cmd_result.ERROR|cmd_result.SUGGEST_EDIT
    _DB.selected_guards = set(guards)
    dump_db()
    RCTX.stdout.write(_('{{{0}}}: is now the set of selected guards.\n').format(', '.join(sorted(_DB.selected_guards))))
    return cmd_result.OK

def get_extdiff_files_for(filepath, patchname):
    assert is_readable()
    assert is_applied(patchname)
    patch =  _DB.series[get_patch_series_index(patchname)]
    assert filepath in patch.files
    assert patch.files[filepath].get_overlapping_patch() is None
    before = patch.files[filepath].before_file_path
    return _O_IP_PAIR(original_version=before, patched_version=filepath)

def get_reconciliation_paths(filepath):
    assert is_readable()
    top_patch = _get_top_patch()
    if not top_patch:
        return None
    assert filepath in top_patch.files
    return top_patch.files[filepath].get_reconciliation_paths()

class TextDiffPlus(patchlib.DiffPlus):
    def __init__(self, file_data, with_timestamps=True):
        diff_plus = file_data.get_diff_plus(as_refreshed=True, with_timestamps=with_timestamps)
        patchlib.DiffPlus.__init__(self, preambles=diff_plus.preambles, diff=diff_plus.diff)
        self.validity = file_data.get_validity()

class TextPatch(patchlib.Patch):
    def __init__(self, patch, with_timestamps=True):
        patchlib.Patch.__init__(self, num_strip_levels=1)
        self.source_name = patch.name
        self.state = PatchState.APPLIED_REFRESHED if patch.is_applied() else PatchState.UNAPPLIED
        self.set_description(patch.description)
        self.set_comments('# created by: Darning\n')
        for filepath in sorted(patch.files):
            edp = TextDiffPlus(patch.files[filepath], with_timestamps=with_timestamps)
            if edp.diff is None and (patch.files[filepath].renamed_to and not patch.files[filepath].came_from_path):
                continue
            self.diff_pluses.append(edp)
            if self.state == PatchState.UNAPPLIED:
                continue
            if self.state == PatchState.APPLIED_REFRESHED and edp.validity != FileData.Validity.REFRESHED:
                self.state = PatchState.APPLIED_NEEDS_REFRESH if edp.validity == FileData.Validity.NEEDS_REFRESH else PatchState.APPLIED_UNREFRESHABLE
            elif self.state == PatchState.APPLIED_NEEDS_REFRESH and edp.validity == FileData.Validity.UNREFRESHABLE:
                self.state = PatchState.APPLIED_UNREFRESHABLE
        self.set_header_diffstat(strip_level=self.num_strip_levels)

def get_textpatch(patchname, with_timestamps=True):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    return TextPatch(patch, with_timestamps=with_timestamps)

def do_export_patch_as(patchname, export_filename, force=False, overwrite=False, with_timestamps=True):
    assert is_writable()
    patch = _get_named_or_top_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    textpatch = TextPatch(patch, with_timestamps=with_timestamps)
    if not force:
        if textpatch.state == PatchState.APPLIED_NEEDS_REFRESH:
            RCTX.stderr.write(_('Patch needs to be refreshed.\n'))
            return cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH
        elif textpatch.state == PatchState.APPLIED_UNREFRESHABLE:
            RCTX.stderr.write(_('Patch needs to be refreshed but has problems which prevent refresh.\n'))
            return cmd_result.ERROR_SUGGEST_FORCE
    if not export_filename:
        export_filename = utils.convert_patchname_to_filename(patch.name)
    if not overwrite and os.path.exists(export_filename):
        RCTX.stderr.write(_('{0}: file already exists.\n').format(export_filename))
        return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    try:
        open(export_filename, 'wb').write(str(textpatch))
    except IOError as edata:
        RCTX.stderr.write(str(edata) + '\n')
        return cmd_result.ERROR
    return cmd_result.OK

class CombinedTextPatch(patchlib.Patch):
    def __init__(self, with_timestamps=True):
        patchlib.Patch.__init__(self, num_strip_levels=1)
        description = ''
        file_first_patch = {}
        for applied_patch in _APPLIED_PATCHES:
            description += applied_patch.description
            for filepath in applied_patch.files:
                if filepath not in file_first_patch:
                    file_first_patch[filepath] = applied_patch
        self.set_description(description)
        self.set_comments('# created by: Darning\n')
        for filepath in sorted(file_first_patch):
            file_data = file_first_patch[filepath].files[filepath]
            self.diff_pluses.append(file_data.get_diff_plus(combined=True, with_timestamps=with_timestamps))
        self.set_header_diffstat(strip_level=self.num_strip_levels)

def get_combined_textpatch(with_timestamps=True):
    assert is_readable()
    if get_series_index_for_top() is None:
        return None
    return CombinedTextPatch(with_timestamps=with_timestamps)

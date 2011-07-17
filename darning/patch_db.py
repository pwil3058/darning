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

from darning import i18n
from darning import scm_ifce
from darning import runext
from darning import utils
from darning import patchlib
from darning import fsdb
from darning import options

options.define('pop', 'drop_added_tws', options.Defn(options.str_to_bool, True, _('Remove added trailing white space (TWS) from patch after pop')))
options.define('push', 'drop_added_tws', options.Defn(options.str_to_bool, True, _('Remove added trailing white space (TWS) from patch before push')))
options.define('remove', 'keep_patch_backup', options.Defn(options.str_to_bool, True, _('Keep back up copies of removed patches.  Facilitates restoration at a later time.')))

# A convenience tuple for sending an original and patched version of something
_O_IP_PAIR = collections.namedtuple('_O_IP_PAIR', ['original_version', 'patched_version'])

class Failure:
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

class FileData:
    '''Change data for a single file'''
    class Presence(object):
        ADDED = patchlib.FilePathPlus.ADDED
        REMOVED = patchlib.FilePathPlus.DELETED
        EXTANT = patchlib.FilePathPlus.EXTANT
    class Validity(object):
        REFRESHED, NEEDS_REFRESH, UNREFRESHABLE = range(3)
    Status = collections.namedtuple('Status', ['presence', 'validity'])
    MERGE_CRE = re.compile('^(<<<<<<<|>>>>>>>).*$')
    def __init__(self, filepath):
        self.path = filepath
        self.diff = None
        try:
            fstat = os.stat(filepath)
            self.old_mode = fstat.st_mode
            self.timestamp = fstat.st_mtime
        except OSError:
            self.old_mode = None
            self.timestamp = 0
        self.new_mode = self.old_mode
        self.scm_revision = None
    @property
    def binary(self):
        return isinstance(self.diff, BinaryDiff)
    def needs_refresh(self):
        '''Does this file need a refresh? (Given that it is not overshadowed.)'''
        if os.path.exists(self.path):
            return self.timestamp < os.path.getmtime(self.path) or self.new_mode is None
        else:
            return self.new_mode is not None or self.timestamp < 0
    def has_unresolved_merges(self):
        if os.path.exists(self.path):
            for line in open(self.path).readlines():
                if FileData.MERGE_CRE.match(line):
                    return True
        return False
    def get_presence(self):
        if self.old_mode is None:
            return FileData.Presence.ADDED
        elif self.new_mode is None:
            return FileData.Presence.DELETED
        else:
            return FileData.Presence.EXTANT

OverlapData = collections.namedtuple('OverlapData', ['unrefreshed', 'uncommitted'])

def _total_overlap_count(overlap_data):
    '''Total number of overlaps'''
    count = 0
    for item in overlap_data:
        count += len(item)
    return count

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
    APPLIED_NEEDS_REFRESH = '-'
    APPLIED_UNFEFRESHABLE = '!'

class PatchTable(object):
    Row = collections.namedtuple('Row', ['name', 'state', 'pos_guards', 'neg_guards'])

class PatchData:
    '''Store data for changes to a number of files as a single patch'''
    Guards = collections.namedtuple('Guards', ['positive', 'negative'])
    def __init__(self, name, description):
        self.name = name
        self.description = description if description is not None else ''
        self.files = dict()
        self.pos_guards = set()
        self.neg_guards = set()
        self.scm_revision = None
    def do_add_file(self, filepath, force=False):
        '''Add the named file to this patch'''
        assert is_writable()
        assert filepath not in self.files
        if not self.is_applied():
            # not much to do here
            self.files[filepath] = FileData(filepath)
            dump_db()
            return
        assert force or not self.file_overlaps_uncommitted_or_unrefreshed(filepath)
        self.files[filepath] = FileData(filepath)
        overlapped_by = self.get_overlapping_patch_for_file(filepath)
        if overlapped_by is None:
            self.do_cache_original(filepath, force)
        else:
            overlapping_corig_f_path = overlapped_by.get_cached_original_file_path(filepath)
            if os.path.exists(overlapping_corig_f_path):
                os.link(overlapping_corig_f_path, self.get_cached_original_file_path(filepath))
                self.files[filepath].old_mode = overlapped_by.files[filepath].old_mode
            else:
                self.files[filepath].old_mode = None
        dump_db()
    def do_drop_file(self, filepath):
        '''Drop the named file from this patch'''
        assert is_writable()
        assert filepath in self.files
        if not self.is_applied():
            # not much to do here
            del self.files[filepath]
            dump_db()
            return
        corig_f_path = self.get_cached_original_file_path(filepath)
        overlapped_by = self.get_overlapping_patch_for_file(filepath)
        if overlapped_by is None:
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists(corig_f_path):
                os.chmod(corig_f_path, self.files[filepath].old_mode)
                shutil.move(corig_f_path, filepath)
        else:
            overlapping_corig_f_path = overlapped_by.get_cached_original_file_path(filepath)
            if os.path.exists(corig_f_path):
                shutil.move(corig_f_path, overlapping_corig_f_path)
                overlapped_by.files[filepath].old_mode = self.files[filepath].old_mode
            else:
                if os.path.exists(overlapping_corig_f_path):
                    os.remove(overlapping_corig_f_path)
                overlapped_by.files[filepath].old_mode = None
            # Make sure that the overlapping file gets refreshed
            overlapped_by.files[filepath].timestamp = 0
        del self.files[filepath]
        dump_db()
    def do_apply(self, force=False):
        '''Apply this patch'''
        assert is_writable()
        assert not self.is_applied()
        assert force or _total_overlap_count(get_patch_overlap_data(self.name)) == 0
        os.mkdir(self.get_cached_original_dir_path())
        results = {}
        if len(self.files) == 0:
            return results
        patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch',]
        drop_atws = options.get('push', 'drop_added_tws')
        for file_data in self.files.values():
            self.do_cache_original(file_data.path, force)
            result = None
            patch_ok = True
            if file_data.binary is not False:
                if file_data.new_mode is not None:
                    open(file_data.path, 'wb').write(file_data.diff.contents)
                elif os.path.exists(file_data.path):
                    os.remove(file_data.path)
            elif file_data.diff:
                if drop_atws:
                    file_data.diff.fix_trailing_whitespace()
                result = runext.run_cmd(patch_cmd + [file_data.path], str(file_data.diff))
                patch_ok = result.ecode == 0
            file_exists = os.path.exists(file_data.path)
            if file_exists:
                if file_data.new_mode is not None:
                    os.chmod(file_data.path, file_data.new_mode)
            else:
                # A non None new_mode means that the file existed when
                # the diff was made so a refresh will be required
                patch_ok = patch_ok and file_data.new_mode is None
            if os.path.exists(file_data.path) and patch_ok:
                file_data.timestamp = os.path.getmtime(file_data.path)
            else:
                file_data.timestamp = 0
            if not patch_ok:
                if result is None:
                    result = runext.Result(1, '', _('Needs update.\n'))
                else:
                    result = runext.Result(max(result.ecode, 1), result.stdout, result.stderr + _('Needs update.\n'))
            if result is not None:
                results[file_data.path] = result
            dump_db()
        return results
    def copy_refreshed_version_to(self, filepath, target_name):
        file_data = self.files[filepath]
        if not file_data.needs_refresh():
            if os.path.exists(corig_f_path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(filepath, target_name)
            return
        corig_f_path = self.get_cached_original_file_path(filepath)
        if file_data.binary is not False:
            if os.path.exists(corig_f_path):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(corig_f_path, target_name)
            return
        if os.path.exists(corig_f_path):
            utils.ensure_file_dir_exists(target_name)
            shutil.copy2(corig_f_path, target_name)
        elif file_data.diff:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write('')
        if file_data.diff:
            patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch', target_name]
            runext.run_cmd(patch_cmd, str(file_data.diff))
    def do_cache_original(self, filepath, force):
        '''Cache the original of the named file for this patch'''
        # "force" argument is supplied to allow shortcutting SCM check
        # which can be expensive
        assert is_writable()
        assert filepath in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filepath) is None
        corig_f_path = self.get_cached_original_file_path(filepath)
        olpatch = self.get_unrefreshed_overlapped_patch_for_file(filepath) if not force else None
        if olpatch:
            olpatch.copy_refreshed_version_to(filepath, corig_f_path)
            self.files[filepath].timestamp = 0
        elif force and scm_ifce.has_uncommitted_change(filepath):
            scm_ifce.copy_clean_version_to(filepath, corig_f_path)
            self.files[filepath].timestamp = 0
        elif os.path.exists(filepath):
            # We'll try to preserve links when we pop patches
            # so we move the file to the cached originals' directory and then make
            # a copy (without links) in the working directory
            utils.ensure_file_dir_exists(corig_f_path)
            shutil.move(filepath, corig_f_path)
            shutil.copy2(corig_f_path, filepath)
        if os.path.exists(corig_f_path):
            # We need this so that we need to reset it on pop
            old_mode = os.stat(corig_f_path).st_mode
            # Make the cached original read only to prevent accidental change
            os.chmod(corig_f_path, utils.turn_off_write(old_mode))
            self.files[filepath].old_mode = old_mode
        else:
            self.files[filepath].old_mode = None
    def generate_diff_preamble_for_file(self, filepath, combined=False):
        assert is_readable()
        assert filepath in self.files
        file_data = self.files[filepath]
        if self.is_applied():
            olp = None if combined else self.get_overlapping_patch_for_file(filepath)
            if olp is not None:
                new_mode = olp.files[filepath].old_mode
            else:
                new_mode = os.stat(filepath).st_mode if os.path.exists(filepath) else None
        else:
            new_mode = file_data.new_mode
        if file_data.old_mode is None:
            lines = ['diff --git /dev/null {0}\n'.format(os.path.join('a', filepath)), ]
            if new_mode is not None:
                lines.append('new file mode {0:07o}\n'.format(new_mode))
        elif new_mode is None:
            lines = ['diff --git {0} /dev/null\n'.format(os.path.join('a', filepath)), ]
            lines.append('deleted file mode {0:07o}\n'.format(file_data.old_mode))
        else:
            lines = ['diff --git {0} {1}\n'.format(os.path.join('a', filepath), os.path.join('b', filepath)), ]
            if file_data.old_mode != new_mode:
                lines.append('old mode {0:07o}\n'.format(file_data.old_mode))
                lines.append('new mode {0:07o}\n'.format(new_mode))
        return patchlib.Preamble.parse_lines(lines)
    def generate_diff_for_file(self, filepath, combined=False):
        assert is_readable()
        assert filepath in self.files
        assert self.is_applied()
        olp = None if combined else self.get_overlapping_patch_for_file(filepath)
        to_file = filepath if olp is None else olp.get_cached_original_file_path(filepath)
        fm_file = self.get_cached_original_file_path(filepath)
        fm_exists = os.path.exists(fm_file)
        if os.path.exists(to_file):
            to_name_label = os.path.join('b' if fm_exists else 'a', filepath)
            to_time_stamp = _pts_for_path(to_file)
            with open(to_file) as fobj:
                to_contents = fobj.read()
        else:
            to_name_label = '/dev/null'
            to_time_stamp = _PTS_ZERO
            to_contents = ''
        if fm_exists:
            fm_name_label = os.path.join('a', filepath)
            fm_time_stamp = _pts_for_path(fm_file)
            with open(fm_file) as fobj:
                fm_contents = fobj.read()
        else:
            fm_name_label = '/dev/null'
            fm_time_stamp = _PTS_ZERO
            fm_contents = ''
        if to_contents == fm_contents:
            return ''
        if to_contents.find('\000') != -1 or fm_contents.find('\000') != -1:
            return BinaryDiff(patchlib._PAIR(fm_name_label, to_name_label))
        diffgen = difflib.unified_diff(fm_contents.splitlines(True), to_contents.splitlines(True),
            fromfile=fm_name_label, tofile=to_name_label, fromfiledate=fm_time_stamp, tofiledate=to_time_stamp)
        return patchlib.Diff.parse_lines(list(diffgen))
    def get_diff_for_file(self, filepath, combined=False):
        assert is_readable()
        assert filepath in self.files
        preamble = self.generate_diff_preamble_for_file(filepath, combined)
        diff = self.generate_diff_for_file(filepath, combined) if self.is_applied() else self.files[filepath].diff
        return patchlib.DiffPlus([preamble], diff)
    def do_refresh_file(self, filepath):
        '''Refresh the named file in this patch'''
        assert is_writable()
        assert filepath in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filepath) is None
        file_data = self.files[filepath]
        # Do a check for unresolved merges here
        if file_data.has_unresolved_merges():
            # ensure this file shows up as needing refresh
            file_data.timestamp = -1
            dump_db()
            return runext.Result(3, '', _('File has unresolved merge(s).\n'))
        f_exists = os.path.exists(filepath)
        if f_exists or os.path.exists(self.get_cached_original_file_path(filepath)):
            file_data.diff = self.generate_diff_for_file(filepath)
            if f_exists:
                stat_data = os.stat(filepath)
                file_data.new_mode = stat_data.st_mode
                file_data.timestamp = stat_data.st_mtime
            else:
                file_data.new_mode = None
                file_data.timestamp = 0
            result = runext.Result(0, str(file_data.diff), '')
        else:
            file_data.diff = None
            file_data.new_mode = None
            file_data.timestamp = 0
            file_data.scm_revision = scm_ifce.get_revision(filepath=file_data.path)
            result = runext.Result(0, '', _('File "{0}" does not exist\n').format(filepath))
        dump_db()
        return result
    def do_unapply(self):
        '''Unapply this patch'''
        assert is_writable()
        assert self.is_applied()
        assert not self.needs_refresh()
        assert not self.is_overlapped()
        drop_atws = options.get('pop', 'drop_added_tws')
        for file_data in self.files.values():
            if os.path.exists(file_data.path):
                os.remove(file_data.path)
            corig_f_path = self.get_cached_original_file_path(file_data.path)
            if os.path.exists(corig_f_path):
                os.chmod(corig_f_path, file_data.old_mode)
                shutil.move(corig_f_path, file_data.path)
            if drop_atws and file_data.diff:
                file_data.diff.fix_trailing_whitespace()
        shutil.rmtree(self.get_cached_original_dir_path())
        return True
    def do_refresh(self):
        '''Refresh the patch'''
        assert is_writable()
        assert self.is_applied()
        results = {}
        for filepath in self.files:
            results[filepath] = self.do_refresh_file(filepath)
        return results
    def get_cached_original_dir_path(self):
        '''Return the path of the cached originals' directory for this patch'''
        return os.path.join(_ORIGINALS_DIR, self.name)
    def get_cached_original_file_path(self, filepath):
        '''Return the path of the cached original for the named file in this patch'''
        return os.path.join(_ORIGINALS_DIR, self.name, filepath)
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
            table = []
            for fde in self.files.values():
                if (self.get_overlapping_patch_for_file(fde.path) is None) and fde.needs_refresh():
                    if fde.has_unresolved_merges():
                        validity = FileData.Validity.UNREFRESHABLE
                    else:
                        validity = FileData.Validity.NEEDS_REFRESH
                else:
                    validity = FileData.Validity.REFRESHED
                table.append(fsdb.Data(fde.path, FileData.Status(fde.get_presence(), validity), None))
        else:
            table = [fsdb.Data(fde.path, FileData.Status(fde.get_presence(), None), None) for fde in self.files.values()]
        return table
    def get_overlapping_patch_for_file(self, filepath):
        '''Return the patch (if any) which overlaps the named file in this patch'''
        assert is_readable()
        assert self.is_applied()
        after = False
        for apatch in get_applied_patch_list():
            if after:
                if filepath in apatch.files:
                    return apatch
            else:
                after = apatch.name == self.name
        return None
    def get_unrefreshed_overlapped_patch_for_file(self, filepath):
        '''
        Return the highest applied patch containing unrefreshed
        changes for this file.
        '''
        assert is_readable()
        applied_patches = get_applied_patch_list()
        try:
            patch_index = applied_patches.index(self)
            applied_patches = applied_patches[:patch_index]
        except ValueError:
            pass
        for applied_patch in reversed(applied_patches):
            apfile = applied_patch.files.get(filepath, None)
            if apfile is not None:
                return applied_patch if apfile.needs_refresh() else None
        return None
    def file_overlaps_uncommitted_or_unrefreshed(self, filepath):
        '''
        Will this file overlap unrefreshed/uncommitted files?
        '''
        assert is_readable()
        if self.get_unrefreshed_overlapped_patch_for_file(filepath) is not None:
            return True
        return scm_ifce.has_uncommitted_change(filepath)
    def get_table_row(self):
        if not self.is_applied():
            state = PatchState.UNAPPLIED
        elif self.needs_refresh():
            if self.has_unresolved_merges():
                state = PatchState.APPLIED_UNFEFRESHABLE
            else:
                state = PatchState.APPLIED_NEEDS_REFRESH
        else:
            state = PatchState.APPLIED_REFRESHED
        return PatchTable.Row(name=self.name, state=state, pos_guards=self.pos_guards, neg_guards=self.neg_guards)
    def is_applied(self):
        '''Is this patch applied?'''
        return os.path.isdir(self.get_cached_original_dir_path())
    def is_blocked_by_guard(self):
        '''Is the this patch blocked from being applied by any guards?'''
        if (self.pos_guards & _DB.selected_guards) != self.pos_guards:
            return True
        if len(self.neg_guards & _DB.selected_guards) != 0:
            return True
        return False
    def is_overlapped(self):
        '''Are any files in this patch overlapped by applied patches?'''
        for filepath in self.files:
            if self.get_overlapping_patch_for_file(filepath) is not None:
                return True
        return False
    def is_pushable(self):
        '''Is this patch pushable?'''
        return not self.is_applied() and not self.is_blocked_by_guard()
    def needs_refresh(self):
        '''Does this patch need a refresh?'''
        for file_data in self.files.values():
            if self.get_overlapping_patch_for_file(file_data.path) is not None:
                continue
            if file_data.needs_refresh():
                return True
        return False
    def has_unresolved_merges(self):
        '''Is this patch refreshable? i.e. no unresolved merges'''
        for file_data in self.files.values():
            if self.get_overlapping_patch_for_file(file_data.path) is not None:
                continue
            if file_data.has_unresolved_merges():
                return True
        return False

class DataBase:
    '''Storage for an ordered sequence/series of patches'''
    def __init__(self, description, host_scm=None):
        self.description = description if description else ''
        self.selected_guards = set()
        self.series = list()
        self.kept_patches = dict()
        self.host_scm = host_scm

_DB_DIR = '.darning.dbd'
_ORIGINALS_DIR = os.path.join(_DB_DIR, 'orig')
_DB_FILE = os.path.join(_DB_DIR, 'database')
_DB_LOCK_FILE = os.path.join(_DB_DIR, 'lock')
_DB = None

def find_base_dir(dirpath=None):
    '''Find the nearest directory above that contains a database'''
    if dirpath is None:
        dirpath = os.getcwd()
    subdir_parts = []
    while True:
        if os.path.isdir(os.path.join(dirpath, _DB_DIR)):
            subdir = None if not subdir_parts else os.path.join(*subdir_parts)
            return dirpath, subdir
        else:
            dirpath, basename = os.path.split(dirpath)
            if not basename:
                break
            subdir_parts.insert(0, basename)
    return None, None

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

def create_db(description):
    '''Create a patch database in the current directory?'''
    def rollback():
        '''Undo steps that were completed before failure occured'''
        for filnm in [_DB_FILE, _DB_LOCK_FILE ]:
            if os.path.exists(filnm):
                os.remove(filnm)
        for dirnm in [_ORIGINALS_DIR, _DB_DIR]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    if os.path.exists(_DB_DIR):
        if os.path.exists(_ORIGINALS_DIR) and os.path.exists(_DB_FILE):
            return Failure(_('Database already exists'))
        return Failure(_('Database directory exists'))
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(_DB_DIR, dir_mode)
        os.mkdir(_ORIGINALS_DIR, dir_mode)
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
        return Failure(edata.strerror)
    except Exception:
        rollback()
        raise
    return True

def release_db():
    '''Release access to the database'''
    assert is_readable()
    global _DB
    writeable = is_writable()
    _DB = None
    if writeable:
        _unlock_db()

def load_db(lock=True):
    '''Load the database for access (read only unless lock is True)'''
    global _DB
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

def get_applied_patch_list():
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
    return [patch.name for patch in get_applied_patch_list()]

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
        __slots__ = ['presence', 'validity', 'origin']
        def __init__(self, presence, validity, origin=None):
            self.presence = presence
            self.validity = validity
            self.origin = origin
    assert is_readable()
    if len(_DB.series) == 0:
        return []
    file_map = {}
    for patch in _DB.series:
        if not patch.is_applied():
            continue
        for fde in patch.files.values():
            if (patch.get_overlapping_patch_for_file(fde.path) is None) and fde.needs_refresh():
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
        table.append(fsdb.Data(filepath, FileData.Status(data.presence, data.validity), data.origin))
    return table

def patch_is_in_series(patchname):
    '''Is there a patch with the given name in the series?'''
    return get_patch_series_index(patchname) is not None

def is_applied(patchname):
    '''Is the named patch currently applied?'''
    return get_patch(patchname).is_applied()

def is_top_applied_patch(patchname):
    '''Is the named patch the top applied patch?'''
    top_index = get_series_index_for_top()
    if top_index is None:
        return False
    return _DB.series[top_index].name == patchname

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
    assert get_patch_series_index(patchname) is None
    patch = PatchData(patchname, description)
    _insert_patch(patch)
    dump_db()

def do_import_patch(epatch, patchname):
    '''Import an external patch with the given name (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(patchname) is None
    descr = utils.make_utf8_compliant(epatch.get_description())
    patch = PatchData(patchname, descr)
    for diff_plus in epatch.diff_pluses:
        path = diff_plus.get_file_path(epatch.num_strip_levels)
        patch.do_add_file(path)
        patch.files[path].diff = diff_plus.diff
        for preamble in diff_plus.preambles:
            if preamble.preamble_type == 'git':
                for key in ['new mode', 'new file mode']:
                    if key in preamble.extras:
                        patch.files[path].new_mode = int(preamble.extras[key], 8)
                        break
                break
    _insert_patch(patch)
    _dump_db()

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

def get_overlap_data(filepaths, patchname=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the named files
    '''
    assert is_readable()
    if not filepaths:
        return OverlapData({}, set())
    applied_patches = get_applied_patch_list()
    if patchname is not None:
        try:
            patch = get_patch(patchname)
            patch_index = applied_patches.index(patch)
            applied_patches = applied_patches[:patch_index]
        except ValueError:
            pass
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
                    unrefreshed[apfile] = applied_patch.name
    return OverlapData(unrefreshed, uncommitted)

def get_patch_overlap_data(patchname):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the named patch's current files if filepaths is None.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return get_overlap_data(_DB.series[patch_index].get_filepaths())

def get_file_diff(filepath, patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return _DB.series[patch_index].get_diff_for_file(filepath)

def get_file_combined_diff(filepath):
    assert is_readable()
    patch = None
    for applied_patch in get_applied_patch_list():
        if filepath in applied_patch.files:
            patch = applied_patch
            break
    assert patch is not None
    return patch.get_diff_for_file(filepath, True)

def get_filelist_overlap_data(filepaths, patchname=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the files in filelist if they are added to the named
    (or top, if None) patch.
    '''
    assert is_readable()
    assert patchname is None or get_patch_series_index(patchname) is not None
    return get_overlap_data(filepaths, patchname)

def get_next_patch_overlap_data():
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the nextpatch
    '''
    assert is_readable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return OverlapData(unrefreshed = {}, uncommitted = [])
    return get_overlap_data(_DB.series[next_index].get_filepaths())

def apply_patch(force=False):
    '''Apply the next patch in the series'''
    assert is_writable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return (False, _('There are no pushable patches available'))
    return (True, _DB.series[next_index].do_apply(force))

def get_top_applied_patch_for_file(filepath):
    assert is_readable()
    applied_patches = get_applied_patch_list()
    for applied_patch in reversed(applied_patches):
        if filepath in applied_patch.files:
            return applied_patch.name
    return None

def get_top_patch_name():
    '''Return the name of the top applied patch'''
    assert is_readable()
    top = get_series_index_for_top()
    return None if top is None else _DB.series[top].name

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

def unapply_top_patch():
    '''Unapply the top applied patch'''
    assert is_writable()
    assert not top_patch_needs_refresh()
    top_patch_index = get_series_index_for_top()
    assert top_patch_index is not None
    return _DB.series[top_patch_index].do_unapply()

def get_filepaths_in_patch(patchname, filepaths=None):
    '''
    Return the names of the files in the named patch.
    If filepaths is not None restrict the returned list to names that
    are also in filepaths.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
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

def add_file_to_patch(patchname, filepath, force=False):
    '''Add the named file to the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filepath not in patch.files
    return patch.do_add_file(filepath, force=force)

def do_drop_file_fm_patch(patchname, filepath):
    '''Drop the named file from the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filepath in patch.files
    return patch.do_drop_file(filepath)

def do_duplicate_patch(patchname, as_patchname, newdescription):
    '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
    assert is_writable()
    assert get_series_index(as_patchname) is None
    patch = get_patch(patchname)
    assert patch is not None and not patch.needs_refresh()
    newpatch = copy.deepcopy(patch)
    newpatch.name = as_patchname
    newpatch.description = newdescription
    _insert_patch(newpatch)
    _dump_db()

def do_refresh_overlapped_files(file_list):
    '''Refresh any files in the list which are in an applied patch
    (within the topmost such patch).'''
    assert is_writable()
    assert get_series_index_for_top() is not None
    applied_patches = get_applied_patch_list()
    assert len(applied_patches) > 0
    file_set = set(file_list)
    results = {}
    for applied_patch in reversed(applied_patches):
        for file_name in applied_patch.files:
            if file_name in file_set:
                results[file_name] = applied_patch.do_refresh_file(file_name)
                file_set.remove(file_name)
                if len(file_set) == 0:
                    break
        if len(file_set) == 0:
            break
    return results

def do_refresh_patch(patchname):
    '''Refresh the named patch'''
    assert is_writable()
    assert is_applied(patchname)
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return _DB.series[patch_index].do_refresh()

def do_remove_patch(patchname):
    '''Remove the named patch from the series'''
    assert is_writable()
    assert get_patch_series_index(patchname) is not None
    assert not is_applied(patchname)
    patch = get_patch(patchname)
    assert patch is not None
    assert not patch.is_applied()
    if options.get('remove', 'keep_patch_backup'):
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    dump_db()

def do_restore_patch(patchname, as_patchname):
    '''Restore the named patch from back up with the specified name'''
    assert is_writable()
    assert not as_patchname or get_patch_series_index(as_patchname) is None
    assert as_patchname or get_patch_series_index(patchname) is None
    assert patchname in _DB.kept_patches
    patch = _DB.kept_patches[patchname]
    if as_patchname:
        patch.name = as_patchname
    _insert_patch(patch)
    del _DB.kept_patches[patchname]
    dump_db()

def do_set_patch_description(patchname, text):
    assert is_writable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    _DB.series[patch_index].description = text if text is not None else ''
    dump_db()

def get_patch_description(patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return _DB.series[patch_index].description

def do_set_series_description(text):
    assert is_writable()
    _DB.description = text if text is not None else ''
    dump_db()

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
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    _DB.series[patch_index].pos_guards = set(guards.positive)
    _DB.series[patch_index].neg_guards = set(guards.negative)
    dump_db()

def do_select_guards(guards):
    assert is_writable()
    _DB.selected_guards = set(guards)
    dump_db()

def get_extdiff_files_for(filepath, patchname):
    assert is_readable()
    assert is_applied(patchname)
    patch =  _DB.series[get_patch_series_index(patchname)]
    assert filepath in patch.files
    assert patch.get_overlapping_patch_for_file(filepath) is None
    orig = patch.get_cached_original_file_path(filepath)
    return _O_IP_PAIR(original_version=orig, patched_version=filepath)


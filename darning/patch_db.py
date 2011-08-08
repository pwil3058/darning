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

class ReportContext(object):
    def __init__(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr

RCTX = ReportContext(stdout=sys.stdout, stderr=sys.stderr)

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
            return FileData.Presence.REMOVED
        else:
            return FileData.Presence.EXTANT

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
            RCTX.stderr.write(_('{0}: file has unrefreshed changes in (applied) "{1}".\n').format(rfilepath, opatch))
        RCTX.stderr.write(_('Aborted.\n'))
        return cmd_result.ERROR_SUGGEST_FORCE_OR_REFRESH if len(self.unrefreshed) > 0 else cmd_result.ERROR_SUGGEST_FORCE

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
    APPLIED_UNREFRESHABLE = '!'

class PatchTable(object):
    Row = collections.namedtuple('Row', ['name', 'state', 'pos_guards', 'neg_guards'])

class PatchData:
    '''Store data for changes to a number of files as a single patch'''
    Guards = collections.namedtuple('Guards', ['positive', 'negative'])
    def __init__(self, name, description):
        self.name = name
        self.description = _tidy_text(description) if description is not None else ''
        self.files = dict()
        self.pos_guards = set()
        self.neg_guards = set()
        self.scm_revision = None
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
    def do_cache_original(self, filepath, olurpatch=None, scm_has_uncommitted_changes=False):
        '''Cache the original of the named file for this patch'''
        # "force" argument is supplied to allow shortcutting SCM check
        # which can be expensive
        assert is_writable()
        assert filepath in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filepath) is None
        assert not (olurpatch and scm_has_uncommitted_changes)
        corig_f_path = self.get_cached_original_file_path(filepath)
        if olurpatch:
            olurpatch.copy_refreshed_version_to(filepath, corig_f_path)
            self.files[filepath].timestamp = 0
        elif scm_has_uncommitted_changes:
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
            RCTX.stderr.write(_('"{0}": file has unresolved merge(s).\n').format(rel_subdir(filepath)))
            return cmd_result.ERROR
        f_exists = os.path.exists(filepath)
        if f_exists or os.path.exists(self.get_cached_original_file_path(filepath)):
            file_data.diff = self.generate_diff_for_file(filepath)
            if f_exists:
                stat_data = os.stat(filepath)
                file_data.new_mode = stat_data.st_mode
                file_data.timestamp = stat_data.st_mtime
                if file_data.old_mode is not None and file_data.old_mode != file_data.new_mode:
                    RCTX.stdout.write(_('"{0}": mode {1:07o} -> {2:07o}.\n').format(rel_subdir(filepath), file_data.old_mode, file_data.new_mode))
            else:
                file_data.new_mode = None
                file_data.timestamp = 0
            RCTX.stdout.write(str(file_data.diff))
        else:
            file_data.diff = None
            file_data.new_mode = None
            file_data.timestamp = 0
            file_data.scm_revision = scm_ifce.get_revision(filepath=file_data.path)
            RCTX.stdout.write(_('"{0}": file does not exist\n').format(rel_subdir(filepath)))
        dump_db()
        return cmd_result.OK
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
    def _get_file_applied_validity(self, file_data):
        assert self.is_applied()
        if (self.get_overlapping_patch_for_file(file_data.path) is None) and file_data.needs_refresh():
            if file_data.has_unresolved_merges():
                return FileData.Validity.UNREFRESHABLE
            else:
                return FileData.Validity.NEEDS_REFRESH
        else:
            return FileData.Validity.REFRESHED
    def get_filepath_validity(self, filepath):
        if not self.is_applied():
            return None
        return self._get_file_applied_validity(self.files[filepath])
    def get_files_table(self):
        is_applied = self.is_applied()
        if is_applied:
            table = []
            for fde in self.files.values():
                validity = self._get_file_applied_validity(fde)
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
        self.description = _tidy_text(description) if description else ''
        self.selected_guards = set()
        self.series = list()
        self.kept_patches = dict()
        self.host_scm = host_scm

_DB_DIR = '.darning.dbd'
_ORIGINALS_DIR = os.path.join(_DB_DIR, 'orig')
_DB_FILE = os.path.join(_DB_DIR, 'database')
_DB_LOCK_FILE = os.path.join(_DB_DIR, 'lock')
_DB = None
_SUB_DIR = None

def rel_subdir(filepath):
    return filepath if _SUB_DIR is None else os.path.relpath(filepath, SUBDIR)

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
        RCTX.stderr.write(_('Inside existing playground: {0}.\n').format(os.path.relpath(root)))
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
    if get_patch_series_index(patchname) is not None:
        RCTX.stderr.write(_('patch "{0}" already exists\n').format(patchname))
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
    descr = utils.make_utf8_compliant(epatch.get_description())
    patch = PatchData(patchname, descr)
    for diff_plus in epatch.diff_pluses:
        file_data = FileData(diff_plus.get_file_path(epatch.num_strip_levels))
        file_data.diff = diff_plus.diff
        for preamble in diff_plus.preambles:
            if preamble.preamble_type == 'git':
                for key in ['new mode', 'new file mode']:
                    if key in preamble.extras:
                        file_data.new_mode = int(preamble.extras[key], 8)
                        break
                break
        patch.files[file_data.path] = file_data
        RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(file_data.path, patchname))
    _insert_patch(patch)
    dump_db()
    top_patchname = get_top_patch_name()
    if top_patchname:
        RCTX.stdout.write(_('{0}: patch inserted after patch "{1}".\n').format(patchname, top_patchname))
    else:
        RCTX.stdout.write(_('{0}: patch inserted at start of series.\n').format(patchname))
    return cmd_result.OK

def do_fold_epatch(epatch, force=False):
    '''Fold an external patch into the top patch.'''
    assert is_writable()
    top_patch = _get_patch(None)
    if not top_patch:
        return cmd_result.ERROR
    top_patch_file_set = set([filepath for filepath in top_patch.files])
    new_file_list = [filepath for filepath in epatch.get_file_paths(epatch.num_strip_levels) if filepath not in top_patch_file_set]
    result = do_add_files_to_patch(top_patch.name, new_file_list, force=force)
    if result != cmd_result.OK:
        return result
    patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch', '--quiet']
    drop_atws = options.get('push', 'drop_added_tws')
    for diff_plus in epatch.diff_pluses:
        top_patch.files[filepath].timestamp = -1
        dump_db()
        filepath = diff_plus.get_file_path(epatch.num_strip_levels)
        RCTX.stdout.write(_('Patching file "{0}".\n').format(rel_subdir(filepath)))
        if drop_atws:
            aws_lines = diff_plus.fix_trailing_whitespace()
            if aws_lines:
                RCTX.stdout.write(_('Added trailing white space to "{0}" at line(s) {{{1}}}: removed before application.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in aws_lines])))
        else:
            aws_lines = diff_plus.report_trailing_whitespace()
            if aws_lines:
                RCTX.stderr.write(_('Added trailing white space to "{1}" at line(s) {{{2}}}.\n').format(rel_subdir(filepath), ', '.join([str(line) for line in aws_lines])))
        result = runext.run_cmd(patch_cmd + [filepath], str(diff_plus.diff))
        if result.ecode == 0:
            RCTX.stderr.write(result.stdout)
        else:
            RCTX.stdout.write(result.stdout)
        RCTX.stderr.write(result.stderr)
        if os.path.exists(filepath):
            for preamble in diff_plus.preambles:
                if preamble.preamble_type == 'git':
                    for key in ['new mode', 'new file mode']:
                        if key in preamble.extras:
                            os.chmod(filepath, int(preamble.extras[key], 8))
                            break
                    break
    if top_patch_needs_refresh():
        RCTX.stdout.write(_('{0}: patch needs refreshing.\n').format(top_patch.name))
    return cmd_result.OK

def do_fold_named_patch(patchname, force=False):
    '''Fold a name internal patch into the top patch.'''
    assert is_writable()
    patch = _get_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    elif patch.is_applied():
        RCTX.stderr.write(_('{0}: patch is applied.\n').format(patch.name))
        return cmd_result.ERROR
    epatch = TextPatch(patch)
    result = do_fold_epatch(epatch, force=force)
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
    applied_patches = get_applied_patch_list()
    top_patch = applied_patches[-1] if applied_patches else None
    skip_set = set([filepath for filepath in top_patch.files]) if top_patch else set()
    unrefreshed = {}
    for applied_patch in reversed(applied_patches[:-1]):
        apfiles = applied_patch.get_filepaths()
        if apfiles:
            apfiles_set = set(apfiles) - skip_set
            for apfile in apfiles_set:
                if applied_patch.files[apfile].needs_refresh():
                    unrefreshed[apfile] = applied_patch.name
            skip_set |= apfiles_set
    uncommitted = set(scm_ifce.get_files_with_uncommitted_changes()) - skip_set
    return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

def get_overlap_data(filepaths, patchname=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the named files
    '''
    assert is_readable()
    if not filepaths:
        return OverlapData()
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
    return OverlapData(unrefreshed=unrefreshed, uncommitted=uncommitted)

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
        return OverlapData()
    return get_overlap_data(_DB.series[next_index].get_filepaths())

def do_apply_next_patch(force=False):
    '''Apply the next patch in the series'''
    assert is_writable()
    next_index = _get_next_patch_index()
    if next_index is None:
        top_patch = get_top_patch_name()
        if top_patch:
            RCTX.stderr.write(_('No pushable patches. "{0}" is on top.\n').format(top_patch))
        else:
            RCTX.stderr.write(_('No pushable patches.\n'))
        return cmd_result.ERROR
    next_patch = _DB.series[next_index]
    overlaps = get_overlap_data(next_patch.get_filepaths())
    if not force and len(overlaps):
        return overlaps.report_and_abort()
    os.mkdir(next_patch.get_cached_original_dir_path())
    if len(next_patch.files) == 0:
        return cmd_result.OK
    patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch', '--quiet']
    drop_atws = options.get('push', 'drop_added_tws')
    biggest_ecode = 0
    for file_data in next_patch.files.values():
        olurpatch = overlaps.unrefreshed.get(file_data.path, None)
        scm_has_uncommitted_changes = file_data.path in overlaps.uncommitted
        next_patch.do_cache_original(file_data.path, olurpatch, scm_has_uncommitted_changes)
        patch_ok = True
        if file_data.binary is not False:
            RCTX.stdout.write(_('Processing binary file "{0}".\n').format(rel_subdir(file_data.path)))
            if file_data.new_mode is not None:
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
            result = runext.run_cmd(patch_cmd + [file_data.path], str(file_data.diff))
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
        file_exists = os.path.exists(file_data.path)
        if file_exists:
            if file_data.new_mode is not None:
                os.chmod(file_data.path, file_data.new_mode)
            file_data.timestamp = os.path.getmtime(file_data.path) if patch_ok else 0
        else:
            # A non None new_mode means that the file existed when
            # the diff was made so a refresh will be required
            if file_data.new_mode is not None:
                biggest_ecode = max(biggest_ecode, 1)
                RCTX.stderr.write(_('Expected file not found.\n'))
            file_data.timestamp = 0
        if os.path.exists(file_data.path) and patch_ok:
            file_data.timestamp = os.path.getmtime(file_data.path)
        else:
            file_data.timestamp = 0
        if olurpatch:
            RCTX.stdout.write(_('Unrefreshed changes incorporated.\n'))
        elif scm_has_uncommitted_changes:
            RCTX.stdout.write(_('Uncommited changes incorporated.\n'))
        dump_db()
    if biggest_ecode > 1:
        RCTX.stderr.write(_('A refresh is required after issues are resolved.\n'))
    elif biggest_ecode > 0:
        RCTX.stderr.write(_('A refresh is required.\n'))
    RCTX.stdout.write(_('Patch "{0}" is now on top\n').format(next_patch.name))
    return cmd_result.OK

def get_top_applied_patch_for_file(filepath):
    assert is_readable()
    applied_patches = get_applied_patch_list()
    for applied_patch in reversed(applied_patches):
        if filepath in applied_patch.files:
            return applied_patch.name
    return None

def get_top_patch():
    '''Return the top applied patch'''
    assert is_readable()
    top = get_series_index_for_top()
    return None if top is None else _DB.series[top]

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

def do_unapply_top_patch():
    '''Unapply the top applied patch'''
    assert is_writable()
    top_patch_index = get_series_index_for_top()
    if top_patch_index is None:
        RCTX.stderr.write(_('No patches applied.\n'))
        return cmd_result.ERROR
    top_patch = _DB.series[top_patch_index]
    if top_patch.needs_refresh():
        RCTX.stderr.write(_('Top patch ("{0}") needs to be refreshed.\n').format(top_patch.name))
        return cmd_result.ERROR_SUGGEST_REFRESH
    drop_atws = options.get('pop', 'drop_added_tws')
    for file_data in top_patch.files.values():
        if os.path.exists(file_data.path):
            os.remove(file_data.path)
        corig_f_path = top_patch.get_cached_original_file_path(file_data.path)
        if os.path.exists(corig_f_path):
            os.chmod(corig_f_path, file_data.old_mode)
            shutil.move(corig_f_path, file_data.path)
        if file_data.diff:
            if drop_atws:
                aws_lines = file_data.diff.fix_trailing_whitespace()
                if aws_lines:
                    RCTX.stdout.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}: removed.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
            else:
                aws_lines = file_data.diff.report_trailing_whitespace()
                if aws_lines:
                    RCTX.stderr.write(_('"{0}": adds trailing white space to "{1}" at line(s) {{{2}}}.\n').format(top_patch.name, rel_subdir(file_data.path), ', '.join([str(line) for line in aws_lines])))
    shutil.rmtree(top_patch.get_cached_original_dir_path())
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
    if not patchname:
        patch_index = get_series_index_for_top()
        if patch_index is None:
            RCTX.stderr.write(_('No patches applied'))
    else:
        patch_index = get_patch_series_index(patchname)
        if patch_index is None:
            RCTX.stderr.write(_('{0}: patch is NOT known').format(patchname))
    return  _DB.series[patch_index] if patch_index is not None else None

def do_add_files_to_patch(patchname, filepaths, force=False):
    '''Add the named files to the named patch'''
    patch = _get_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    prepend_subdir(filepaths)
    patch_is_applied = patch.is_applied()
    if patch_is_applied:
        overlaps = get_filelist_overlap_data(filepaths, patch.name)
        if not force and overlaps:
            return overlaps.report_and_abort()
    else:
        overlaps = OverlapData()
    already_in_patch = set(patch.get_filepaths(filepaths))
    for filepath in filepaths:
        if filepath in already_in_patch:
            RCTX.stderr.write(_('{0}: file already in patch "{1}". Ignored.\n').format(rel_subdir(filepath), patch.name))
            continue
        elif os.path.isdir(filepath):
            RCTX.stderr.write(_('{0}: is a directory. Ignored.\n').format(rel_subdir(filepath)))
            continue
        already_in_patch.add(filepath)
        rfilepath = rel_subdir(filepath)
        overlapped_by = patch.get_overlapping_patch_for_file(filepath) if patch_is_applied else None
        patch.files[filepath] = FileData(filepath)
        if overlapped_by is None:
            if filepath in overlaps.uncommitted:
                patch.do_cache_original(filepath, None, True)
                RCTX.stderr.write(_('{0}: file added to patch "{1}". Uncommited SCM changes have been incorporated.\n').format(rfilepath, patch.name))
            elif filepath in overlaps.unrefreshed:
                patch.do_cache_original(filepath, get_patch(overlaps.unrefreshed[filepath]), False)
                RCTX.stderr.write(_('{0}: file added to patch "{1}". Unrefeshed changes in patch "{2}" incorporated.\n').format(rfilepath, patch.name, overlaps.unrefreshed[filepath]))
            else:
                patch.do_cache_original(filepath, None, False)
                RCTX.stdout.write(_('{0}: file added to patch "{1}".\n').format(rfilepath, patch.name))
        else:
            overlapping_corig_f_path = overlapped_by.get_cached_original_file_path(filepath)
            if os.path.exists(overlapping_corig_f_path):
                os.link(overlapping_corig_f_path, patch.get_cached_original_file_path(filepath))
                patch.files[filepath].old_mode = overlapped_by.files[filepath].old_mode
            else:
                patch.files[filepath].old_mode = None
            RCTX.stderr.write(_('{0}: (overlapped) file added to patch "{1}".\n').format(rfilepath, patch.name))
        dump_db() # do this now to minimize problems if interrupted
    return cmd_result.OK

def do_delete_files_in_top_patch(filepaths):
    assert is_writable()
    patch = get_top_patch()
    if patch is None:
        RCTX.stderr.write(_('No patches applied.\n'))
        return cmd_result.ERROR
    nonexists = 0
    ioerrors = 0
    for filepath in prepend_subdir(filepaths):
        if not os.path.exists(filepath):
            RCTX.stderr.write(_('{0}: file does not exist. Ignored.\n').format(rel_subdir(filepath)))
            nonexists += 1
            continue
        if filepath not in patch.files:
            patch.files[filepath] = FileData(filepath)
            patch.do_cache_original(filepath, None, False)
        dump_db()
        try:
            os.remove(filepath)
        except OSError as edata:
            RCTX.stderr.write(edata)
            ioerrors += 1
            continue
        RCTX.stdout.write(_('{0}: file deleted within patch "{1}".\n').format(rel_subdir(filepath), patch.name))
    return cmd_result.OK if (ioerrors == 0 and len(filepaths) > nonexists) else cmd_result.ERROR

def do_copy_file_to_top_patch(filepath, as_filepath, overwrite=False):
    assert is_writable()
    patch = get_top_patch()
    if patch is None:
        RCTX.stderr.write(_('No patches applied.\n'))
        return cmd_result.ERROR
    filepath = rel_basedir(filepath)
    if not os.path.exists(filepath):
        RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
        return cmd_result.ERROR
    as_filepath = rel_basedir(as_filepath)
    if as_filepath in patch.files:
        if not overwrite:
            RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(as_filepath)))
            return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    else:
        patch.files[as_filepath] = FileData(as_filepath)
        patch.do_cache_original(as_filepath, None, False)
    dump_db()
    try:
        shutil.copy2(filepath, as_filepath)
    except OSError as edata:
        RCTX.stderr.write(edata)
        return cmd_result.ERROR
    RCTX.stdout.write(_('{0}: file added to patch "{1}" as "{2}".\n').format(rel_subdir(filepath), patch.name, rel_subdir(as_filepath)))
    return cmd_result.OK

def do_rename_file_in_top_patch(filepath, new_filepath, force=False, overwrite=False):
    assert is_writable()
    patch = get_top_patch()
    if patch is None:
        RCTX.stderr.write(_('No patches applied.\n'))
        return cmd_result.ERROR
    filepath = rel_basedir(filepath)
    if not os.path.exists(filepath):
        RCTX.stderr.write(_('{0}: file does not exist.\n').format(rel_subdir(filepath)))
        return cmd_result.ERROR
    if not filepath in patch.files:
        result = do_add_files_to_patch(patch.name, [rel_subdir(filepath)], force=force)
        if result != cmd_result.OK:
            return result
    new_filepath = rel_basedir(new_filepath)
    if new_filepath in patch.files:
        if not overwrite:
            RCTX.stderr.write(_('{0}: file already in patch.\n').format(rel_subdir(new_filepath)))
            return cmd_result.ERROR | cmd_result.SUGGEST_RENAME
    else:
        patch.files[new_filepath] = FileData(new_filepath)
        patch.do_cache_original(new_filepath, None, False)
    dump_db()
    try:
        os.rename(filepath, new_filepath)
    except OSError as edata:
        RCTX.stderr.write(edata)
        return cmd_result.ERROR
    RCTX.stdout.write(_('{0}: file added to patch "{1}" as "{2}".\n').format(rel_subdir(filepath), patch.name, rel_subdir(new_filepath)))
    return cmd_result.OK

def do_drop_files_fm_patch(patchname, filepaths):
    '''Drop the named file from the named patch'''
    assert is_writable()
    patch = _get_patch(patchname)
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
    newpatch = copy.deepcopy(patch)
    newpatch.name = as_patchname
    newpatch.description = _tidy_text(newdescription)
    _insert_patch(newpatch)
    dump_db()
    RCTX.stdout.write(_('{0}: patch duplicated as "{1}"\n').format(patch.name, as_patchname))
    return cmd_result.OK

def do_refresh_overlapped_files(file_list):
    '''Refresh any files in the list which are in an applied patch
    (within the topmost such patch).'''
    assert is_writable()
    assert get_series_index_for_top() is not None
    applied_patches = get_applied_patch_list()
    assert len(applied_patches) > 0
    file_set = set(file_list)
    eflags = 0
    for applied_patch in reversed(applied_patches):
        for file_name in applied_patch.files:
            if file_name in file_set:
                eflags |= applied_patch.do_refresh_file(file_name)
                file_set.remove(file_name)
                if len(file_set) == 0:
                    break
        if len(file_set) == 0:
            break
    return eflags

def do_refresh_patch(patchname=None):
    '''Refresh the named (or top applied) patch'''
    assert is_writable()
    patch = _get_patch(patchname)
    if patch is None:
        return cmd_result.ERROR
    if not patch.is_applied():
        RCTX.stderr.write(_('Patch "{0}" is not applied\n').format(patchname))
        return cmd_result.ERROR
    is_top = is_top_applied_patch(patch.name)
    eflags = 0
    for filepath in patch.files:
        if not is_top:
            olap_patch = patch.get_overlapping_patch_for_file(filepath)
            if olap_patch:
                RCTX.stderr.write(_('"{0}: overlapped by patch "{1}": skipped\n').format(rel_subdir(filepath), olap_patch.name))
                continue
        eflags |= patch.do_refresh_file(filepath)
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
        RCTX.stderr,write(_('{0}: patch is applied and cannot be removed\n').format(patchname))
    if options.get('remove', 'keep_patch_backup'):
        _DB.kept_patches[patch.name] = patch
    _DB.series.remove(patch)
    dump_db()
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
    patch = _DB.kept_patches[patchname]
    if as_patchname:
        patch.name = as_patchname
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
    patch = _get_patch(patchname)
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
    patch = _get_patch(patchname)
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
    assert patch.get_overlapping_patch_for_file(filepath) is None
    orig = patch.get_cached_original_file_path(filepath)
    return _O_IP_PAIR(original_version=orig, patched_version=filepath)

class TextDiffPlus(patchlib.DiffPlus):
    def __init__(self, patch, filepath):
        preamble = patch.generate_diff_preamble_for_file(filepath)
        diff = patch.files[filepath].diff
        patchlib.DiffPlus.__init__(self, [preamble], diff if diff else None)
        self.validity = patch.get_filepath_validity(filepath)

class TextPatch(patchlib.Patch):
    def __init__(self, patch):
        patchlib.Patch.__init__(self, num_strip_levels=1)
        self.name = patch.name
        self.state = PatchState.APPLIED_REFRESHED if patch.is_applied() else PatchState.UNAPPLIED
        self.set_description(patch.description)
        self.set_comments('# created by: Darning\n')
        for filepath in sorted(patch.files):
            edp = TextDiffPlus(patch, filepath)
            self.diff_pluses.append(edp)
            if self.state == PatchState.UNAPPLIED:
                continue
            if self.state == PatchState.APPLIED_REFRESHED and edp.validity != FileData.Validity.REFRESHED:
                self.state = PatchState.APPLIED_NEEDS_REFRESH if edp.validity == FileData.Validity.NEEDS_REFRESH else PatchState.APPLIED_UNREFRESHABLE
            elif self.state == PatchState.APPLIED_NEEDS_REFRESH and edp.validity == FileData.Validity.UNREFRESHABLE:
                self.state = PatchState.APPLIED_UNREFRESHABLE
        self.set_header_diffstat(strip_level=self.num_strip_levels)

def get_textpatch(patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    return TextPatch(patch)

def do_export_patch_as(patchname, export_filename, force=False, overwrite=False):
    assert is_writable()
    patch = _get_patch(patchname)
    if not patch:
        return cmd_result.ERROR
    textpatch = TextPatch(patch)
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

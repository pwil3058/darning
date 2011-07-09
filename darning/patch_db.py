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

from darning import scm_ifce
from darning import runext
from darning import utils
from darning import patchlib
from darning import fsdb

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
        return 'Failure(%s)' % self.msg

class BinaryDiff(patchlib.Diff):
    def __init__(self, file_data):
        Diff.__init__(self, 'binary', [], file_data, hunks=None)
        if os.path.exists(file_data.after):
            self.contents = open(file_data.after).read()
        else:
            self.contents = None
    def __str__(self):
        return 'Binary files "{0}" and "{1}" differ.\n'.format(self.file_data.before, self.file_data.after)
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
    def __init__(self, name):
        self.name = name
        self.diff = None
        try:
            fstat = os.stat(name)
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
        if os.path.exists(self.name):
            return self.timestamp < os.path.getmtime(self.name) or self.new_mode is None
        else:
            return self.new_mode is not None or self.timestamp < 0
    def has_unresolved_merges(self):
        if os.path.exists(self.name):
            for line in open(self.name).readlines():
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
    def do_add_file(self, filename, force=False):
        '''Add the named file to this patch'''
        assert is_writable()
        assert filename not in self.files
        if not self.is_applied():
            # not much to do here
            self.files[filename] = FileData(filename)
            dump_db()
            return
        assert force or not self.file_overlaps_uncommitted_or_unrefreshed(filename)
        self.files[filename] = FileData(filename)
        overlapped_by = self.get_overlapping_patch_for_file(filename)
        if overlapped_by is None:
            self.do_back_up_file(filename, force)
        else:
            overlapping_bu_f_name = overlapped_by.get_backup_file_name(filename)
            if os.path.exists(overlapping_bu_f_name):
                os.link(overlapping_bu_f_name, self.get_backup_file_name(filename))
                self.files[filename].old_mode = overlapped_by.files[filename].old_mode
            else:
                self.files[filename].old_mode = None
        dump_db()
    def do_drop_file(self, filename):
        '''Drop the named file from this patch'''
        assert is_writable()
        assert filename in self.files
        if not self.is_applied():
            # not much to do here
            del self.files[filename]
            dump_db()
            return
        bu_f_name = self.get_backup_file_name(filename)
        overlapped_by = self.get_overlapping_patch_for_file(filename)
        if overlapped_by is None:
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists(bu_f_name):
                os.chmod(bu_f_name, self.files[filename].old_mode)
                shutil.move(bu_f_name, filename)
        else:
            overlapping_bu_f_name = overlapped_by.get_backup_file_name(filename)
            if os.path.exists(bu_f_name):
                shutil.move(bu_f_name, overlapping_bu_f_name)
                overlapped_by.files[filename].old_mode = self.files[filename].old_mode
            else:
                if os.path.exists(overlapping_bu_f_name):
                    os.remove(overlapping_bu_f_name)
                overlapped_by.files[filename].old_mode = None
            # Make sure that the overlapping file gets refreshed
            overlapped_by.files[filename].timestamp = 0
        del self.files[filename]
        dump_db()
    def do_apply(self, force=False):
        '''Apply this patch'''
        assert is_writable()
        assert not self.is_applied()
        assert force or _total_overlap_count(get_patch_overlap_data(self.name)) == 0
        os.mkdir(self.get_backup_dir_name())
        results = {}
        if len(self.files) == 0:
            return results
        patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch',]
        for file_data in self.files.values():
            self.do_back_up_file(file_data.name, force)
            result = None
            patch_ok = True
            if file_data.binary is not False:
                if file_data.new_mode is not None:
                    open(file_data.name, 'wb').write(file_data.diff.contents)
                elif os.path.exists(file_data.name):
                    os.remove(file_data.name)
            elif file_data.diff:
                result = runext.run_cmd(patch_cmd + [file_data.name], str(file_data.diff))
                patch_ok = result.ecode == 0
            file_exists = os.path.exists(file_data.name)
            if file_exists:
                if file_data.new_mode is not None:
                    os.chmod(file_data.name, file_data.new_mode)
            else:
                # A non None new_mode means that the file existed when
                # the diff was made so a refresh will be required
                patch_ok = patch_ok and file_data.new_mode is None
            if os.path.exists(file_data.name) and patch_ok:
                file_data.timestamp = os.path.getmtime(file_data.name)
            else:
                file_data.timestamp = 0
            if not patch_ok:
                if result is None:
                    result = runext.Result(1, '', 'Needs update.\n')
                else:
                    result = runext.Result(max(result.ecode, 1), result.stdout, result.stderr + 'Needs update.\n')
            if result is not None:
                results[file_data.name] = result
            dump_db()
        return results
    def copy_refreshed_version_to(self, filename, target_name):
        file_data = self.files[filename]
        if not file_data.needs_refresh():
            if os.path.exists(bu_f_name):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(filename, target_name)
            return
        bu_f_name = self.get_backup_file_name(filename)
        if file_data.binary is not False:
            if os.path.exists(bu_f_name):
                utils.ensure_file_dir_exists(target_name)
                shutil.copy2(bu_f_name, target_name)
            return
        if os.path.exists(bu_f_name):
            utils.ensure_file_dir_exists(target_name)
            shutil.copy2(bu_f_name, target_name)
        elif file_data.diff:
            utils.ensure_file_dir_exists(target_name)
            with open(target_name, 'w') as fobj:
                fobj.write('')
        if file_data.diff:
            patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch', target_name]
            runext.run_cmd(patch_cmd, str(file_data.diff))
    def do_back_up_file(self, filename, force):
        '''Back up the named file for this patch'''
        # "force" argument is supplied to allow shortcutting SCM check
        # which can be expensive
        assert is_writable()
        assert filename in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filename) is None
        bu_f_name = self.get_backup_file_name(filename)
        olpatch = self.get_unrefreshed_overlapped_patch_for_file(filename) if not force else None
        if olpatch:
            olpatch.copy_refreshed_version_to(filename, bu_f_name)
            self.files[filename].timestamp = 0
        elif force and scm_ifce.has_uncommitted_change(filename):
            scm_ifce.copy_clean_version_to(filename, bu_f_name)
            self.files[filename].timestamp = 0
        elif os.path.exists(filename):
            # We'll try to preserve links when we pop patches
            # so we move the file to the backups directory and then make
            # a copy (without links) in the working directory
            utils.ensure_file_dir_exists(bu_f_name)
            shutil.move(filename, bu_f_name)
            shutil.copy2(bu_f_name, filename)
        if os.path.exists(bu_f_name):
            # We need this so that we need to reset it on pop
            old_mode = os.stat(bu_f_name).st_mode
            # Make the backup read only to prevent accidental change
            os.chmod(bu_f_name, utils.turn_off_write(old_mode))
            self.files[filename].old_mode = old_mode
        else:
            self.files[filename].old_mode = None
    def generate_diff_preamble_for_file(self, filename, combined=False):
        assert is_readable()
        assert filename in self.files
        file_data = self.files[filename]
        if self.is_applied():
            olp = None if combined else self.get_overlapping_patch_for_file(filename)
            if olp is not None:
                new_mode = olp.files[filename].old_mode
            else:
                new_mode = os.stat(filename).st_mode if os.path.exists(filename) else None
        else:
            new_mode = file_data.new_mode
        if file_data.old_mode is None:
            lines = ['diff --git /dev/null {0}\n'.format(os.path.join('a', filename)), ]
            if new_mode is not None:
                lines.append('new file mode {0:07o}\n'.format(new_mode))
        elif new_mode is None:
            lines = ['diff --git {0} /dev/null\n'.format(os.path.join('a', filename)), ]
            lines.append('deleted file mode {0:07o}\n'.format(file_data.old_mode))
        else:
            lines = ['diff --git {0} {1}\n'.format(os.path.join('a', filename), os.path.join('b', filename)), ]
            if file_data.old_mode != new_mode:
                lines.append('old mode {0:07o}\n'.format(file_data.old_mode))
                lines.append('new mode {0:07o}\n'.format(new_mode))
        return patchlib.Preamble.parse_lines(lines)
    def generate_diff_for_file(self, filename, combined=False):
        assert is_readable()
        assert filename in self.files
        assert self.is_applied()
        olp = None if combined else self.get_overlapping_patch_for_file(filename)
        to_file = filename if olp is None else olp.get_backup_file_name(filename)
        fm_file = self.get_backup_file_name(filename)
        fm_exists = os.path.exists(fm_file)
        if os.path.exists(to_file):
            to_name_label = os.path.join('b' if fm_exists else 'a', filename)
            to_time_stamp = _pts_for_path(to_file)
            with open(to_file) as fobj:
                to_contents = fobj.read()
        else:
            to_name_label = '/dev/null'
            to_time_stamp = _PTS_ZERO
            to_contents = ''
        if fm_exists:
            fm_name_label = os.path.join('a', filename)
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
    def get_diff_for_file(self, filename, combined=False):
        assert is_readable()
        assert filename in self.files
        preamble = self.generate_diff_preamble_for_file(filename, combined)
        diff = self.generate_diff_for_file(filename, combined) if self.is_applied() else self.files[filename].diff
        return patchlib.DiffPlus([preamble], diff)
    def do_refresh_file(self, filename):
        '''Refresh the named file in this patch'''
        assert is_writable()
        assert filename in self.files
        assert self.is_applied()
        assert self.get_overlapping_patch_for_file(filename) is None
        file_data = self.files[filename]
        # Do a check for unresolved merges here
        if file_data.has_unresolved_merges():
            # ensure this file shows up as needing refresh
            file_data.timestamp = -1
            dump_db()
            return runext.Result(3, '', 'File has unresolved merge(s).\n')
        f_exists = os.path.exists(filename)
        if f_exists or os.path.exists(self.get_backup_file_name(filename)):
            file_data.diff = self.generate_diff_for_file(filename)
            if f_exists:
                stat_data = os.stat(filename)
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
            file_data.scm_revision = scm_ifce.get_revision(filename=file_data.name)
            result = runext.Result(0, '', 'File "{0}" does not exist\n'.format(filename))
        dump_db()
        return result
    def do_unapply(self):
        '''Unapply this patch'''
        assert is_writable()
        assert self.is_applied()
        assert not self.needs_refresh()
        assert not self.is_overlapped()
        for file_data in self.files.values():
            if os.path.exists(file_data.name):
                os.remove(file_data.name)
            bu_f_name = self.get_backup_file_name(file_data.name)
            if os.path.exists(bu_f_name):
                os.chmod(bu_f_name, file_data.old_mode)
                shutil.move(bu_f_name, file_data.name)
        shutil.rmtree(self.get_backup_dir_name())
        return True
    def do_refresh(self):
        '''Refresh the patch'''
        assert is_writable()
        assert self.is_applied()
        results = {}
        for filename in self.files:
            results[filename] = self.do_refresh_file(filename)
        return results
    def get_backup_dir_name(self):
        '''Return the name of the backup directory for this patch'''
        return os.path.join(_BACKUPS_DIR, self.name)
    def get_backup_file_name(self, filename):
        '''Return the name of the backup directory for the named file in this patch'''
        return os.path.join(_BACKUPS_DIR, self.name, filename)
    def get_filenames(self, filenames=None):
        '''
        Return the names of the files in this patch.
        If filenames is not None restrict the returned list to names that
        are also in filenames.
        '''
        if filenames is None:
            return [filename for filename in self.files]
        else:
            return [filename for filename in self.files if filename in filenames]
    def get_file_names_set(self, filenames=None):
        '''Return the set of names for the files in this patch.
        If filenames is not None restrict the returned set to names that
        are also in filenames.
        '''
        return set(self.get_filenames(filenames=filenames))
    def get_files_table(self):
        is_applied = self.is_applied()
        if is_applied:
            table = []
            for fde in self.files.values():
                if (self.get_overlapping_patch_for_file(fde.name) is None) and fde.needs_refresh():
                    if fde.has_unresolved_merges():
                        validity = FileData.Validity.UNREFRESHABLE
                    else:
                        validity = FileData.Validity.NEEDS_REFRESH
                else:
                    validity = FileData.Validity.REFRESHED
                table.append(fsdb.Data(fde.name, FileData.Status(fde.get_presence(), validity), None))
        else:
            table = [fsdb.Data(fde.name, FileData.Status(fde.get_presence(), None), None) for fde in self.files.values()]
        return table
    def get_overlapping_patch_for_file(self, filename):
        '''Return the patch (if any) which overlaps the named file in this patch'''
        assert is_readable()
        assert self.is_applied()
        after = False
        for apatch in get_applied_patch_list():
            if after:
                if filename in apatch.files:
                    return apatch
            else:
                after = apatch.name == self.name
        return None
    def get_unrefreshed_overlapped_patch_for_file(self, filename):
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
            apfile = applied_patch.files.get(filename, None)
            if apfile is not None:
                return applied_patch if apfile.needs_refresh() else None
        return None
    def file_overlaps_uncommitted_or_unrefreshed(self, filename):
        '''
        Will this file overlap unrefreshed/uncommitted files?
        '''
        assert is_readable()
        if self.get_unrefreshed_overlapped_patch_for_file(filename) is not None:
            return True
        return scm_ifce.has_uncommitted_change(filename)
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
        return os.path.isdir(self.get_backup_dir_name())
    def is_blocked_by_guard(self):
        '''Is the this patch blocked from being applied by any guards?'''
        if (self.pos_guards & _DB.selected_guards) != self.pos_guards:
            return True
        if len(self.neg_guards & _DB.selected_guards) != 0:
            return True
        return False
    def is_overlapped(self):
        '''Are any files in this patch overlapped by applied patches?'''
        for filename in self.files:
            if self.get_overlapping_patch_for_file(filename) is not None:
                return True
        return False
    def is_pushable(self):
        '''Is this patch pushable?'''
        return not self.is_applied() and not self.is_blocked_by_guard()
    def needs_refresh(self):
        '''Does this patch need a refresh?'''
        for file_data in self.files.values():
            if self.get_overlapping_patch_for_file(file_data.name) is not None:
                continue
            if file_data.needs_refresh():
                return True
        return False
    def has_unresolved_merges(self):
        '''Is this patch refreshable? i.e. no unresolved merges'''
        for file_data in self.files.values():
            if self.get_overlapping_patch_for_file(file_data.name) is not None:
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
    def _do_insert_patch(self, patch, after=None):
        '''Insert given patch into series after the top or nominated patch'''
        assert is_writable()
        assert self.get_series_index(patch.name) is None
        assert after is None or self.get_series_index(after) is not None
        if after is not None:
            assert not is_applied(after) or is_top_applied_patch(after)
            index = self.get_series_index(after) + 1
        else:
            top_index = self.get_series_index_for_top()
            index = top_index + 1 if top_index is not None else 0
        self.series.insert(index, patch)
        dump_db()
    def do_create_new_patch(self, name, description):
        '''Create a new patch with the given name and description (after the top patch)'''
        assert is_writable()
        assert self.get_series_index(name) is None
        patch = PatchData(name, description)
        self._do_insert_patch(patch)
    def do_import_patch(self, epatch, name):
        '''Import an external patch with the given name (after the top patch)'''
        assert is_writable()
        assert self.get_series_index(name) is None
        descr = utils.make_utf8_compliant(epatch.get_description())
        patch = PatchData(name, descr)
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
        self._do_insert_patch(patch)
    def do_duplicate_patch(self, name, newname, newdescription):
        '''Create a duplicate of the named patch with a new name and new description (after the top patch)'''
        assert is_writable()
        assert self.get_series_index(newname) is None
        patch = self.get_patch(name)
        assert patch is not None and not patch.needs_refresh()
        newpatch = copy.deepcopy(patch)
        newpatch.name = newname
        newpatch.description = newdescription
        self._do_insert_patch(newpatch)
    def do_refresh_overlapped_files(self, file_list):
        '''Refresh the files in the list within the topmost applied patch of
        which they are a member'''
        assert is_writable()
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
    def do_remove_patch(self, name, keep=True):
        '''Remove the named patch from series and (optionally) keep it for later restoration'''
        assert is_writable()
        patch = self.get_patch(name)
        assert patch is not None
        assert not patch.is_applied()
        if keep:
            self.kept_patches[patch.name] = patch
        self.series.remove(patch)
        dump_db()
    def do_restore_patch(self, name, newname=None):
        '''Restore a previously removed patch to the series (after the top patch)'''
        assert is_writable()
        assert newname is None or self.get_series_index(newname) is None
        assert newname is not None or self.get_series_index(name) is None
        assert name in self.kept_patches
        patch = self.kept_patches[name]
        if newname is not None:
            patch.name = newname
        self._do_insert_patch(patch)
        del self.kept_patches[name]
        dump_db()
    def get_applied_patches(self):
        '''Get a list of applied patches in series order'''
        applied = list()
        applied_set = _get_applied_patch_names_set()
        if len(applied_set) == 0:
            return []
        for patch in self.series:
            if patch.name in applied_set:
                applied.append(patch)
                applied_set.remove(patch.name)
                if len(applied_set) == 0:
                    break
        assert len(applied_set) == 0, 'Series/applied patches discrepency'
        return applied
    def get_combined_patch_file_table(self):
        '''Get a table of file data for all applied patches'''
        class _Data(object):
            __slots__ = ['presence', 'validity', 'origin']
            def __init__(self, presence, validity, origin=None):
                self.presence = presence
                self.validity = validity
                self.origin = origin
        file_map = {}
        for patch in self.series:
            if not patch.is_applied():
                continue
            for fde in patch.files.values():
                if (patch.get_overlapping_patch_for_file(fde.name) is None) and fde.needs_refresh():
                    if fde.has_unresolved_merges():
                        validity = FileData.Validity.UNREFRESHABLE
                    else:
                        validity = FileData.Validity.NEEDS_REFRESH
                else:
                    validity = FileData.Validity.REFRESHED
                if fde.name in file_map:
                    file_map[fde.name].validity = validity
                else:
                    file_map[fde.name] = _Data(fde.get_presence(), validity)
        table = []
        for filename in sorted(file_map):
            data = file_map[filename]
            table.append(fsdb.Data(filename, FileData.Status(data.presence, data.validity), data.origin))
        return table
    def get_overlap_data(self, filenames, patchname=None):
        '''
        Get the data detailing unrefreshed/uncommitted files that will be
        overlapped by the named files
        '''
        assert is_readable()
        if not filenames:
            return OverlapData({}, set())
        applied_patches = get_applied_patch_list()
        if patchname is not None:
            try:
                patch = self.get_patch(patchname)
                patch_index = applied_patches.index(patch)
                applied_patches = applied_patches[:patch_index]
            except ValueError:
                pass
        uncommitted = set(scm_ifce.get_files_with_uncommitted_changes(filenames))
        remaining_files = set(filenames)
        unrefreshed = {}
        for applied_patch in reversed(applied_patches):
            if len(uncommitted) + len(remaining_files) == 0:
                break
            apfiles = applied_patch.get_filenames(remaining_files)
            if apfiles:
                apfiles_set = set(apfiles)
                remaining_files -= apfiles_set
                uncommitted -= apfiles_set
                for apfile in apfiles:
                    if applied_patch.files[apfile].needs_refresh():
                        unrefreshed[apfile] = applied_patch.name
        return OverlapData(unrefreshed, uncommitted)
    def get_patch(self, name):
        '''Get the patch with the given name'''
        patch_index = self.get_series_index(name)
        if patch_index is not None:
            return self.series[patch_index]
        else:
            return None
    def get_patch_table_data(self):
        return [patch.get_table_row() for patch in self.series]
    def get_series_index(self, name):
        '''Get the series index for the patch with the given name'''
        index = 0
        for patch in self.series:
            if patch.name == name:
                return index
            index += 1
        return None
    def get_series_index_for_next(self):
        '''Get the index of the next patch to be applied'''
        top = self.get_series_index_for_top()
        index = 0 if top is None else top + 1
        while index < len(self.series):
            if self.series[index].is_blocked_by_guard():
                index += 1
                continue
            return index
        return None
    def get_series_index_for_top(self):
        '''Get the index in series of the top applied patch'''
        applied_set = _get_applied_patch_names_set()
        if len(applied_set) == 0:
            return None
        index = 0
        for patch in self.series:
            if patch.name in applied_set:
                applied_set.remove(patch.name)
                if len(applied_set) == 0:
                    return index
            index += 1
        return None

_DB_DIR = '.darning.dbd'
_BACKUPS_DIR = os.path.join(_DB_DIR, 'backups')
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
        return Failure('%s: Unable to open' % _DB_LOCK_FILE)
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
        for dirnm in [_BACKUPS_DIR, _DB_DIR]:
            if os.path.exists(dirnm):
                os.rmdir(dirnm)
    if os.path.exists(_DB_DIR):
        if os.path.exists(_BACKUPS_DIR) and os.path.exists(_DB_FILE):
            return Failure('Database already exists')
        return Failure('Database directory exists')
    try:
        dir_mode = stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
        os.mkdir(_DB_DIR, dir_mode)
        os.mkdir(_BACKUPS_DIR, dir_mode)
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
        return Failure('Database is read only. Lock held by: {0}'.format(holder))
    return True

def dump_db():
    '''Dump in memory database to file'''
    assert is_writable()
    fobj = open(_DB_FILE, 'wb')
    try:
        cPickle.dump(_DB, fobj)
    finally:
        fobj.close()

def get_patch_series_names():
    '''Get a list of patch names in series order (names only)'''
    assert is_readable()
    return [patch.name for patch in _DB.series]

def _get_applied_patch_names_set():
    '''Get the set of applied patches' names'''
    def isdir(item):
        '''Is item a directory?'''
        return os.path.isdir(os.path.join(_BACKUPS_DIR, item))
    return set([item for item in os.listdir(_BACKUPS_DIR) if isdir(item)])

def get_applied_patch_name_list():
    '''Get an ordered list of applied patch names'''
    assert is_readable()
    return [patch.name for patch in _DB.get_applied_patches()]

def get_applied_patch_list():
    '''Get an ordered list of applied patches'''
    assert is_readable()
    return _DB.get_applied_patches()

def get_patch_series_index(name):
    '''Get the index in series for the patch with the given name'''
    assert is_readable()
    return _DB.get_series_index(name)

def get_patch_file_table(name):
    assert is_readable()
    if len(_DB.series) == 0:
        return []
    index = _DB.get_series_index(name)
    return _DB.series[index].get_files_table()

def get_combined_patch_file_table():
    assert is_readable()
    if len(_DB.series) == 0:
        return []
    return _DB.get_combined_patch_file_table()

def _get_top_patch_index():
    '''Get the index in series of the top applied patch'''
    assert is_readable()
    return _DB.get_series_index_for_top()

def patch_is_in_series(name):
    '''Is there a patch with the given name in the series?'''
    return get_patch_series_index(name) is not None

def is_applied(name):
    '''Is the named patch currently applied?'''
    return _DB.get_patch(name).is_applied()

def is_top_applied_patch(name):
    '''Is the named patch the top applied patch?'''
    top_index = _get_top_patch_index()
    if top_index is None:
        return False
    return _DB.series[top_index].name == name

def patch_needs_refresh(name):
    '''Does the named patch need to be refreshed?'''
    assert is_readable()
    assert get_patch_series_index(name) is not None
    return _DB.get_patch(name).needs_refresh()

def create_new_patch(name, description):
    '''Create a new patch with the given name and description (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(name) is None
    _DB.do_create_new_patch(name, description)

def import_patch(epatch, name):
    '''Import an external patch with the given name (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(name) is None
    _DB.do_import_patch(epatch, name)

def top_patch_needs_refresh():
    '''Does the top applied patch need a refresh?'''
    assert is_readable()
    top = _get_top_patch_index()
    if top is not None:
        return _DB.series[top].needs_refresh()
    return False

def _get_next_patch_index():
    '''Get the next patch to be applied'''
    assert is_readable()
    return _DB.get_series_index_for_next()

def get_patch_overlap_data(name):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the named patch's current files if filenames is None.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    return _DB.get_overlap_data(_DB.series[patch_index].get_filenames())

def get_file_diff(filename, patchname):
    assert is_readable()
    patch_index = get_patch_series_index(patchname)
    assert patch_index is not None
    return _DB.series[patch_index].get_diff_for_file(filename)

def get_file_combined_diff(filename):
    assert is_readable()
    patch = None
    for applied_patch in get_applied_patch_list():
        if filename in applied_patch.files:
            patch = applied_patch
            break
    assert patch is not None
    return patch.get_diff_for_file(filename, True)

def get_filelist_overlap_data(filenames, patchname=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the files in filelist if they are added to the named
    (or top, if None) patch.
    '''
    assert is_readable()
    assert patchname is None or get_patch_series_index(patchname) is not None
    return _DB.get_overlap_data(filenames, patchname)

def get_next_patch_overlap_data():
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the nextpatch
    '''
    assert is_readable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return OverlapData(unrefreshed = {}, uncommitted = [])
    return _DB.get_overlap_data(_DB.series[next_index].get_filenames())

def apply_patch(force=False):
    '''Apply the next patch in the series'''
    assert is_writable()
    next_index = _get_next_patch_index()
    if next_index is None:
        return (False, 'There are no pushable patches available')
    return (True, _DB.series[next_index].do_apply(force))

def get_top_applied_patch_for_file(filename):
    assert is_readable()
    applied_patches = get_applied_patch_list()
    for applied_patch in reversed(applied_patches):
        if filename in applied_patch.files:
            return applied_patch.name
    return None

def get_top_patch_name():
    '''Return the name of the top applied patch'''
    assert is_readable()
    top = _get_top_patch_index()
    return None if top is None else _DB.series[top].name

def is_blocked_by_guard(name):
    '''Is the named patch blocked from being applied by any guards?'''
    assert is_readable()
    assert get_patch_series_index(name) is not None
    return _DB.get_patch(name).is_blocked_by_guard()

def is_pushable():
    '''Is there a pushable patch?'''
    assert is_readable()
    return _get_next_patch_index() is not None

def is_patch_pushable(name):
    '''Is the named patch pushable?'''
    assert is_readable()
    return _DB.get_patch(name).is_pushable()

def unapply_top_patch():
    '''Unapply the top applied patch'''
    assert is_writable()
    assert not top_patch_needs_refresh()
    top_patch_index = _get_top_patch_index()
    assert top_patch_index is not None
    return _DB.series[top_patch_index].do_unapply()

def get_filenames_in_patch(name, filenames=None):
    '''
    Return the names of the files in the named patch.
    If filenames is not None restrict the returned list to names that
    are also in filenames.
    '''
    assert is_readable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    return _DB.series[patch_index].get_filenames(filenames)

def get_filenames_in_next_patch(filenames=None):
    '''
    Return the names of the files in the next patch (to be applied).
    If filenames is not None restrict the returned list to names that
    are also in filenames.
    '''
    assert is_readable()
    patch_index = _get_next_patch_index()
    assert patch_index is not None
    return _DB.series[patch_index].get_filenames(filenames)

def add_file_to_patch(name, filename, force=False):
    '''Add the named file to the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filename not in patch.files
    return patch.do_add_file(filename, force=force)

def do_drop_file_fm_patch(name, filename):
    '''Drop the named file from the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filename in patch.files
    return patch.do_drop_file(filename)

def do_refresh_overlapped_files(file_list):
    '''Refresh any files in the list which are in an applied patch
    (within the topmost such patch).'''
    assert is_writable()
    assert _get_top_patch_index() is not None
    return _DB.do_refresh_overlapped_files(file_list)

def do_refresh_patch(name):
    '''Refresh the named patch'''
    assert is_writable()
    assert is_applied(name)
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    return _DB.series[patch_index].do_refresh()

def do_set_patch_description(name, text):
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    _DB.series[patch_index].description = text if text is not None else ''
    dump_db()

def get_patch_description(name):
    assert is_readable()
    patch_index = get_patch_series_index(name)
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
    return _DB.get_patch_table_data()

def get_selected_guards():
    assert is_readable()
    return _DB.selected_guards

def get_patch_guards(name):
    assert is_readable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch_data = _DB.series[patch_index]
    return PatchData.Guards(positive=patch_data.pos_guards, negative=patch_data.neg_guards)

def do_set_patch_guards(name, guards):
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    _DB.series[patch_index].pos_guards = set(guards.positive)
    _DB.series[patch_index].neg_guards = set(guards.negative)
    dump_db()

def do_select_guards(guards):
    assert is_writable()
    _DB.selected_guards = set(guards)
    dump_db()

def get_extdiff_files_for(filename, patchname):
    assert is_readable()
    assert is_applied(patchname)
    patch =  _DB.series[get_patch_series_index(patchname)]
    assert filename in patch.files
    assert patch.get_overlapping_patch_for_file(filename) is None
    orig = patch.get_backup_file_name(filename)
    return _O_IP_PAIR(original_version=orig, patched_version=filename)


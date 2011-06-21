from darning import patchlib
from darning import fsdb
class FileData:
    class Presence(object):
        ADDED = patchlib.FilePathPlus.ADDED
        REMOVED = patchlib.FilePathPlus.DELETED
        EXTANT = patchlib.FilePathPlus.EXTANT
    class Validity(object):
        REFRESHED, NEEDS_REFRESH, UNREFRESHABLE = range(3)
    Status = collections.namedtuple('Status', ['presence', 'validity'])
                if FileData.MERGE_CRE.match(line):
    def get_presence(self):
        if self.old_mode is None:
            return FileData.Presence.ADDED
        elif self.new_mode is None:
            return FileData.Presence.DELETED
        else:
            return FileData.Presence.EXTANT
class PatchData:
            self.files[filename] = FileData(filename)
        assert not self.file_overlaps_uncommitted_or_unrefreshed(filename)
        self.files[filename] = FileData(filename)
            overlapping_bu_f_name = overlapped_by.get_backup_file_name(filename)
            if os.path.exists(overlapping_bu_f_name):
                os.link(overlapping_bu_f_name, self.get_backup_file_name(filename))
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
        assert _total_overlap_count(get_patch_overlap_data(self.name)) == 0
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
    def file_overlaps_uncommitted_or_unrefreshed(self, filename):
        overlapped by this file in this patch
        for applied_patch in reversed(applied_patches):
            apfile = applied_patch.files.get(filename, None)
            if apfile is not None:
                return apfile.needs_refresh()
        return scm_ifce.has_uncommitted_change(filename)
            if self.has_unresolved_merges():
                state = PatchState.APPLIED_UNFEFRESHABLE
            else:
                state = PatchState.APPLIED_NEEDS_REFRESH
            if self.get_overlapping_patch_for_file(file_data.name) is not None:
                continue
    def has_unresolved_merges(self):
        '''Is this patch refreshable? i.e. no unresolved merges'''
        for file_data in self.files.values():
            if self.get_overlapping_patch_for_file(file_data.name) is not None:
                continue
            if file_data.has_unresolved_merges():
                return True
        return False
class DataBase:
        patch = PatchData(name, description)
        patch = PatchData(name, descr)
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
        db_obj = DataBase(description, None)
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

def get_patch_overlap_data(name):
    overlapped by the named patch's current files if filenames is None.
    return _DB.get_overlap_data(_DB.series[patch_index].get_filenames())

def get_filelist_overlap_data(filenames, patchname=None):
    '''
    Get the data detailing unrefreshed/uncommitted files that will be
    overlapped by the files in filelist if they are added to the named
    (or top, if None) patch.
    '''
    assert is_readable()
    assert patchname is None or get_patch_series_index(patchname) is not None
    return _DB.get_overlap_data(filenames, patchname)
    return _DB.get_overlap_data(_DB.series[next_index].get_filenames())
def do_drop_file_fm_patch(name, filename):
    '''Drop the named file from the named patch'''
    assert is_writable()
    patch_index = get_patch_series_index(name)
    assert patch_index is not None
    patch = _DB.series[patch_index]
    assert filename in patch.files
    return patch.do_drop_file(filename)

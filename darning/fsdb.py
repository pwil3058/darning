### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import collections
import os
import hashlib

class Relation(object):
    COPIED_FROM = '<<-'
    RENAMED_FROM = '<-'
    RENAMED_TO = '->'

RFD = collections.namedtuple('RFD', ['path', 'relation'])
Data = collections.namedtuple('Data', ['name', 'status', 'related_file'])
Deco = collections.namedtuple('Deco', ['style', 'foreground'])

def split_path(path):
    if os.path.isabs(path):
        path = os.path.relpath(path)
    parts = []
    while path:
        path, tail = os.path.split(path)
        parts.insert(0, tail)
    return parts

class NullFileDb:
    def __init__(self):
        pass
    def dir_contents(self, dirpath, show_hidden=False):
        return ([], [])

class OsFileDb:
    def __init__(self):
        pass
    def _is_not_hidden_file(self, filepath):
        return filepath[0] != '.'
    def dir_contents(self, dirpath, show_hidden=False):
        files = []
        dirs = []
        if not dirpath:
            dirpath = os.curdir
        elements = os.listdir(dirpath)
        for element in elements:
            if os.path.isdir(os.path.join(dirpath, element)):
                if self._is_not_hidden_file(element) or show_hidden:
                    dirs.append(Data(element, None, None))
            elif self._is_not_hidden_file(element) or show_hidden:
                files.append(Data(element, None, None))
        dirs.sort()
        files.sort()
        return (dirs, files)

class GenDir:
    def __init__(self):
        self.status = None
        self.status_set = set()
        self.subdirs = {}
        self.files = {}
    def _new_dir(self):
        return GenDir()
    def add_file(self, path_parts, status, related_file=None):
        self.status_set.add(status)
        name = path_parts[0]
        if len(path_parts) == 1:
            self.files[name] = Data(name=name, status=status, related_file=related_file)
        else:
            if name not in self.subdirs:
                self.subdirs[name] = self._new_dir()
            self.subdirs[name].add_file(path_parts[1:], status, related_file)
    def _update_own_status(self):
        if len(self.status_set) > 0:
            self.status = self.status_set.pop()
            self.status_set.add(self.status)
        else:
            self.status = None
    def update_status(self):
        self._update_own_status()
        for key in list(self.subdirs.keys()):
            self.subdirs[key].update_status()
    def _find_dir(self, dirpath_parts):
        if not dirpath_parts:
            return self
        elif dirpath_parts[0] in self.subdirs:
            return self.subdirs[dirpath_parts[0]]._find_dir(dirpath_parts[1:])
        else:
            return None
    def find_dir(self, dirpath):
        if not dirpath:
            return self
        return self._find_dir(split_path(dirpath))
    def _is_hidden_dir(self, dkey):
        return dkey[0] == '.'
    def _is_hidden_file(self, fdata):
        return fdata.name[0] == '.'
    def dirs_and_files(self, show_hidden=False):
        dkeys = list(self.subdirs.keys())
        dkeys.sort()
        dirs = []
        for dkey in dkeys:
            if not show_hidden and self._is_hidden_dir(dkey):
                continue
            dirs.append(Data(name=dkey, status=self.subdirs[dkey].status, related_file=None))
        files = []
        fkeys = list(self.files.keys())
        fkeys.sort()
        for fkey in fkeys:
            fdata = self.files[fkey]
            if not show_hidden and self._is_hidden_file(fdata):
                continue
            files.append(fdata)
        return (dirs, files)

class GenFileDb:
    DIR_TYPE = GenDir
    def __init__(self):
        self.base_dir = self.DIR_TYPE()
    def _set_contents(self, file_list, unresolved_file_list=list()):
        for item in file_list:
            self.base_dir.add_file(split_path(item), status=None, related_file=None)
    def add_file(self, filepath, status, related_file=None):
        self.base_dir.add_file(split_path(filepath), status, related_file)
    def decorate_dirs(self):
        self.base_dir.update_status()
    def dir_contents(self, dirpath='', show_hidden=False):
        tdir = self.base_dir.find_dir(dirpath)
        if not tdir:
            return ([], [])
        return tdir.dirs_and_files(show_hidden)

class OsSnapshotFileDb:
    DIR_TYPE = GenDir
    def __init__(self, default_status=None):
        self.tree_hash = hashlib.sha1()
        self.base_dir = self.DIR_TYPE()
        for root, dirs, files in os.walk('.'):
            self.tree_hash.update(root)
            rparts = split_path(root)[1:] # get rid of the leading './'
            dir_data = self.base_dir._find_dir(rparts)
            for d in dirs:
                dir_data.subdirs[d] = self.DIR_TYPE()
            for f in files:
                self.tree_hash.update(f)
                dir_data.files[f] = Data(f, default_status, None)
    def dir_contents(self, dirpath='', show_hidden=False):
        tdir = self.base_dir.find_dir(dirpath)
        if not tdir:
            return ([], [])
        return tdir.dirs_and_files(show_hidden)
    def _get_current_tree_hash(self):
        h = hashlib.sha1()
        for root, dirs, files in os.walk('.'):
            h.update(root)
            for f in files:
                h.update(f)
        return h
    def is_current(self):
        h = self._get_current_tree_hash()
        return h.digest() == self.tree_hash.digest()

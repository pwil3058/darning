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
Utility functions
'''

import stat
import os

from darning import urlops

HOME = os.path.expanduser("~")

def path_rel_home(path):
    """Return the given path as a path relative to user's home directory."""
    if urlops.parse_url(path).scheme:
        return path
    path = os.path.abspath(path)
    len_home = len(HOME)
    if len(path) >= len_home and HOME == path[:len_home]:
        path = "~" + path[len_home:]
    return path

def file_list_to_string(file_list):
    """Return the given list of file names as a single string:
    - using a single space as a separator, and
    - placing double quotes around file names that contain spaces.
    """
    mod_file_list = []
    for fname in file_list:
        if fname.count(' ') == 0:
            mod_file_list.append(fname)
        else:
            mod_file_list.append('"%s"' % fname)
    return ' '.join(mod_file_list)

# handle the fact os.path.samefile is not available on all operating systems
def samefile(filename1, filename2):
    """Return whether the given paths refer to the same file or not."""
    try:
        return os.path.samefile(filename1, filename2)
    except AttributeError:
        return os.path.abspath(filename1) == os.path.abspath(filename2)

def get_first_in_envar(envar_list):
    for envar in envar_list:
        try:
            value = os.environ[envar]
            if value != '':
                return value
        except KeyError:
            continue
    return ''

def turn_off_write(mode):
    '''Return the given mode with the write bits turned off'''
    return mode & ~(stat.S_IWUSR|stat.S_IWGRP|stat.S_IWOTH)

def is_utf8_compliant(text):
    try:
        _ = text.decode('utf-8')
    except UnicodeError:
        return False
    return True

ISO_8859_CODECS = ['iso-8859-{0}'.format(x) for x in range(1, 17)]
ISO_2022_CODECS = ['iso-2022-jp', 'iso-2022-kr'] + \
    ['iso-2022-jp-{0}'.format(x) for x in range(1, 3) + ['2004', 'ext']]

def make_utf8_compliant(text):
    '''Return a UTF-8 compliant version of text'''
    if is_utf8_compliant(text):
        return text
    for codec in ISO_8859_CODECS + ISO_2022_CODECS:
        try:
            text = unicode(text, codec).encode('utf-8')
            return text
        except UnicodeError:
            continue
    raise UnicodeError

def files_in_dir(dirname, recurse=True, relative=False):
    '''Return a list of the files in the given directory.'''
    if recurse:
        def onerror(exception):
            raise exception
        files = []
        for basedir, dirnames, filenames in os.walk(dirname, onerror=onerror):
            if relative:
                basedir = '' if basedir == dirname else os.path.relpath(basedir, dirname)
            files += [os.path.join(basedir, entry) for entry in filenames]
        return files
    elif relative:
        return [entry for entry in os.listdir(dirname) if not os.path.isdir(entry)]
    else:
        return [os.path.join(dirname, entry) for entry in os.listdir(dirname) if not os.path.isdir(entry)]

def ensure_file_dir_exists(filename):
    file_dir = os.path.dirname(filename)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

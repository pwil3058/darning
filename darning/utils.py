### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>
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
import os.path
import subprocess
import gobject
import signal
import zlib
import gzip
import bz2
import re
import hashlib

# TODO: purify utils (i.e. minimize . imports)

from .cmd_result import CmdResult
from .config_data import HOME

from . import urlops
from . import options

def singleton(aClass):
    def onCall(*args, **kwargs):
        if onCall.instance is None:
            onCall.instance = aClass(*args, **kwargs)
        return onCall.instance
    onCall.instance = None
    return onCall

def create_flag_generator():
    """
    Create a new flag generator
    """
    next_flag_num = 0
    while True:
        yield 2 ** next_flag_num
        next_flag_num += 1

def path_relative_to_dir(fdir, path):
    if not os.path.isdir(fdir):
        return None
    if fdir == path:
        return os.curdir
    lcwd = len(fdir)
    if len(path) <= lcwd + 1 or fdir != path[0:lcwd] or path[lcwd] != os.sep:
        return None
    return path[lcwd + 1:]

def path_relative_to_playground(path):
    return path_relative_to_dir(os.getcwd(), os.path.abspath(path))

def path_rel_home(path):
    """Return the given path as a path relative to user's home directory."""
    pr = urlops.parse_url(path)
    if pr.scheme and pr.scheme != "file":
        return path
    path = os.path.abspath(pr.path)
    len_home = len(HOME)
    if len(path) >= len_home and HOME == path[:len_home]:
        path = "~" + path[len_home:]
    return path

def cwd_rel_home():
    """Return path of current working directory relative to user's home
    directory.
    """
    return path_rel_home(os.getcwd())

quote_if_needed = lambda string: string if string.count(" ") == 0 else "\"" + string + "\""

quoted_join = lambda strings, joint=" ": joint.join((quote_if_needed(file_path) for file_path in strings))

def strings_to_quoted_list_string(strings):
    if len(strings) == 1:
        return quote_if_needed(strings[0])
    return quoted_join(strings[:-1], ", ") + _(" and ") + quote_if_needed(strings[-1])

# handle the fact os.path.samefile is not available on all operating systems
def samefile(filepath1, filepath2):
    """Return whether the given paths refer to the same file or not."""
    try:
        return os.path.samefile(filepath1, filepath2)
    except AttributeError:
        return os.path.abspath(filepath1) == os.path.abspath(filepath2)

if os.name == 'nt' or os.name == 'dos':
    def _which(cmd):
        """Return the path of the executable for the given command"""
        for dirpath in os.environ['PATH'].split(os.pathsep):
            potential_path = os.path.join(dirpath, cmd)
            if os.path.isfile(potential_path) and \
               os.access(potential_path, os.X_OK):
                return potential_path
        return None


    NT_EXTS = ['.bat', '.bin', '.exe']


    def which(cmd):
        """Return the path of the executable for the given command"""
        path = _which(cmd)
        if path:
            return path
        _, ext = os.path.splitext(cmd)
        if ext in NT_EXTS:
            return None
        for ext in NT_EXTS:
            path = _which(cmd + ext)
            if path is not None:
                return path
        return None
else:
    def which(cmd):
        """Return the path of the executable for the given command"""
        for dirpath in os.environ['PATH'].split(os.pathsep):
            potential_path = os.path.join(dirpath, cmd)
            if os.path.isfile(potential_path) and \
               os.access(potential_path, os.X_OK):
                return potential_path
        return None

def get_file_contents(srcfile, decompress=True):
    '''
    Get the contents of filename to text after (optionally) applying
    decompression as indicated by filename's suffix.
    '''
    if decompress:
        from . import runext
        _root, ext = os.path.splitext(srcfile)
        res = 0
        if ext == '.gz':
            return gzip.open(srcfile).read()
        elif ext == '.bz2':
            bz2f = bz2.BZ2File(srcfile, 'r')
            text = bz2f.read()
            bz2f.close()
            return text
        elif ext == '.xz':
            res, text, serr = runext.run_cmd(["xz", "-cd", srcfile])
        elif ext == '.lzma':
            res, text, serr = runext.run_cmd(["lzma", "-cd", srcfile])
        else:
            return open(srcfile).read()
        if res != 0:
            sys.stderr.write(serr)
        return text
    else:
        return open(srcfile).read()

def set_file_contents(filename, text, compress=True):
    '''
    Set the contents of filename to text after (optionally) applying
    compression as indicated by filename's suffix.
    '''
    if compress:
        _root, ext = os.path.splitext(filename)
        res = 0
        if ext == '.gz':
            try:
                gzip.open(filename, 'wb').write(text)
                return True
            except (IOError, zlib.error):
                return False
        elif ext == '.bz2':
            try:
                bz2f = bz2.BZ2File(filename, 'w')
                text = bz2f.write(text)
                bz2f.close()
                return True
            except IOError:
                return False
        elif ext == '.xz':
            res, text, serr = run_cmd('xz -c', text)
        elif ext == '.lzma':
            res, text, serr = run_cmd('lzma -c', text)
        if res != 0:
            sys.stderr.write(serr)
            return False
    try:
        open(filename, 'w').write(text)
    except IOError as edata:
        return CmdResult.error(stderr=str(edata))
    return CmdResult.ok()

def get_first_in_envar(envar_list, default=""):
    for envar in envar_list:
        try:
            value = os.environ[envar]
            if value != '':
                return value
        except KeyError:
            continue
    return default

def turn_off_write(mode):
    '''Return the given mode with the write bits turned off'''
    return mode & ~(stat.S_IWUSR|stat.S_IWGRP|stat.S_IWOTH)

def get_mode_for_file(filepath):
    try:
        return os.stat(filepath).st_mode
    except OSError:
        return None

def do_turn_off_write_for_file(filepath):
    '''Turn off write bits for name file and return original mode'''
    mode = get_mode_for_file(filepath)
    os.chmod(filepath, turn_off_write(mode))
    return mode

def is_utf8_compliant(text):
    try:
        _dummy= text.decode('utf-8')
    except UnicodeError:
        return False
    return True

ISO_8859_CODECS = ['iso-8859-{0}'.format(x) for x in range(1, 17)]
ISO_2022_CODECS = ['iso-2022-jp', 'iso-2022-kr'] + \
    ['iso-2022-jp-{0}'.format(x) for x in range(1, 3) + ['2004', 'ext']]

def make_utf8_compliant(text):
    '''Return a UTF-8 compliant version of text'''
    if text is None:
        return ''
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
        for basedir, dirnames, filepaths in os.walk(dirname, onerror=onerror):
            if relative:
                basedir = '' if basedir == dirname else os.path.relpath(basedir, dirname)
            files += [os.path.join(basedir, entry) for entry in filepaths]
        return files
    elif relative:
        return [entry for entry in os.listdir(dirname) if not os.path.isdir(entry)]
    else:
        return [os.path.join(dirname, entry) for entry in os.listdir(dirname) if not os.path.isdir(entry)]

def ensure_file_dir_exists(filepath):
    file_dir = os.path.dirname(filepath)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

def convert_patchname_to_filename(patchname):
    repl = options.get('export', 'replace_spc_in_name_with')
    if isinstance(repl, str):
        return re.sub('(\s+)', repl, patchname.strip())
    else:
        return patchname

_VALID_DIR_NAME_CRE = re.compile('^[ \w.-]+$')
ALLOWED_DIR_NAME_CHARS_MSG = _('Only alphanumeric characters plus " ", "_", "-" and "." are allowed.')

def is_valid_dir_name(dirname):
    return _VALID_DIR_NAME_CRE.match(dirname) is not None

def get_sha1_for_file(filepath):
    if os.path.isfile(filepath):
        return hashlib.sha1(open(filepath).read()).hexdigest()
    return None

def get_digest_for_file_list(file_list):
    h = hashlib.sha1()
    for filepath in file_list:
        if os.path.isfile(filepath):
            h.update(open(filepath).read())
    return h.digest()

def get_git_hash_for_content(content):
    h = hashlib.sha1('blob {0}\000'.format(len(content)))
    h.update(content)
    return h.hexdigest()

def get_git_hash_for_file(filepath):
    if os.path.isfile(filepath):
        h = hashlib.sha1('blob {0}\000'.format(os.path.getsize(filepath)))
        h.update(open(filepath).read())
        return h.hexdigest()
    return None

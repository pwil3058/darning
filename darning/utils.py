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

from .cmd_result import CmdResult
from .config_data import HOME

from . import urlops
from . import options

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
            mod_file_list.append("\"{0}\"".format(fname))
    return ' '.join(mod_file_list)

# handle the fact os.path.samefile is not available on all operating systems
def samefile(filepath1, filepath2):
    """Return whether the given paths refer to the same file or not."""
    try:
        return os.path.samefile(filepath1, filepath2)
    except AttributeError:
        return os.path.abspath(filepath1) == os.path.abspath(filepath2)

def create_file(name, console=None):
    """Attempt to create a file with the given name and report the outcome as
    a CmdResult tuple.
    1. If console is not None print report of successful creation on it.
    2. If a file with same name already exists fail and report a warning.
    3. If file creation fails for other reasons report an error.
    """
    if not os.path.exists(name):
        try:
            if console:
                console.start_cmd("create \"{0}\"".format(name))
            open(name, 'w').close()
            if console:
                console.end_cmd()
            ws_event.notify_events(ws_event.FILE_ADD)
            return CmdResult.ok()
        except (IOError, OSError) as msg:
            return CmdResult.error(stderr="\"{0}\": {1}".format(name, msg))
    else:
        return CmdResult.warning(stderr=_("\"{0}\": file already exists").format(name))

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
    except IOError:
        return False
    return True

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

def get_git_hash_for_file(filepath):
    if os.path.isfile(filepath):
        hash = hashlib.sha1('blob {0}\000'.format(os.path.getsize(filepath)))
        hash.update(open(filepath).read())
        return hash.hexdigest()
    return None

def os_move_or_copy_file(file_path, dest, opsym, force=False, dry_run=False, extra_checks=None, verbose=False):
    assert opsym in (fsdb.Relation.MOVED_TO, fsdb.Relation.COPIED_TO), _("Invalid operation requested")
    if os.path.isdir(dest):
        dest = os.path.join(dest, os.path.basename(file_path))
    omsg = "{0} {1} {2}.".format(file_path, opsym, dest) if verbose else ""
    if dry_run:
        if os.path.exists(dest):
            return CmdResult.error(omsg, _('File "{0}" already exists. Select "force" to overwrite.').format(dest)) + CmdResult.SUGGEST_FORCE
        else:
            return CmdResult.ok(omsg)
    from . import console
    console.LOG.start_cmd("{0} {1} {2}\n".format(file_path, opsym, dest))
    if not force and os.path.exists(dest):
        emsg = _('File "{0}" already exists. Select "force" to overwrite.').format(dest)
        result = CmdResult.error(omsg, emsg) + CmdResult.SUGGEST_FORCE
        console.LOG.end_cmd(result)
        return result
    if extra_checks:
        result = extra_check([(file_path, dest)])
        if not result.is_ok:
            console.LOG.end_cmd(result)
            return result
    try:
        if opsym is fsdb.Relation.MOVED_TO:
            os.rename(file_path, dest)
        elif opsym is fsdb.Relation.COPIED_TO:
            shutil.copy(file_path, dest)
        result = CmdResult.ok(omsg)
    except (IOError, os.error, shutil.Error) as why:
        result = CmdResult.error(omsg, _("\"{0}\" {1} \"{2}\" failed. {3}.\n").format(file_path, opsym, dest, str(why)))
    console.LOG.end_cmd(result)
    ws_event.notify_events(ws_event.FILE_ADD|ws_event.FILE_DEL)
    return result

def os_move_or_copy_files(file_path_list, dest, opsym, force=False, dry_run=False, extra_checks=None, verbose=False):
    assert opsym in (fsdb.Relation.MOVED_TO, fsdb.Relation.COPIED_TO), _("Invalid operation requested")
    def _overwrite_msg(overwrites):
        if len(overwrites) == 0:
            return ""
        elif len(overwrites) > 1:
            return _("Files:\n\t{0}\nalready exist. Select \"force\" to overwrite.").format("\n\t".join(["\"" + fp + "\"" for fp in overwrites]))
        else:
            return _("File \"{0}\" already exists. Select \"force\" to overwrite.").format(overwrites[0])
    if len(file_path_list) == 1:
        return os_move_or_copy_file(file_path_list[0], dest, opsym, force=force, dry_run=dry_run, extra_checks=extra_checks)
    from . import console
    if not dry_run:
        console.LOG.start_cmd("{0} {1} {2}\n".format(file_list_to_string(file_path_list), opsym, dest))
    if not os.path.isdir(dest):
        result = CmdResult.error(stderr=_('"{0}": Destination must be a directory for multifile rename.').format(dest))
        if not dry_run:
            console.LOG.end_cmd(result)
        return result
    opn_paths_list = [(file_path, os.path.join(dest, os.path.basename(file_path))) for file_path in file_path_list]
    omsg = "\n".join(["{0} {1} {2}.".format(src, opsym, dest) for (src, dest) in opn_paths_list]) if verbose else ""
    if dry_run:
        overwrites = [dest for (src, dest) in opn_paths_list if os.path.exists(dest)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            return CmdResult.error(omsg, emsg) + CmdResult.SUGGEST_FORCE
        else:
            return CmdResult.ok(omsg)
    if not force:
        overwrites = [dest for (src, dest) in opn_paths_list if os.path.exists(dest)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            result = CmdResult.error(omsg, emsg) + CmdResult.SUGGEST_FORCE
            console.LOG.end_cmd(result)
            return result
    if extra_checks:
        result = extra_check(opn_paths_list)
        if not result.is_ok:
            console.LOG.end_cmd(result)
            return result
    failed_opns_str = ""
    for (src, dest) in opn_paths_list:
        if verbose:
            console.LOG.append_stdout("{0} {1} {2}.".format(src, opsym, dest))
        try:
            if opsym is fsdb.Relation.MOVED_TO:
                os.rename(src, dest)
            elif opsym is fsdb.Relation.COPIED_TO:
                if os.path.isdir(src):
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
        except (IOError, os.error, shutil.Error) as why:
            serr = _('"{0}" {1} "{2}" failed. {3}.\n').format(src, opsym, dest, str(why))
            console.LOG.append_stderr(serr)
            failed_opns_str += serr
            continue
    console.LOG.end_cmd()
    ws_event.notify_events(ws_event.FILE_ADD|ws_event.FILE_DEL)
    if failed_opns_str:
        return CmdResult.error(omsg, failed_opns_str)
    return CmdResult.ok(omsg)

def os_copy_file(file_path, dest, force=False, dry_run=False):
    return os_move_or_copy_file(file_path, dest, opsym=fsdb.Relation.COPIED_TO, force=force, dry_run=dry_run)

def os_copy_files(file_path_list, dest, force=False, dry_run=False):
    return os_move_or_copy_files(file_path_list, dest, opsym=fsdb.Relation.COPIED_TO, force=force, dry_run=dry_run)

def os_move_file(file_path, dest, force=False, dry_run=False):
    return os_move_or_copy_file(file_path, dest, opsym=fsdb.Relation.MOVED_TO, force=force, dry_run=dry_run)

def os_move_files(file_path_list, dest, force=False, dry_run=False):
    return os_move_or_copy_files(file_path_list, dest, opsym=fsdb.Relation.MOVED_TO, force=force, dry_run=dry_run)

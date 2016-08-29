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

import os
import shutil
import errno

from .cmd_result import CmdResult

from . import enotify

E_FILE_ADDED, E_FILE_DELETED, E_FILE_CHANGES = enotify.new_event_flags_and_mask(2)
E_FILE_MOVED = E_FILE_ADDED | E_FILE_DELETED

class Relation:
    COPIED_FROM = '<<-'
    COPIED_TO = '->>'
    MOVED_FROM = '<-'
    MOVED_TO = '->'

class _DummyLog:
    def start_cmd(self, *args, **kwargs): pass
    def end_cmd(self, *args, **kwargs): pass
    def append_stdout(self, *args, **kwargs): pass
    def append_stderr(self, *args, **kwargs): pass

_CONSOLE_LOG = _DummyLog()
def set_console_log(console_log):
    global _CONSOLE_LOG
    _CONSOLE_LOG = console_log if console_log else _DummyLog()

def get_destn_file_paths(file_paths, destn):
    if len(file_paths) == 1 and not os.path.isdir(destn):
        return [destn]
    else:
        return [os.path.join(destn, os.path.basename(file_path)) for file_path in file_paths]

def check_for_overwrites(destn_file_paths):
    from . import utils
    overwritten = [file_path for file_path in destn_file_paths if os.path.exists(file_path)]
    if overwritten:
        stderr = _("File(s):\n")
        for file_path in overwritten:
            stderr += "\t{0}\n".format(utils.quote_if_needed(file_path))
        return CmdResult.error(stderr=stderr + _("will be overwritten!\n")) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
    return CmdResult.ok()

def os_create_dir(dir_path):
    _CONSOLE_LOG.start_cmd("mkdir -p " + dir_path)
    try:
        os.makedirs(dir_path)
        result = CmdResult.ok()
    except OSError as edata:
        result = CmdResult.error(str(edata))
    _CONSOLE_LOG.end_cmd(result)
    return result

def os_create_file(file_path):
    """Attempt to create a file with the given file_path and report the outcome as
    a CmdResult tuple.
    1. If console is not None print report of successful creation on it.
    2. If a file with same file_path already exists fail and report a warning.
    3. If file creation fails for other reasons report an error.
    """
    _CONSOLE_LOG.start_cmd("create \"{0}\"".format(file_path))
    if not os.path.exists(file_path):
        try:
            open(file_path, 'w').close()
            enotify.notify_events(E_FILE_ADDED)
            result = CmdResult.ok()
        except (IOError, OSError) as msg:
            result = CmdResult.error(stderr="\"{0}\": {1}".format(file_path, msg))
    else:
        result = CmdResult.warning(stderr=_("\"{0}\": file already exists").format(file_path))
    _CONSOLE_LOG.end_cmd(result)
    return result

def os_delete_fs_items(fsi_paths, events=E_FILE_DELETED, force=False):
    from . import utils
    _CONSOLE_LOG.start_cmd(_('delete {0}').format(utils.quoted_join(fsi_paths)))
    serr = ""
    errorcode = CmdResult.ERROR
    for fsi_path in fsi_paths:
        try:
            if os.path.isdir(fsi_path) and not os.path.islink(fsi_path):
                if force:
                    shutil.rmtree(fsi_path)
                else:
                    os.removedirs(fsi_path)
            else:
                os.remove(fsi_path)
            _CONSOLE_LOG.append_stdout(_('Deleted: {0}\n').format(fsi_path))
        except OSError as edata:
            if edata.errno == errno.ENOTEMPTY:
                errorcode = CmdResult.ERROR_SUGGEST_FORCE
            errmsg = _("Error: {}: \"{}\"\n").format(edata.strerror, fsi_path)
            serr += errmsg
            _CONSOLE_LOG.append_stderr(errmsg)
    _CONSOLE_LOG.end_cmd()
    enotify.notify_events(events)
    return CmdResult(errorcode, "", serr)  if serr else CmdResult.ok()

def os_move_or_copy_fs_item(fsi_path, destn, opsym, overwrite=False, force=False, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    new_path = os.path.join(destn, os.path.basename(fsi_path)) if destn.endswith(os.sep) else destn
    omsg = "{0} {1} {2}.".format(fsi_path, opsym, new_path) if verbose else ""
    _CONSOLE_LOG.start_cmd("{0} {1} {2}\n".format(fsi_path, opsym, new_path))
    if os.path.exists(new_path):
        if not overwrite:
            emsg = _("{0} \"{1}\" already exists.").format(_("Directory") if os.path.isdir(new_path) else _("File"), new_path)
            result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
            _CONSOLE_LOG.end_cmd(result)
            return result
        try:
            if os.path.isdir(new_path) and not os.path.islink(new_path):
                if force:
                    shutil.rmtree(new_path)
                else:
                    os.removedirs(new_path)
            else:
                os.remove(new_path)
        except OSError as edata:
            errorcode = CmdResult.ERROR_SUGGEST_FORCE if edata.errno == errno.ENOTEMPTY else CmdResult.ERROR
            errmsg = _("Error: {}: \"{}\" {} \"{}\"\n").format(edata.strerror, fsi_path, opsym, new_path)
            _CONSOLE_LOG.append_stderr(errmsg)
            return CmdResult(errorcode, "", errmsg)
        except shutil.Error as edata:
            serr = _("Error: \"{0}\" {1} \"{2}\" failed.\n").format(fsi_path, opsym, new_path)
            for src_path, dest_path, reason in edata.args:
                serr += _("Error: \"{0}\" {1} \"{2}\": {3}.\n").format(src_path, opsym, dest_path, reason)
            return CmdResult.error(omsg, serr)
    try:
        if opsym is Relation.MOVED_TO:
            os.rename(fsi_path, new_path)
        elif os.path.isdir(fsi_path):
            shutil.copytree(fsi_path, new_path)
        else:
            shutil.copy2(fsi_path, new_path)
        result = CmdResult.ok(omsg)
    except OSError as edata:
        result = CmdResult.error(omsg, _("Error: \"{0}\" {1} \"{2}\" failed. {3}.\n").format(fsi_path, opsym, new_path, edata.strerror))
    except shutil.Error as edata:
        serr = _("Error: \"{0}\" {1} \"{2}\" failed.\n").format(fsi_path, opsym, new_path)
        for src_path, dest_path, reason in edata.args:
            serr += _("Error: \"{0}\" {1} \"{2}\": {3}.\n").format(src_path, opsym, dest_path, reason)
        result = CmdResult.error(omsg, serr)
    _CONSOLE_LOG.end_cmd(result)
    enotify.notify_events(E_FILE_MOVED)
    return result

def os_move_or_copy_fs_items(fsi_paths, destn, opsym, overwrite=False, force=False, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    assert len(fsi_paths) > 1
    from . import utils
    def _overwrite_msg(overwrites):
        if len(overwrites) == 0:
            return ""
        elif len(overwrites) > 1:
            return _("Files:\n\t{0}\nalready exist.").format("\n\t".join(["\"" + fp + "\"" for fp in overwrites]))
        else:
            return _("File \"{0}\" already exists.").format(overwrites[0])
    _CONSOLE_LOG.start_cmd("{0} {1} {2}\n".format(utils.quoted_join(fsi_paths), opsym, destn))
    if not os.path.isdir(destn):
        result = CmdResult.error(stderr=_('"{0}": Destination must be a directory for multifile move/copy.').format(destn))
        _CONSOLE_LOG.end_cmd(result)
        return result
    opn_paths_list = [(fsi_path, os.path.join(destn, os.path.basename(fsi_path))) for fsi_path in fsi_paths]
    omsg = "\n".join(["{0} {1} {2}.".format(src, opsym, destn) for (src, destn) in opn_paths_list]) if verbose else ""
    if not overwrite:
        overwrites = [destn for (src, destn) in opn_paths_list if os.path.exists(destn)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
            _CONSOLE_LOG.end_cmd(result)
            return result
    failed_opns_str = ""
    rescode = CmdResult.OK
    for (src, tgt) in opn_paths_list:
        if verbose:
            _CONSOLE_LOG.append_stdout("{0} {1} {2}.".format(src, opsym, tgt))
        if os.path.exists(tgt):
            try:
                if os.path.isdir(tgt) and not os.path.islink(tgt):
                    if force:
                        shutil.rmtree(tgt)
                    else:
                        os.removedirs(tgt)
                else:
                    os.remove(tgt)
            except OSError as edata:
                rescode |= CmdResult.ERROR_SUGGEST_FORCE if edata.errno == errno.ENOTEMPTY else CmdResult.ERROR
                serr = _("Error: {}: \"{}\" {} \"{}\"\n").format(edata.strerror, src, opsym, tgt)
                _CONSOLE_LOG.append_stderr(serr)
                failed_opns_str += serr
                continue
            except shutil.Error as edata:
                rescode |= CmdResult.ERROR
                serr = _("Error: \"{0}\" {1} \"{2}\" failed.\n").format(src, opsym, tgt)
                for src_path, tgt_path, reason in edata.args:
                    serr += _("Error: \"{0}\" {1} \"{2}\": {3}.\n").format(src_path, opsym, tgt_path, reason)
                _CONSOLE_LOG.append_stderr(serr)
                failed_opns_str += serr
                continue
        try:
            if opsym is Relation.MOVED_TO:
                os.rename(src, tgt)
            elif os.path.isdir(src):
                shutil.copytree(src, tgt)
            else:
                shutil.copy2(src, tgt)
        except OSError as edata:
            rescode |= CmdResult.ERROR
            serr = _("Error: \"{0}\" {1} \"{2}\" failed. {3}.\n").format(src, opsym, tgt, edata.strerror)
            _CONSOLE_LOG.append_stderr(serr)
            failed_opns_str += serr
            continue
        except shutil.Error as edata:
            rescode |= CmdResult.ERROR
            serr = _("Error: \"{0}\" {1} \"{2}\" failed.\n").format(src, opsym, tgt)
            for src_path, tgt_path, reason in edata.args:
                serr += _("Error: \"{0}\" {1} \"{2}\": {3}.\n").format(src_path, opsym, tgt_path, reason)
            _CONSOLE_LOG.append_stderr(serr)
            failed_opns_str += serr
            continue
    _CONSOLE_LOG.end_cmd()
    enotify.notify_events(E_FILE_MOVED)
    return CmdResult(rescode, omsg, failed_opns_str)

def os_copy_fs_item(fsi_path, destn, overwrite=False, force=False):
    return os_move_or_copy_fs_item(fsi_path, destn, opsym=Relation.COPIED_TO, overwrite=overwrite, force=force)

def os_copy_fs_items(fsi_paths, destn, overwrite=False, force=False):
    return os_move_or_copy_fs_items(fsi_paths, destn, opsym=Relation.COPIED_TO, overwrite=overwrite, force=force)

def os_move_fs_item(fsi_path, destn, overwrite=False, force=False):
    return os_move_or_copy_fs_item(fsi_path, destn, opsym=Relation.MOVED_TO, overwrite=overwrite, force=force)

def os_move_fs_items(fsi_paths, destn, overwrite=False, force=False):
    return os_move_or_copy_fs_items(fsi_paths, destn, opsym=Relation.MOVED_TO, overwrite=overwrite, force=force)

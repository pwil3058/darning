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

from .cmd_result import CmdResult
from .fsdb import Relation

from .gui import ws_event

E_FILE_ADDED, E_FILE_DELETED, E_FILE_CHANGES = ws_event.new_event_flags_and_mask(2)
E_FILE_MOVED = E_FILE_ADDED | E_FILE_DELETED

def os_create_file(file_path):
    """Attempt to create a file with the given file_path and report the outcome as
    a CmdResult tuple.
    1. If console is not None print report of successful creation on it.
    2. If a file with same file_path already exists fail and report a warning.
    3. If file creation fails for other reasons report an error.
    """
    from .gui import console
    console.LOG.start_cmd("create \"{0}\"".format(file_path))
    if not os.path.exists(file_path):
        try:
            open(file_path, 'w').close()
            ws_event.notify_events(E_FILE_ADDED)
            result = CmdResult.ok()
        except (IOError, OSError) as msg:
            result = CmdResult.error(stderr="\"{0}\": {1}".format(file_path, msg))
    else:
        result = CmdResult.warning(stderr=_("\"{0}\": file already exists").format(file_path))
    console.LOG.end_cmd(result)
    return result

def os_delete_files(file_paths):
    from .gui import console
    console.LOG.start_cmd(_('delete {0}').format(utils.quoted_join(file_paths)))
    serr = ""
    for filename in file_paths:
        try:
            os.remove(filename)
            console.LOG.append_stdout(_('Deleted: {0}\n').format(filename))
        except os.error as value:
            errmsg = ("%s: %s" + os.linesep) % (value[1], filename)
            serr += errmsg
            console.LOG.append_stderr(errmsg)
    console.LOG.end_cmd()
    ws_event.notify_events(os_utils.E_FILE_DELETED)
    return CmdResult.error("", serr) if serr else CmdResult.ok()

def os_move_or_copy_file(file_path, dest, opsym, force=False, dry_run=False, extra_checks=None, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    if os.path.isdir(dest):
        dest = os.path.join(dest, os.path.basename(file_path))
    omsg = "{0} {1} {2}.".format(file_path, opsym, dest) if verbose else ""
    if dry_run:
        if os.path.exists(dest):
            return CmdResult.error(omsg, _('File "{0}" already exists. Select "force" to overwrite.').format(dest)) | CmdResult.SUGGEST_FORCE
        else:
            return CmdResult.ok(omsg)
    from .gui import console
    console.LOG.start_cmd("{0} {1} {2}\n".format(file_path, opsym, dest))
    if not force and os.path.exists(dest):
        emsg = _('File "{0}" already exists. Select "force" to overwrite.').format(dest)
        result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_FORCE
        console.LOG.end_cmd(result)
        return result
    if extra_checks:
        result = extra_check([(file_path, dest)])
        if not result.is_ok:
            console.LOG.end_cmd(result)
            return result
    try:
        if opsym is Relation.MOVED_TO:
            os.rename(file_path, dest)
        elif opsym is Relation.COPIED_TO:
            shutil.copy(file_path, dest)
        result = CmdResult.ok(omsg)
    except (IOError, os.error, shutil.Error) as why:
        result = CmdResult.error(omsg, _("\"{0}\" {1} \"{2}\" failed. {3}.\n").format(file_path, opsym, dest, str(why)))
    console.LOG.end_cmd(result)
    ws_event.notify_events(E_FILE_MOVED)
    return result

def os_move_or_copy_files(file_path_list, dest, opsym, force=False, dry_run=False, extra_checks=None, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    def _overwrite_msg(overwrites):
        if len(overwrites) == 0:
            return ""
        elif len(overwrites) > 1:
            return _("Files:\n\t{0}\nalready exist. Select \"force\" to overwrite.").format("\n\t".join(["\"" + fp + "\"" for fp in overwrites]))
        else:
            return _("File \"{0}\" already exists. Select \"force\" to overwrite.").format(overwrites[0])
    if len(file_path_list) == 1:
        return os_move_or_copy_file(file_path_list[0], dest, opsym, force=force, dry_run=dry_run, extra_checks=extra_checks)
    from .gui import console
    if not dry_run:
        console.LOG.start_cmd("{0} {1} {2}\n".format(quoted_join(file_path_list), opsym, dest))
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
            return CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_FORCE
        else:
            return CmdResult.ok(omsg)
    if not force:
        overwrites = [dest for (src, dest) in opn_paths_list if os.path.exists(dest)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_FORCE
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
            if opsym is Relation.MOVED_TO:
                os.rename(src, dest)
            elif opsym is Relation.COPIED_TO:
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
    ws_event.notify_events(E_FILE_MOVED)
    if failed_opns_str:
        return CmdResult.error(omsg, failed_opns_str)
    return CmdResult.ok(omsg)

def os_copy_file(file_path, dest, force=False, dry_run=False):
    return os_move_or_copy_file(file_path, dest, opsym=Relation.COPIED_TO, force=force, dry_run=dry_run)

def os_copy_files(file_path_list, dest, force=False, dry_run=False):
    return os_move_or_copy_files(file_path_list, dest, opsym=Relation.COPIED_TO, force=force, dry_run=dry_run)

def os_move_file(file_path, dest, force=False, dry_run=False):
    return os_move_or_copy_file(file_path, dest, opsym=Relation.MOVED_TO, force=force, dry_run=dry_run)

def os_move_files(file_path_list, dest, force=False, dry_run=False):
    return os_move_or_copy_files(file_path_list, dest, opsym=Relation.MOVED_TO, force=force, dry_run=dry_run)

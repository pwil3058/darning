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
    from .gui import console
    console.LOG.start_cmd("mkdir -p " + dir_path)
    try:
        os.makedirs(dir_path)
        result = CmdResult.ok()
    except OSError as edata:
        result = CmdResult.error(str(edata))
    console.LOG.end_cmd(result)
    return result

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

def os_delete_files(file_paths, events=E_FILE_DELETED):
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
    ws_event.notify_events(events)
    return CmdResult.error("", serr) if serr else CmdResult.ok()

def os_move_or_copy_file(file_path, destn, opsym, overwrite=False, dry_run=False, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    if os.path.isdir(destn):
        destn = os.path.join(destn, os.path.basename(file_path))
    omsg = "{0} {1} {2}.".format(file_path, opsym, destn) if verbose else ""
    if dry_run:
        if os.path.exists(destn):
            return CmdResult.error(omsg, _('File "{0}" already exists.').format(destn)) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
        else:
            return CmdResult.ok(omsg)
    from .gui import console
    console.LOG.start_cmd("{0} {1} {2}\n".format(file_path, opsym, destn))
    if not overwrite and os.path.exists(destn):
        emsg = _('File "{0}" already exists.').format(destn)
        result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
        console.LOG.end_cmd(result)
        return result
    try:
        if opsym is Relation.MOVED_TO:
            os.rename(file_path, destn)
        elif opsym is Relation.COPIED_TO:
            shutil.copy(file_path, destn)
        result = CmdResult.ok(omsg)
    except (IOError, os.error, shutil.Error) as why:
        result = CmdResult.error(omsg, _("\"{0}\" {1} \"{2}\" failed. {3}.\n").format(file_path, opsym, destn, str(why)))
    console.LOG.end_cmd(result)
    ws_event.notify_events(E_FILE_MOVED)
    return result

def os_move_or_copy_files(file_paths, destn, opsym, overwrite=False, dry_run=False, verbose=False):
    assert opsym in (Relation.MOVED_TO, Relation.COPIED_TO), _("Invalid operation requested")
    def _overwrite_msg(overwrites):
        if len(overwrites) == 0:
            return ""
        elif len(overwrites) > 1:
            return _("Files:\n\t{0}\nalready exist.").format("\n\t".join(["\"" + fp + "\"" for fp in overwrites]))
        else:
            return _("File \"{0}\" already exists.").format(overwrites[0])
    if len(file_paths) == 1:
        return os_move_or_copy_file(file_paths[0], destn, opsym, overwrite=overwrite, dry_run=dry_run)
    from .gui import console
    if not dry_run:
        console.LOG.start_cmd("{0} {1} {2}\n".format(quoted_join(file_paths), opsym, destn))
    if not os.path.isdir(destn):
        result = CmdResult.error(stderr=_('"{0}": Destination must be a directory for multifile rename.').format(destn))
        if not dry_run:
            console.LOG.end_cmd(result)
        return result
    opn_paths_list = [(file_path, os.path.join(destn, os.path.basename(file_path))) for file_path in file_paths]
    omsg = "\n".join(["{0} {1} {2}.".format(src, opsym, destn) for (src, destn) in opn_paths_list]) if verbose else ""
    if dry_run:
        overwrites = [destn for (src, destn) in opn_paths_list if os.path.exists(destn)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            return CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
        else:
            return CmdResult.ok(omsg)
    if not overwrite:
        overwrites = [destn for (src, destn) in opn_paths_list if os.path.exists(destn)]
        if len(overwrites) > 0:
            emsg = _overwrite_msg(overwrites)
            result = CmdResult.error(omsg, emsg) | CmdResult.SUGGEST_OVERWRITE_OR_RENAME
            console.LOG.end_cmd(result)
            return result
    failed_opns_str = ""
    for (src, destn) in opn_paths_list:
        if verbose:
            console.LOG.append_stdout("{0} {1} {2}.".format(src, opsym, destn))
        try:
            if opsym is Relation.MOVED_TO:
                os.rename(src, destn)
            elif opsym is Relation.COPIED_TO:
                if os.path.isdir(src):
                    shutil.copytree(src, destn)
                else:
                    shutil.copy2(src, destn)
        except (IOError, os.error, shutil.Error) as why:
            serr = _('"{0}" {1} "{2}" failed. {3}.\n').format(src, opsym, destn, str(why))
            console.LOG.append_stderr(serr)
            failed_opns_str += serr
            continue
    console.LOG.end_cmd()
    ws_event.notify_events(E_FILE_MOVED)
    if failed_opns_str:
        return CmdResult.error(omsg, failed_opns_str)
    return CmdResult.ok(omsg)

def os_copy_file(file_path, destn, overwrite=False, dry_run=False):
    return os_move_or_copy_file(file_path, destn, opsym=Relation.COPIED_TO, overwrite=overwrite, dry_run=dry_run)

def os_copy_files(file_paths, destn, overwrite=False, dry_run=False):
    return os_move_or_copy_files(file_paths, destn, opsym=Relation.COPIED_TO, overwrite=overwrite, dry_run=dry_run)

def os_move_file(file_path, destn, overwrite=False, dry_run=False):
    return os_move_or_copy_file(file_path, destn, opsym=Relation.MOVED_TO, overwrite=overwrite, dry_run=dry_run)

def os_move_files(file_paths, destn, overwrite=False, dry_run=False):
    return os_move_or_copy_files(file_paths, destn, opsym=Relation.MOVED_TO, overwrite=overwrite, dry_run=dry_run)

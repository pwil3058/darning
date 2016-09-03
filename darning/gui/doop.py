### Copyright (C) 2005-2016 Peter Williams <pwil3058@gmail.com>
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

"""
Wrappers for common (but complex) "do" operations.
"""

from gi.repository import Gtk

from . import dialogue

class DoOperationMixin:
    def do_op_rename_overwrite_force_or_cancel(self, source, target, do_op, rename_target):
        overwrite = False
        force = False
        while True:
            with self.showing_busy():
                result = do_op(source, target, overwrite=overwrite, force=force)
            if (not overwrite and result.suggests_overwrite) or (not force and result.suggests_force):
                resp = dialogue.ask_rename_overwrite_force_or_cancel(result, parent=self._parent)
                if resp == Gtk.ResponseType.CANCEL:
                    return CmdResult.ok() # we don't want to be a nag
                elif resp == dialogue.Response.OVERWRITE:
                    overwrite = True
                elif resp == dialogue.Response.FORCE:
                    force = True
                elif resp == dialogue.Response.RENAME:
                    target = rename_target(target, self._parent)
                    if target is None:
                        break
                continue
            break
        dialogue.report_any_problems(result, self._parent)
        return result

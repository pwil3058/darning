### Copyright (C) 2011-2015 Peter Williams <pwil3058@gmail.com>
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

'''Manage configurable options'''

from aipoed.options import define, Defn, str_to_bool

define("pop", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch after pop")))
define("push", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch before push")))
define("absorb", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch before absorb")))
define("remove", "keep_patch_backup", Defn(str_to_bool, True, _("Keep back up copies of removed patches.  Facilitates restoration at a later time.")))

define("diff", "extdiff", Defn(str, None, _("The name of external application for viewing diffs")))

define("reconcile", "tool", Defn(str, "meld", _("The name of external application for reconciling conflicts")))

define("export", "replace_spc_in_name_with", Defn(str, None, _("Character to replace spaces in patch names with during export")))

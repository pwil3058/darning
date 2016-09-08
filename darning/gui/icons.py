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

import os
import sys
import collections

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GdkPixbuf

from .. import APP_NAME

# find the icons directory
# first look in the source directory (so that we can run uninstalled)
_libdir = os.path.join(sys.path[0], "pixmaps")
if not os.path.exists(_libdir) or not os.path.isdir(_libdir):
    _TAILEND = os.path.join("share", "pixmaps", APP_NAME)
    _prefix = sys.path[0]
    while _prefix:
        _libdir = os.path.join(_prefix, _TAILEND)
        if os.path.exists(_libdir) and os.path.isdir(_libdir):
            break
        _prefix = os.path.dirname(_prefix)

APP_ICON = APP_NAME
APP_ICON_FILE = os.path.join(os.path.dirname(_libdir), APP_ICON + os.extsep + "png")
APP_ICON_PIXBUF = GdkPixbuf.Pixbuf.new_from_file(APP_ICON_FILE)

STOCK_APPLIED = APP_NAME + "_stock_applied"
STOCK_APPLIED_NEEDS_REFRESH = APP_NAME + "_stock_applied_needs_refresh"
STOCK_APPLIED_UNREFRESHABLE = APP_NAME + "_stock_applied_unrefreshable"
STOCK_BRANCH = APP_NAME + "_stock_branch"
STOCK_COMMIT = APP_NAME + "_stock_commit"
STOCK_DIFF = APP_NAME + "_stock_diff"
STOCK_FINISH_PATCH = APP_NAME + "_stock_finish_patch"
STOCK_FOLD_PATCH = APP_NAME + "_stock_fold_patch"
STOCK_IMPORT_PATCH = APP_NAME + "_stock_import_patch"
STOCK_MERGE = APP_NAME + "_stock_merge"
STOCK_NEW_PATCH = APP_NAME + "_stock_new_patch"
STOCK_PATCH_GUARD = APP_NAME + "_stock_patch_guard"
STOCK_PATCH_GUARD_SELECT = APP_NAME + "_stock_patch_guard_select"
STOCK_POP_PATCH = APP_NAME + "_stock_pop_patch"
STOCK_PUSH_PATCH = APP_NAME + "_stock_push_patch"
STOCK_REFRESH_PATCH = APP_NAME + "_stock_refresh_patch"
STOCK_TAG = APP_NAME + "_stock_tag"
STOCK_FILE_REFRESHED = APP_NAME + "_stock_file_refreshed"
STOCK_FILE_NEEDS_REFRESH = APP_NAME + "_stock_file_needs_refresh"
STOCK_FILE_UNREFRESHABLE = APP_NAME + "_stock_file_unrefreshable"

_STOCK_ITEMS_OWN_PNG = [
    (STOCK_APPLIED, _("Applied"), 0, 0, None),
    (STOCK_APPLIED_NEEDS_REFRESH, _("Applied (needs refresh)"), 0, 0, None),
    (STOCK_APPLIED_UNREFRESHABLE, _("Applied (unrefreshable)"), 0, 0, None),
    (STOCK_BRANCH, _("Branch"), 0, 0, None),
    (STOCK_COMMIT, _("Commit"), 0, 0, None),
    (STOCK_DIFF, _("Diff"), 0, 0, None),
    (STOCK_FINISH_PATCH, _("Finish"), 0, 0, None),
    (STOCK_FOLD_PATCH, _("Fold"), 0, 0, None),
    (STOCK_IMPORT_PATCH, _("Import"), 0, 0, None),
    (STOCK_MERGE, _("Merge"), 0, 0, None),
    (STOCK_NEW_PATCH, _("New"), 0, 0, None),
    (STOCK_PATCH_GUARD, _("Guard"), 0, 0, None),
    (STOCK_PATCH_GUARD_SELECT, _("Select"), 0, 0, None),
    (STOCK_POP_PATCH, _("Pop"), 0, 0, None),
    (STOCK_PUSH_PATCH, _("Push"), 0, 0, None),
    (STOCK_REFRESH_PATCH, _("Refresh"), 0, 0, None),
    (STOCK_TAG, _("Tag"), 0, 0, None),
    (STOCK_FILE_REFRESHED, _("Refreshed"), 0, 0, None),
    (STOCK_FILE_NEEDS_REFRESH, _("Needs Refresh"), 0, 0, None),
    (STOCK_FILE_UNREFRESHABLE, _("Unrefreshable"), 0, 0, None),
]

#Gtk.stock_add(_STOCK_ITEMS_OWN_PNG)

_FACTORY = Gtk.IconFactory()
_FACTORY.add_default()
_FACTORY.add(APP_ICON, Gtk.IconSet(APP_ICON_PIXBUF))

_PREFIX = APP_NAME + "_"

def _png_file_name(item_name):
    return os.path.join(_libdir, item_name[len(_PREFIX):] + os.extsep + "png")

def make_pixbuf(name):
    return GdkPixbuf.Pixbuf.new_from_file(_png_file_name(name))

for _item in _STOCK_ITEMS_OWN_PNG:
    _name = _item[0]
    _FACTORY.add(_name, Gtk.IconSet(make_pixbuf(_name)))

StockAlias = collections.namedtuple("StockAlias", ["name", "alias", "text"])

# Icons that are aliased to Gtk or other stock items
STOCK_BACKOUT = APP_NAME + "_stock_backout"
STOCK_CHECKOUT = APP_NAME + "_stock_checkout"
STOCK_CLONE = APP_NAME + "_stock_clone"
STOCK_CONFIG = APP_NAME + "_stock_config"
STOCK_EDIT = APP_NAME + "_stock_edit"
STOCK_GRAPH = APP_NAME + "_stock_graph"
STOCK_GUESS = APP_NAME + "_stock_guess"
STOCK_INIT = APP_NAME + "_stock_init"
STOCK_INSERT = APP_NAME + "_stock_insert"
STOCK_LOG = APP_NAME + "_stock_log"
STOCK_MARK_RESOLVE = APP_NAME + "_stock_mark_resolve"
STOCK_MARK_UNRESOLVE = APP_NAME + "_stock_mark_uresolve"
STOCK_MOVE = APP_NAME + "_stock_move"
STOCK_PULL = APP_NAME + "_stock_pull"
STOCK_PUSH = APP_NAME + "_stock_push"
STOCK_RECOVERY = APP_NAME + "_stock_recovery"
STOCK_REMOVE = APP_NAME + "_stock_remove"
STOCK_RENAME = APP_NAME + "_stock_rename"
STOCK_RESOLVE = APP_NAME + "_stock_resolve"
STOCK_REVERT = APP_NAME + "_stock_revert"
STOCK_ROLLBACK = APP_NAME + "_stock_rollback"
STOCK_SELECT_GUARD = APP_NAME + "_stock_select_guard"
STOCK_SERVE = APP_NAME + "_stock_serve"
STOCK_SHELVE = APP_NAME + "_stock_shelve"
STOCK_STATUS = APP_NAME + "_stock_status"
STOCK_STATUS_NOT_OK = APP_NAME + "_stock_status_not_ok"
STOCK_STATUS_OK = APP_NAME + "_stock_ok"
STOCK_SYNCH = APP_NAME + "_stock_synch"
STOCK_UPDATE = APP_NAME + "_stock_update"
STOCK_VERIFY = APP_NAME + "_stock_verify"
STOCK_NEW_PLAYGROUND = APP_NAME + "_stock_new_playground"

# Icons that have to be designed eventually (using GtK stock in the meantime)
_STOCK_ALIAS_LIST = [
    StockAlias(name=STOCK_BACKOUT, alias=Gtk.STOCK_MEDIA_REWIND, text=""),
    StockAlias(name=STOCK_CHECKOUT, alias=Gtk.STOCK_EXECUTE, text=""),
    StockAlias(name=STOCK_CLONE, alias=Gtk.STOCK_COPY, text=""),
    StockAlias(name=STOCK_CONFIG, alias=Gtk.STOCK_PREFERENCES, text=""),
    StockAlias(name=STOCK_EDIT, alias=Gtk.STOCK_EDIT, text=""),
    StockAlias(name=STOCK_GRAPH, alias=Gtk.STOCK_FILE, text=""),
    StockAlias(name=STOCK_GUESS, alias=Gtk.STOCK_DIALOG_QUESTION, text=""),
    StockAlias(name=STOCK_INIT, alias=STOCK_APPLIED, text=""),
    StockAlias(name=STOCK_INSERT, alias=Gtk.STOCK_ADD, text=_("_Insert")),
    StockAlias(name=STOCK_LOG, alias=Gtk.STOCK_FIND, text=""),
    StockAlias(name=STOCK_MARK_RESOLVE, alias=Gtk.STOCK_APPLY, text=""),
    StockAlias(name=STOCK_MARK_UNRESOLVE, alias=Gtk.STOCK_CANCEL, text=""),
    StockAlias(name=STOCK_MOVE, alias=Gtk.STOCK_PASTE, text=""),
    StockAlias(name=STOCK_PULL, alias=Gtk.STOCK_GO_FORWARD, text=""),
    StockAlias(name=STOCK_PUSH, alias=Gtk.STOCK_GO_BACK, text=""),
    StockAlias(name=STOCK_RECOVERY, alias=Gtk.STOCK_REVERT_TO_SAVED, text=""),
    StockAlias(name=STOCK_REMOVE, alias=Gtk.STOCK_REMOVE, text=""),
    StockAlias(name=STOCK_RENAME, alias=Gtk.STOCK_PASTE, text=""),
    StockAlias(name=STOCK_RESOLVE, alias=Gtk.STOCK_CONVERT, text=_("Resolve")),
    StockAlias(name=STOCK_REVERT, alias=Gtk.STOCK_UNDO, text=""),
    StockAlias(name=STOCK_ROLLBACK, alias=Gtk.STOCK_UNDO, text=""),
    StockAlias(name=STOCK_SELECT_GUARD, alias=STOCK_APPLIED, text=""),
    StockAlias(name=STOCK_SERVE, alias=Gtk.STOCK_EXECUTE, text=""),
    StockAlias(name=STOCK_SHELVE, alias=Gtk.STOCK_EXECUTE, text=""),
    StockAlias(name=STOCK_STATUS, alias=Gtk.STOCK_INFO, text=""),
    StockAlias(name=STOCK_STATUS_NOT_OK, alias=Gtk.STOCK_CANCEL, text=""),
    StockAlias(name=STOCK_STATUS_OK, alias=Gtk.STOCK_APPLY, text=""),
    StockAlias(name=STOCK_SYNCH, alias=Gtk.STOCK_REFRESH, text=""),
    StockAlias(name=STOCK_UPDATE, alias=Gtk.STOCK_EXECUTE, text=""),
    StockAlias(name=STOCK_VERIFY, alias=STOCK_APPLIED, text=""),
    StockAlias(name=STOCK_NEW_PLAYGROUND, alias=Gtk.STOCK_NEW, text=_("New Playground")),
]

_STYLE = Gtk.Frame().get_style()

for _item in _STOCK_ALIAS_LIST:
    _FACTORY.add(_item.name, _STYLE.lookup_icon_set(_item.alias))

#Gtk.stock_add([(item.name, item.text, 0, 0, None) for item in _STOCK_ALIAS_LIST])

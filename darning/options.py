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


import os
import collections

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from .config_data import APP_NAME, CONFIG_DIR_NAME
from . import CmdResult

_GLOBAL_CFG_FILE = os.path.join(CONFIG_DIR_NAME, "options.cfg")
GLOBAL_OPTIONS = configparser.SafeConfigParser()

def load_global_options():
    global GLOBAL_OPTIONS
    GLOBAL_OPTIONS = configparser.SafeConfigParser()
    try:
        GLOBAL_OPTIONS.read(_GLOBAL_CFG_FILE)
    except configparser.ParsingError as edata:
        return CmdResult.error(stderr=_("Error reading global options: {0}\n").format(str(edata)))
    return CmdResult.ok()

def reload_global_options():
    global GLOBAL_OPTIONS
    new_version = configparser.SafeConfigParser()
    try:
        new_version.read(_GLOBAL_CFG_FILE)
    except configparser.ParsingError as edata:
        return CmdResult.error(stderr=_("Error reading global options: {0}\n").format(str(edata)))
    GLOBAL_OPTIONS = new_version
    return CmdResult.ok()

_PGND_CFG_FILE = os.path.expanduser(".darning.dbd/options.cfg")
PGND_OPTIONS = configparser.SafeConfigParser()

def load_pgnd_options():
    global PGND_OPTIONS
    PGND_OPTIONS = configparser.SafeConfigParser()
    try:
        PGND_OPTIONS.read(_PGND_CFG_FILE)
    except configparser.ParsingError as edata:
        return CmdResult.error(stderr=_("Error reading playground options: {0}\n").format(str(edata)))
    return CmdResult.ok()

def reload_pgnd_options():
    global PGND_OPTIONS
    new_version = configparser.SafeConfigParser()
    try:
        new_version.read(_PGND_CFG_FILE)
    except configparser.ParsingError as edata:
        return CmdResult.error(stderr=_("Error reading playground options: {0}\n").format(str(edata)))
    PGND_OPTIONS = new_version
    return CmdResult.ok()

class DuplicateDefn(Exception): pass

Defn = collections.namedtuple("Defn", ["str_to_val", "default", "help"])

DEFINITIONS = {}

def define(section, oname, odefn):
    if not section in DEFINITIONS:
        DEFINITIONS[section] = {oname: odefn,}
    elif oname in DEFINITIONS[section]:
        raise DuplicateDefn("{0}:{1} already defined".format(section, oname))
    else:
        DEFINITIONS[section][oname] = odefn

def str_to_bool(string):
    lowstr = string.lower()
    if lowstr in ["true", "yes", "on", "1"]:
        return True
    elif lowstr in ["false", "no", "off", "0"]:
        return False
    else:
        return None

def get(section, oname, pgnd_only=False):
    # This should cause an exception if section:oname is not known
    # which is what we want
    str_to_val = DEFINITIONS[section][oname].str_to_val
    value = None
    if PGND_OPTIONS.has_option(section, oname):
        value = str_to_val(PGND_OPTIONS.get(section, oname))
    elif not pgnd_only and GLOBAL_OPTIONS.has_option(section, oname):
        value = str_to_val(GLOBAL_OPTIONS.get(section, oname))
    return value if value is not None else DEFINITIONS[section][oname].default

define("user", "name", Defn(str, None, _("User's display name e.g. Fred Bloggs")))
define("user", "email", Defn(str, None, _("User's email address e.g. fred@bloggs.com")))

define("pop", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch after pop")))
define("push", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch before push")))
define("absorb", "drop_added_tws", Defn(str_to_bool, True, _("Remove added trailing white space (TWS) from patch before absorb")))
define("remove", "keep_patch_backup", Defn(str_to_bool, True, _("Keep back up copies of removed patches.  Facilitates restoration at a later time.")))

define("diff", "extdiff", Defn(str, None, _("The name of external application for viewing diffs")))

define("reconcile", "tool", Defn(str, "meld", _("The name of external application for reconciling conflicts")))

define("export", "replace_spc_in_name_with", Defn(str, None, _("Character to replace spaces in patch names with during export")))

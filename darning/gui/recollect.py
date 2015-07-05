### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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
import sys
import collections

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from ..config_data import APP_NAME, CONFIG_DIR_NAME

_RECOLLECTIONS_PATH = os.path.join(CONFIG_DIR_NAME, "guistate.mem")

RECOLLECTIONS = configparser.SafeConfigParser()

Result = collections.namedtuple('Result', ['sucessful', 'why_not'])
OK = Result(True, None)

def load_recollections():
    global RECOLLECTIONS
    RECOLLECTIONS = configparser.SafeConfigParser()
    try:
        RECOLLECTIONS.read(_RECOLLECTIONS_PATH)
    except configparser.ParsingError as edata:
        return Result(False, _('Error reading user options: {0}\n').format(str(edata)))
    return OK

def reload_recollections():
    global RECOLLECTIONS
    new_version = configparser.SafeConfigParser()
    try:
        new_version.read(_RECOLLECTIONS_PATH)
    except configparser.ParsingError as edata:
        return Result(False, _('Error reading user options: {0}\n').format(str(edata)))
    RECOLLECTIONS = new_version
    return OK

class DuplicateDefn(Exception): pass

Defn = collections.namedtuple('Defn', ['str_to_val', 'default'])

DEFINITIONS = {}

def define(section, oname, odefn):
    if not section in DEFINITIONS:
        DEFINITIONS[section] = {oname: odefn,}
    elif oname in DEFINITIONS[section]:
        raise DuplicateDefn('{0}:{1} already defined'.format(section, oname))
    else:
        DEFINITIONS[section][oname] = odefn

def get(section, oname):
    # This should cause an exception if section:oname is not known
    # which is what we want
    str_to_val = DEFINITIONS[section][oname].str_to_val
    value = None
    if RECOLLECTIONS.has_option(section, oname):
        value = str_to_val(RECOLLECTIONS.get(section, oname))
    return value if value is not None else DEFINITIONS[section][oname].default

def set(section, oname, val):
    # This should cause an exception if section:oname is not known
    # which is what we want
    if not RECOLLECTIONS.has_section(section):
        if DEFINITIONS[section][oname]:
            RECOLLECTIONS.add_section(section)
        else:
            raise LookupError('{0}:{1}'.format(section, oname))
    RECOLLECTIONS.set(section, oname, val)
    RECOLLECTIONS.write(open(_RECOLLECTIONS_PATH, 'w'))

define(APP_NAME, "last_pgnd", Defn(str, ""))

define("main_window", "last_geometry", Defn(str, ""))
define("main_window", "vpaned_position", Defn(int, -1))
define("main_window", "hpaned_position", Defn(int, -1))

define("export", "last_directory", Defn(str, ""))
define("import", "last_directory", Defn(str, ""))

load_recollections()

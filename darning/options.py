### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
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

'''Manage configurable options for Darning'''


import os
import collections

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from darning import cmd_result

_GLOBAL_CFG_FILE = os.path.expanduser('~/.darning.d/options.cfg')
GLOBAL_OPTIONS = configparser.SafeConfigParser()

def load_global_options():
    global GLOBAL_OPTIONS
    GLOBAL_OPTIONS = configparser.SafeConfigParser()
    try:
        GLOBAL_OPTIONS.read(_GLOBAL_CFG_FILE)
    except configparser.ParsingError as edata:
        return cmd_result.Result(cmd_result.ERROR, '', 'Error reading global options: {0}\n'.format(str(edata)))
    return cmd_result.Result(cmd_result.OK, '', '')

def reload_global_options():
    global GLOBAL_OPTIONS
    new_version = configparser.SafeConfigParser()
    try:
        new_version.read(_GLOBAL_CFG_FILE)
    except configparser.ParsingError as edata:
        return cmd_result.Result(cmd_result.ERROR, '', 'Error reading global options: {0}\n'.format(str(edata)))
    GLOBAL_OPTIONS = new_version
    return cmd_result.Result(cmd_result.OK, '', '')

_PGND_CFG_FILE = os.path.expanduser('.darning.dbd/options.cfg')
PGND_OPTIONS = configparser.SafeConfigParser()

def load_pgnd_options():
    global PGND_OPTIONS
    PGND_OPTIONS = configparser.SafeConfigParser()
    try:
        PGND_OPTIONS.read(_PGND_CFG_FILE)
    except configparser.ParsingError as edata:
        return cmd_result.Result(cmd_result.ERROR, '', 'Error reading playground options: {0}\n'.format(str(edata)))
    return cmd_result.Result(cmd_result.OK, '', '')

def reload_pgnd_options():
    global PGND_OPTIONS
    new_version = configparser.SafeConfigParser()
    try:
        new_version.read(_PGND_CFG_FILE)
    except configparser.ParsingError as edata:
        return cmd_result.Result(cmd_result.ERROR, '', 'Error reading playground options: {0}\n'.format(str(edata)))
    PGND_OPTIONS = new_version
    return cmd_result.Result(cmd_result.OK, '', '')

class DuplicateDefn(Exception): pass

Defn = collections.namedtuple('Defn', ['type', 'default', 'help'])

DEFINITIONS = {}

def define(section, oname, odefn):
    if not section in DEFINITIONS:
        DEFINITIONS[section] = {oname: odefn,}
    elif oname in DEFINITIONS[section]:
        raise DuplicateDefn('{0}:{1} already defined'.format(section, name))
    else:
        DEFINITIONS[section][oname] = odefn

def get(section, oname):
    # This should cause an exception if section:oname is not known
    # which is what we want
    otype = DEFINITIONS[section][oname].type
    if PGND_OPTIONS.has_option(section, oname):
        return otype(PGND_OPTIONS.get(section, oname))
    elif GLOBAL_OPTIONS.has_option(section, oname):
        return otype(GLOBAL_OPTIONS.get(section, oname))
    else:
        return DEFINITIONS[section][oname].default

define('user', 'name', Defn(str, None, 'User\'s display name e.g. Fred Bloggs'))
define('user', 'email', Defn(str, None, 'User\'s email address e.g. fred@bloggs.com'))

### Copyright (C) 2007-2011 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''
External command return values
'''

import collections

Result = collections.namedtuple('Result', ['eflags', 'stdout', 'stderr'])

# N.B. WARNING is at bit 9 so that 8 bits are available for important
# flags that we hope hg can be modified to use
OK = 0
_NFLAGS = 9
ERROR, \
SUGGEST_FORCE, \
SUGGEST_REFRESH, \
SUGGEST_RECOVER, \
SUGGEST_RENAME, \
SUGGEST_DISCARD, \
SUGGEST_EDIT, \
SUGGEST_MERGE, \
WARNING = [2 ** flag_num for flag_num in range(_NFLAGS)]
SUGGEST_ALL = 2 ** _NFLAGS - 1 - WARNING|ERROR
SUGGEST_FORCE_OR_REFRESH = SUGGEST_FORCE | SUGGEST_REFRESH
WARNING_SUGGEST_FORCE = WARNING | SUGGEST_FORCE
ERROR_SUGGEST_FORCE = ERROR | SUGGEST_FORCE
WARNING_SUGGEST_REFRESH = WARNING | SUGGEST_REFRESH
ERROR_SUGGEST_REFRESH = ERROR | SUGGEST_REFRESH
WARNING_SUGGEST_FORCE_OR_REFRESH = WARNING | SUGGEST_FORCE_OR_REFRESH
ERROR_SUGGEST_FORCE_OR_REFRESH = ERROR | SUGGEST_FORCE_OR_REFRESH
SUGGEST_FORCE_OR_RENAME = SUGGEST_FORCE | SUGGEST_RENAME
SUGGEST_MERGE_OR_DISCARD = SUGGEST_MERGE | SUGGEST_DISCARD

BASIC_VALUES_MASK = OK | WARNING | ERROR

def basic_value(res):
    if isinstance(res, Result):
        return res.eflags & BASIC_VALUES_MASK
    else:
        return res & BASIC_VALUES_MASK

def is_ok(res):
    return basic_value(res) == OK

def is_warning(res):
    return basic_value(res) == WARNING

def is_less_than_warning(res):
    return basic_value(res) not in [WARNING, ERROR]

def is_error(res):
    return basic_value(res) == ERROR

def is_less_than_error(res):
    return basic_value(res) != ERROR

def suggests_force(res):
    if isinstance(res, Result):
        return (res.eflags & SUGGEST_FORCE) == SUGGEST_FORCE
    else:
        return (res & SUGGEST_FORCE) == SUGGEST_FORCE

def map_cmd_result(result, ignore_err_re=None):
    if result.eflags == 0:
        if result.stderr and not (ignore_err_re and ignore_err_re.match(result.stderr)):
            outres = WARNING
        else:
            outres = OK
    else:
        outres = ERROR
    return Result(outres, result.stdout, result.stderr)

class Failure(Exception):
    def __init__(self, result):
        self.result = result

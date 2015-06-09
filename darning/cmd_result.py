### Copyright (C) 2007-2015 Peter Williams <pwil3058@gmail.com>
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

'''
External command return values
'''

import collections

class CmdResult(collections.namedtuple('CmdResult', ['ecode', 'stdout', 'stderr'])):
    OK = 0
    _NFLAGS = 11
    WARNING, \
    ERROR, \
    SUGGEST_FORCE, \
    SUGGEST_REFRESH, \
    SUGGEST_RECOVER, \
    SUGGEST_RENAME, \
    SUGGEST_DISCARD, \
    SUGGEST_ABSORB, \
    SUGGEST_EDIT, \
    SUGGEST_MERGE, \
    SUGGEST_OVERWRITE = [2 ** flag_num for flag_num in range(_NFLAGS)]
    SUGGEST_ALL = 2 ** _NFLAGS - 1 - WARNING|ERROR
    SUGGEST_FORCE_OR_REFRESH = SUGGEST_FORCE | SUGGEST_REFRESH
    SUGGEST_FORCE_OR_RENAME = SUGGEST_FORCE | SUGGEST_RENAME
    SUGGEST_MERGE_OR_DISCARD = SUGGEST_MERGE | SUGGEST_DISCARD
    SUGGEST_OVERWRITE_OR_RENAME = SUGGEST_OVERWRITE | SUGGEST_RENAME
    SUGGEST_FORCE_OR_EDIT = SUGGEST_FORCE | SUGGEST_EDIT
    SUGGEST_FORCE_OR_ABSORB = SUGGEST_FORCE | SUGGEST_ABSORB
    SUGGEST_FORCE_ABSORB_OR_REFRESH = SUGGEST_FORCE | SUGGEST_ABSORB | SUGGEST_REFRESH
    ERROR_SUGGEST_FORCE = ERROR | SUGGEST_FORCE
    ERROR_SUGGEST_REFRESH = ERROR | SUGGEST_REFRESH
    ERROR_SUGGEST_FORCE_OR_ABSORB = ERROR | SUGGEST_FORCE_OR_ABSORB
    ERROR_SUGGEST_FORCE_OR_REFRESH = ERROR | SUGGEST_FORCE_OR_REFRESH
    ERROR_SUGGEST_FORCE_ABSORB_OR_REFRESH = ERROR | SUGGEST_FORCE_ABSORB_OR_REFRESH

    BASIC_VALUES_MASK = OK | WARNING | ERROR
    def __str__(self):
        return "CmdResult(ecode={0:b}, stdout={1}, stderr={2})".format(self.ecode, self.stdout, self.stderr)
    def mapped_for_warning(self, sanitize_stderr=None):
        if self.ecode == 0:
            if (self.stderr if sanitize_stderr is None else sanitize_stderr(self.stderr)):
                return self.__class__(self.WARNING, self.stdout, self.stderr)
            else:
                return self.__class__(self.OK, self.stdout, self.stderr)
        else:
            return self.__class__(self.ERROR, self.stdout, self.stderr)
    def mapped_for_suggestions(self, suggestion_table):
        ecode = self.ecode
        for suggestion, criteria in suggestion_table:
            if criteria(self):
                ecode |= suggestion
        return self.__class__(ecode, self.stdout, self.stderr)
    def __or__(self, suggestions):
        assert suggestions & self.SUGGEST_ALL == suggestions
        return self.__class__(self.ecode | suggestions, self.stdout, self.stderr)
    def __sub__(self, suggestions):
        assert suggestions & self.SUGGEST_ALL == suggestions
        return self.__class__(self.ecode & ~suggestions, self.stdout, self.stderr)
    @classmethod
    def ok(cls, stdout="", stderr=""):
        return cls(cls.OK, stdout, stderr)
    @classmethod
    def warning(cls, stdout="", stderr=""):
        return cls(cls.WARNING, stdout, stderr)
    @classmethod
    def error(cls, stdout="", stderr=""):
        return cls(cls.ERROR, stdout, stderr)
    @property
    def msg(self):
        return "\n".join([self.stdout, self.stderr])
    @property
    def is_ok(self):
        assert self.ecode == 0 or self.ecode & self.BASIC_VALUES_MASK != 0
        return self.ecode == self.OK
    @property
    def is_warning(self):
        return self.ecode & self.BASIC_VALUES_MASK == self.WARNING
    @property
    def is_error(self):
        return self.ecode & self.BASIC_VALUES_MASK == self.ERROR
    @property
    def is_less_than_error(self):
        return self.ecode & self.BASIC_VALUES_MASK != self.ERROR
    @property
    def suggests_force(self):
        return self.ecode & self.SUGGEST_FORCE
    @property
    def suggests_refresh(self):
        return self.ecode & self.SUGGEST_REFRESH
    @property
    def suggests_recover(self):
        return self.ecode & self.SUGGEST_RECOVER
    @property
    def suggests_rename(self):
        return self.ecode & self.SUGGEST_RENAME
    @property
    def suggests_discard(self):
        return self.ecode & self.SUGGEST_DISCARD
    @property
    def suggests_absorb(self):
        return self.ecode & self.SUGGEST_ABSORB
    @property
    def suggests_edit(self):
        return self.ecode & self.SUGGEST_EDIT
    @property
    def suggests_overwrite(self):
        return self.ecode & self.SUGGEST_OVERWRITE
    @property
    def suggests_force(self):
        return self.ecode & self.SUGGEST_FORCE
    def suggests(self, suggestion):
        return self.ecode & suggestion != 0

class CmdFailure(Exception):
    def __init__(self, result):
        self.result = result

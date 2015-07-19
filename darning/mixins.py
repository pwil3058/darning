### Copyright (C) 2015 Peter Williams <peter_ono@users.sourceforge.net>
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

class ExtensiblePickleObject(object):
    '''A base class for pickleable objects that can cope with modifications'''
    RENAMES = dict()
    NEW_FIELDS = dict()
    def __setstate__(self, state):
        self.__dict__ = state
        for old_field in self.RENAMES:
            if old_field in self.__dict__:
                self.__dict__[self.RENAMES[old_field]] = self.__dict__.pop(old_field)
    def __getstate__(self):
        return self.__dict__
    def __getattr__(self, attr):
        if attr in self.NEW_FIELDS:
            return self.NEW_FIELDS[attr]
        raise AttributeError(attr)

# CITE: http://code.activestate.com/recipes/578433-mixin-for-pickling-objects-with-__slots__/
class PedanticSlotPickleMixin(object):
    def __getstate__(self):
        return {slot : getattr(self, slot) for slot in self.__slots__}
    def __setstate__(self, state):
        for slot, value in state.iteritems():
            setattr(self, slot, value)
    def all_slots_are_initialized(self):
        for slot in self.__slots__:
            if not hasattr(self, slot):
                return False
        return True

class LenientSlotPickleMixin(object):
    def __getstate__(self):
        return {slot : getattr(self, slot) for slot in self.__slots__ if hasattr(self, slot)}
    def __setstate__(self, state):
        for slot, value in state.iteritems():
            setattr(self, slot, value)
    def all_slots_are_initialized(self):
        for slot in self.__slots__:
            if not hasattr(self, slot):
                return False
        return True

class WrapperMixin(object):
    WRAPPED_ATTRIBUTES = list()
    WRAPPED_OBJECT_NAME = "_WRAPPED_OBJECT"
    def __getattr__(self, attr_name):
        if attr_name in self.WRAPPED_ATTRIBUTES:
            return getattr(self.__dict__[self.WRAPPED_OBJECT_NAME], attr_name)
        raise AttributeError(attr_name)
    def __setattr__(self, attr_name, value):
        if attr_name in self.WRAPPED_ATTRIBUTES:
            setattr(self.__dict__[self.WRAPPED_OBJECT_NAME], attr_name, value)
        self.__dict__[attr_name] = value

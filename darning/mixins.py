###  Copyright (C) 2016 Peter Williams <pwil3058@gmail.com>
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

# CITE: http://code.activestate.com/recipes/578433-mixin-for-pickling-objects-with-__slots__/
class PedanticSlotPickleMixin:
    def __getstate__(self):
        return {slot : getattr(self, slot) for slot in self.__slots__}
    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)
    def all_slots_are_initialized(self):
        for slot in self.__slots__:
            if not hasattr(self, slot):
                return False
        return True

class LenientSlotPickleMixin:
    def __getstate__(self):
        return {slot : getattr(self, slot) for slot in self.__slots__ if hasattr(self, slot)}
    def __setstate__(self, state):
        for slot, value in state.items():
            setattr(self, slot, value)
    def all_slots_are_initialized(self):
        for slot in self.__slots__:
            if not hasattr(self, slot):
                return False
        return True

class WrapperMixin:
    WRAPPED_ATTRIBUTES = list()
    WRAPPED_OBJECT_NAME = "_WRAPPED_OBJECT"
    def __getattr__(self, attr_name):
        if attr_name in self.WRAPPED_ATTRIBUTES:
            return getattr(self.__dict__[self.WRAPPED_OBJECT_NAME], attr_name)
        raise AttributeError(attr_name)
    def __setattr__(self, attr_name, value):
        if attr_name in self.WRAPPED_ATTRIBUTES:
            setattr(self.__dict__[self.WRAPPED_OBJECT_NAME], attr_name, value)
        else:
            self.__dict__[attr_name] = value

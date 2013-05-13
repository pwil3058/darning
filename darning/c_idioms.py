### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
### Copyright (C) 2007 Nicolas Pitre <nico@fluxnic.net>
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
Provide tools to support C idioms such as pointer arithmetic.
This allows implementation (in Python) of algorithms published in C
in a way that resembles the original and makes updating for changes in
the original easier.
'''

import copy

# 'C' algorithm often rely on unsigned overflow but
# Python extends rather than overflowing so we need to lop off the
# extra bits where appropriate
class _UintWrapper(object):
    MAX = None
    def __init__(self, value=0):
        assert value >= 0
        self._value = value & self.MAX
    # Unary functions that return a value of our type
    def __abs__(self): return self.__class__(int.__abs__(self._value))
    def __invert__(self): return self.__class__(int.__invert__(self._value))
    def __neg__(self): return self.__class__(int.__neg__(self._value))
    def __pos__(self): return self.__class__(int.__pos__(self._value))
    # Unary functions that return a value NOT of our type
    def __int__(self): return self._value
    def __float__(self): return int.__float__(self._value)
    def __hash__(self): return int.__hash__(self._value)
    def __hex__(self): return int.__hex__(self._value)
    def __index__(self): return int.__index__(self._value)
    def __long__(self): return int.__long__(self._value)
    def __nonzero__(self): return int.__nonzero__(self._value)
    def __oct__(self): return int.__oct__(self._value)
    def __repr__(self): return int.__repr__(self._value)
    def __sizeof__(self): return int.__sizeof__(self._value)
    def __str__(self): return int.__str__(self._value)
    def __trunc__(self): return int.__trunc__(self._value)
    # Binary functions that return a value of our type
    def __add__(self, other): return self.__class__(int.__add__(self._value, int(other)))
    def __and__(self, other): return self.__class__(int.__and__(self._value, int(other)))
    def __cmp__(self, other): return self.__class__(int.__cmp__(self._value, int(other)))
    def __div__(self, other): return self.__class__(int.__div__(self._value, int(other)))
    def __divmod__(self, other):
        div, rem = int.__divmod__(self._value, int(other))
        return self.__class__(div), self.__class__(rem)
    def __floordiv__(self, other): return self.__class__(int.__floordiv__(self._value, int(other)))
    def __lshift__(self, other): return self.__class__(int.__lshift__(self._value, int(other)))
    def __mod__(self, other): return self.__class__(int.__mod__(self._value, int(other)))
    def __mul__(self, other): return self.__class__(int.__mul__(self._value, int(other)))
    def __or__(self, other): return self.__class__(int.__or__(self._value, int(other)))
    def __pow__(self, other): return self.__class__(int.__pow__(self._value, int(other)))
    def __sub__(self, other): return self.__class__(int.__sub__(self._value, int(other)))
    def __xor__(self, other): return self.__class__(int.__xor__(self._value, int(other)))
    def __truediv__(self, other): return self.__class__(int.__truediv__(self._value, int(other)))
    # Binary functions that return a value NOT of our type
    def __radd__(self, other): return int.__radd__(self._value, int(other))
    def __rand__(self, other): return int.__rand__(self._value, int(other))
    def __rdiv__(self, other): return int.__rdiv__(self._value, int(other))
    def __rdivmod__(self, other): return int.__rdivmod__(self._value, int(other))
    def __rfloordiv__(self, other): return int.__rfloordiv__(self._value, int(other))
    def __rlshift__(self, other): return int.__rlshift__(self._value, int(other))
    def __rmod__(self, other): return int.__rmod__(self._value, int(other))
    def __rmul__(self, other): return int.__rmul__(self._value, int(other))
    def __ror__(self, other): return int.__ror__(self._value, int(other))
    def __rpow__(self, other): return int.__rpow__(self._value, int(other))
    def __rrshift__(self, other): return int.__rrshift__(self._value, int(other))
    def __rshift__(self, other): return int.__rshift__(self._value, int(other))
    def __rsub__(self, other): return int.__rsub__(self._value, int(other))
    def __rtruediv__(self, other): return int.__rtruediv__(self._value, int(other))
    def __rxor__(self, other): return int.__rxor__(self._value, int(other))
    # Ones to ignore (hopefully __getattr__() will handle them OK.
    #def __class__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __coerce__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __delattr__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __doc__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __format__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __getattribute__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __getnewargs__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __new__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __reduce__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __reduce_ex__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __setattr__(self, other): return self.__class(int.__op__(self._value, int(other)))
    #def __subclasshook__(self, other): return self.__class(int.__op__(self._value, int(other)))
    def __getattr__(self, attrname):
        return getattr(int, attrname)

class Uint8(_UintWrapper):
    MAX = 0xFF
    def __init__(self, value=0):
        _UintWrapper.__init__(self, value)

class Uint16(_UintWrapper):
    MAX = 0xFFFF
    def __init__(self, value=0):
        _UintWrapper.__init__(self, value)

class Uint32(_UintWrapper):
    MAX = 0xFFFFFFFF
    def __init__(self, value=0):
        _UintWrapper.__init__(self, value)

class Uint64(_UintWrapper):
    MAX = 0xFFFFFFFFFFFFFFFF
    def __init__(self, value=0):
        _UintWrapper.__init__(self, value)

class Sequence(object):
    '''
    A wrapper for sequence objects that makes them more C like.
    Basically disable Python negative index mechanism and disallow
    access outside the wrapped sequence's bounds.
    This should catch errors in translating algorithms that assume C
    behaviour.
    '''
    def __init__(self, wrapped):
        self.wrapped = wrapped
    def _check_key(self, key):
        if isinstance(key, slice):
            if key.start is not None and key.start < 0:
                raise IndexError
            if key.stop is not None and (key.stop < 0 or key.stop > len(self.wrapped)):
                    raise IndexError
        elif key < 0:
            raise IndexError
    def __getitem__(self, key):
        self._check_key(key)
        return self.wrapped.__getitem__(key)
    def __setitem__(self, key, arg):
        self._check_key(key)
        self.wrapped.__setitem__(key, arg)
    def __len__(self):
        return len(self.wrapped)
    def __getattr__(self, attrname):
        return getattr(self.wrapped, attrname)

class Pointer(object):
    '''
    An offset window to a sequence object (e.g. list, tuple).
    Useful for implementing algorithms designed using C pointer
    arithmmetic to process arrays.  But with the advantage of bounds
    checking.  Negative indices are relative to offset not the end
    of the wrapped object.
    '''
    def __init__(self, wrapped, start=0):
        self.wrapped = Sequence(wrapped)
        self.offset = start
    def copy(self):
        return copy.copy(self)
    def copy_then_incr(self):
        ret = self.copy()
        self.offset += 1
        return ret
    def copy_then_decr(self):
        ret = self.copy()
        self.offset -= 1
        return ret
    def incr_then_copy(self):
        self.offset += 1
        return self.copy()
    def decr_then_copy(self, count=None):
        self.offset -= 1
        return self.copy()
    def get(self):
        return self.wrapped[self.offset]
    def get_then_incr(self, count=None):
        if count is None:
            try:
                ret = self.wrapped[self.offset]
            except IndexError:
                raise StopIteration
            self.offset += 1
        else:
            assert count >= 0
            start = self.offset
            self.offset += count
            ret = self.wrapped[start:self.offset]
        return ret
    def get_then_decr(self):
        try:
            ret = self.wrapped[self.offset]
        except IndexError:
            raise StopIteration
        self.offset -= 1
        return ret
    def incr_then_get(self):
        self.offset += 1
        try:
            ret = self.wrapped[self.offset]
        except IndexError:
            raise StopIteration
        return ret
    def decr_then_get(self, count=None):
        if count is None:
            self.offset -= 1
            try:
                ret = self.wrapped[self.offset]
            except IndexError:
                raise StopIteration
        else:
            assert count >= 0
            stop = self.offset
            self.offset -= count
            ret = self.wrapped[self.offset:self.offset + count]
        return ret
    def _shift_slice(self, key):
        # start/stop are relative to offset regardless of sign
        start = self.offset if key.start is None else self.offset + key.start
        stop = None if key.stop is None else self.offset + key.stop
        return slice(start, stop, key.step)
    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.wrapped.__getitem__(self._shift_slice(key))
        else:
            return self.wrapped[self.offset + key]
    def __setitem__(self, key, arg):
        if isinstance(key, slice):
            self.wrapped.__setitem__(self._shift_slice(key), arg)
        else:
            self.wrapped[self.offset + key] = arg
    def __add__(self, arg):
        new_ptr = self.copy()
        new_ptr += arg
        return new_ptr
    def __sub__(self, arg):
        new_ptr = self.copy()
        new_ptr -= arg
        return new_ptr
    def __iadd__(self, arg):
        self.offset += arg
        return self
    def __isub__(self, arg):
        self.offset -= arg
        return self
    def __int__(self):
        return self.offset
    def __len__(self):
        return len(self.wrapped) - self.offset
    def __nonzero__(self):
        # For use by Python < 3.0
        return 0 <= self.offset and self.offset < len(self.wrapped)
    def __bool__(self):
        # For use by Python >= 3.0
        return self.__nonzero__()

class Index(object):
    def __init__(self, start=0):
        self.value = int(start)
    def incr(self):
        ret = self.value
        self.value += 1
        return ret
    def decr(self):
        ret = self.value
        self.value -= 1
        return ret
    def __getattr__(self, attrname):
        return getattr(self.value, attrname)
    def __iadd__(self, arg):
        self.value += arg
        return self
    def __isub__(self, arg):
        self.value -= arg
        return self
    def __int__(self):
        return self.value
    def __nonzero__(self):
        return self.value != 0
    def __bool__(self):
        return self.__nonzero__()

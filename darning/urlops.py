### Copyright (C) 2009 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Provide URL operations in a way compatible with both Python 2 and 3"""

_USE_URLPARSE = True
try:
    import urlparse
except ImportError:
    _USE_URLPARSE = False
    import urllib.parse

def parse_url(path, scheme="", allow_fragments=True):
    """Return ParseResult for the given path"""
    if _USE_URLPARSE:
        return urlparse.urlparse(path, scheme, allow_fragments)
    else:
        return urllib.parse.urlparse(path, scheme, allow_fragments)

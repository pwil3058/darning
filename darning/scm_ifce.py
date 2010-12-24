### Copyright (C) 2010 Peter Williams <peter_ono@users.sourceforge.net>
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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''
Provide an interface to SCM controlling source on which patches sit
ONLY A DUMMY interface for the time being.
'''

def get_revision(filename=None):
    '''
    Return the SCM revision for the named file or the whole playground
    if the filename is None
    '''
    # Always return None for the time being
    if filename is None or len(filename) >= 0:
        return None
    return True

def has_uncommitted_change(filename):
    '''
    Does the SCM have uncommitted changes for the named file?
    '''
    # Always return False for the time being (assuming a filename is given)
    if filename is None or len(filename) == 0:
        return True
    return False

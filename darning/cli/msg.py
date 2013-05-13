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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

'''Standardize CLI error, warning and info messages'''

import sys

OK = 0
ERROR = 1

def Info(template, *args):
    '''Print an message to stdout and return OK'''
    if len(args) == 0:
        sys.stdout.write(template + '\n')
    else:
        sys.stdout.write(template.format(*args) + '\n')
    return OK

def Warn(template, *args):
    '''Print an message to stderr and return OK'''
    sys.stderr.write(_('Warning: '))
    if len(args) == 0:
        sys.stderr.write(template + '\n')
    else:
        sys.stderr.write(template.format(*args) + '\n')
    return OK

def Error(template, *args):
    '''Print an message to stderr and return ERROR'''
    sys.stderr.write(_('Error: '))
    if len(args) == 0:
        sys.stderr.write(str(template) + '\n')
    else:
        sys.stderr.write(template.format(*args) + '\n')
    return ERROR

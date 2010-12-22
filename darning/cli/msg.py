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

'''Standardize CLI error, warning and info messages'''

import sys

OK = 0
ERROR = 1

def Info(template, *args):
    if len(args) == 0:
        sys.stdout.write(template + '\n')
    else:
        sys.stdout.write(template.format(*args) + '\n')
    return OK

def Warning(template, *args):
    sys.stderr.write('Warning: ')
    if len(args) == 0:
        sys.stderr.write(template + '\n')
    else:
        sys.stderr.write(template.format(*args) + '\n')
    return OK

def Error(template, *args):
    sys.stderr.write('Error: ')
    if len(args) == 0:
        sys.stderr.write(template + '\n')
    else:
        sys.stderr.write(template.format(*args) + '\n')
    return ERROR

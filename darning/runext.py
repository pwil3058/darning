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

'''Run external commands and capture their output'''

import os
import signal
import subprocess
import collections

Result = collections.namedtuple('Result', ['ecode', 'stdout', 'stderr'])

def run_cmd(cmd, input_text=None):
    '''Run the given external command and return the results'''
    is_posix = os.name == 'posix'
    if is_posix:
        savedsh = signal.getsignal(signal.SIGPIPE)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    sub = subprocess.Popen(cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, close_fds=is_posix, bufsize=-1)
    outd, errd = sub.communicate(input_text)
    if is_posix:
        signal.signal(signal.SIGPIPE, savedsh)
    return Result(ecode=sub.returncode, stdout=outd, stderr=errd)

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

'''Run external commands and capture their output'''

import os
import signal
import subprocess
import collections
import shlex
import gobject

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

def run_cmd_in_bgnd(cmd):
    """Run the given command in the background and poll for its exit using
    _wait_for_bgnd_timeout() as a callback.
    """
    def _wait_for_bgnd_cmd_timeout(pid):
        """Callback to clean up after background tasks complete"""
        try:
            if os.name == 'nt' or os.name == 'dos':
                rpid, _dummy= os.waitpid(pid, 0)
            else:
                rpid, _dummy= os.waitpid(pid, os.WNOHANG)
            return rpid != pid
        except OSError:
            return False
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if not cmd:
        return False
    pid = subprocess.Popen(cmd).pid
    if not pid:
        return False
    gobject.timeout_add(2000, _wait_for_bgnd_cmd_timeout, pid)
    return True

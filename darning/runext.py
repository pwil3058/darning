### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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
import shlex
import gobject
import gtk
import select

from .cmd_result import CmdResult, CmdFailure

def run_cmd(cmd, input_text=None, sanitize_stderr=None):
    '''Run the given external command and return the results'''
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
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
    return CmdResult(ecode=sub.returncode, stdout=outd, stderr=errd).mapped_for_warning(sanitize_stderr=sanitize_stderr)

def run_get_cmd(cmd, input_text=None, sanitize_stderr=None, default=CmdFailure, do_rstrip=True):
    result = run_cmd(cmd, input_text=input_text, sanitize_stderr=sanitize_stderr)
    if not result.is_ok:
        if default is CmdFailure:
            raise CmdFailure(result.msg)
        else:
            return default
    return result.stdout.rstrip() if do_rstrip else result.stdout

def run_cmd_in_console(console, cmd, input_text=None, sanitize_stderr=None):
    """Run the given command in the given console and report the outcome as a
    Result tuple.
    If input_text is not None pas it to the command as standard input.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if os.name == 'nt' or os.name == 'dos':
        return run_cmd_in_console_nt(console, cmd, input_text=input_text, sanitize_stderr=sanitize_stderr)
    is_posix = os.name == 'posix'
    if is_posix:
        savedsh = signal.getsignal(signal.SIGPIPE)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    # TODO: fix command string written to console for spaces in components
    console.start_cmd(' '.join(cmd) + "\n")
    while gtk.events_pending():
        gtk.main_iteration()
    try:
        # we need to catch OSError if command is unknown
        sub = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
              stderr=subprocess.PIPE, close_fds=is_posix, bufsize=-1)
        if input_text is not None:
            sub.stdin.write(input_text)
            console.append_stdin(input_text)
        sub.stdin.close()
        stdout_eof = stderr_eof = False
        outd = errd = ""
        while True:
            to_check_in = [sub.stdout] * (not stdout_eof) + \
                          [sub.stderr] * (not stderr_eof)
            ready = select.select(to_check_in, [], [], 0)
            if sub.stdout in ready[0]:
                ochunk = sub.stdout.readline()
                if ochunk == '':
                    stdout_eof = True
                else:
                    console.append_stdout(ochunk)
                    outd += ochunk
            if sub.stderr in ready[0]:
                echunk = sub.stderr.readline()
                if echunk == '':
                    stderr_eof = True
                else:
                    console.append_stderr(echunk)
                    errd += echunk
            while gtk.events_pending():
                gtk.main_iteration()
            if stdout_eof and stderr_eof:
                break
        sub.wait()
        result = CmdResult(ecode=sub.returncode, stdout=outd, stderr=errd)
    except OSError as edata:
        emsg = "{0}: [Error {1}] {2}\n".format(cmd[0], edata.errno, edata.strerror)
        console.append_stderr(emsg)
        result = CmdResult(ecode=edata.errno, stdout="", stderr=emsg)
    console.end_cmd()
    if is_posix:
        signal.signal(signal.SIGPIPE, savedsh)
    return result.mapped_for_warning(sanitize_stderr=sanitize_stderr)

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

if os.name == 'nt' or os.name == 'dos':
    def run_cmd_in_console_nt(console, cmd, input_text=None, sanitize_stderr=None):
        """Run the given command in the given console and report the
        outcome as a CmdResult tuple.
        If input_text is not None pas it to the command as standard input.
        """
        console.start_cmd((cmd if isinstance(cmd, str) else " ".join(cmd)) + "\n")
        if input_text is not None:
            console.append_stdin(input_text)
        result = run_cmd(cmd, input_text=input_text)
        console.append_stdout(result.stdout)
        console.append_stderr(result.stderr)
        console.end_cmd()
        return result.mapped_for_warning(sanitize_stderr=sanitize_stderr)

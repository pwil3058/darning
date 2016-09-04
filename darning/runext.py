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
import select

from . import CmdResult, CmdFailure

IS_POSIX = os.name == "posix"
IS_MSFT = os.name == "nt" or os.name == "dos"

if IS_MSFT:
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    def run_cmd(cmd, input_text=None, sanitize_stderr=None, decode_stdout=True):
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        sub = subprocess.Popen(cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=IS_POSIX, bufsize=-1,
            startupinfo=startupinfo)
        outd, errd = sub.communicate(input_text)
        return CmdResult(ecode=sub.returncode, stdout=outd.decode() if decode_stdout else outd, stderr=errd.decode()).mapped_for_warning(sanitize_stderr=sanitize_stderr)

    def run_cmd_in_console(console, cmd, input_text=None, sanitize_stderr=None):
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        console.start_cmd((cmd if isinstance(cmd, str) else " ".join(cmd)) + "\n")
        if input_text is not None:
            console.append_stdin(input_text)
        result = run_cmd(cmd, input_text=input_text)
        console.append_stdout(result.stdout)
        console.append_stderr(result.stderr)
        console.end_cmd()
        return result.mapped_for_warning(sanitize_stderr=sanitize_stderr)
else:
    def run_cmd(cmd, input_text=None, sanitize_stderr=None, decode_stdout=True):
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        if IS_POSIX:
            savedsh = signal.getsignal(signal.SIGPIPE)
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        sub = subprocess.Popen(cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=IS_POSIX, bufsize=-1)
        outd, errd = sub.communicate(input_text)
        if IS_POSIX:
            signal.signal(signal.SIGPIPE, savedsh)
        return CmdResult(ecode=sub.returncode, stdout=outd.decode() if decode_stdout else outd, stderr=errd.decode()).mapped_for_warning(sanitize_stderr=sanitize_stderr)

    def run_cmd_in_console(console, cmd, input_text=None, sanitize_stderr=None):
        from .utils import quote_if_needed
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        if IS_POSIX:
            savedsh = signal.getsignal(signal.SIGPIPE)
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        console.start_cmd(" ".join((quote_if_needed(s) for s in cmd)) + "\n")
        try:
            # we need to catch OSError if command is unknown
            sub = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, close_fds=IS_POSIX, bufsize=-1)
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
                    ochunk = sub.stdout.readline().decode()
                    if ochunk == "":
                        stdout_eof = True
                    else:
                        console.append_stdout(ochunk)
                        outd += ochunk
                if sub.stderr in ready[0]:
                    echunk = sub.stderr.readline().decode()
                    if echunk == "":
                        stderr_eof = True
                    else:
                        console.append_stderr(echunk)
                        errd += echunk
                if stdout_eof and stderr_eof:
                    break
            sub.wait()
            result = CmdResult(ecode=sub.returncode, stdout=outd, stderr=errd)
        except OSError as edata:
            emsg = "{0}: [Error {1}] {2}\n".format(cmd[0], edata.errno, edata.strerror)
            console.append_stderr(emsg)
            result = CmdResult(ecode=edata.errno, stdout="", stderr=emsg)
        console.end_cmd()
        if IS_POSIX:
            signal.signal(signal.SIGPIPE, savedsh)
        return result.mapped_for_warning(sanitize_stderr=sanitize_stderr)

def run_get_cmd(cmd, input_text=None, sanitize_stderr=None, default=CmdFailure, do_rstrip=True, decode_stdout=True):
    result = run_cmd(cmd, input_text=input_text, sanitize_stderr=sanitize_stderr, decode_stdout=decode_stdout)
    if not result.is_ok:
        if default is CmdFailure:
            raise CmdFailure(result.msg)
        else:
            return default
    return result.stdout.rstrip() if (decode_stdout and do_rstrip) else result.stdout

def run_do_cmd(console, cmd, input_text=None, sanitize_stderr=None, suggestions=None):
    result = run_cmd_in_console(console=console, cmd=cmd, input_text=input_text, sanitize_stderr=sanitize_stderr)
    return result.mapped_for_suggestions(suggestions if suggestions else [])

def run_cmd_in_bgnd(cmd):
    """Run the given command in the background and poll for its exit using
    _wait_for_bgnd_timeout() as a callback.
    """
    from gi.repository import GObject
    def _wait_for_bgnd_cmd_timeout(pid):
        """Callback to clean up after background tasks complete"""
        try:
            if os.name == "nt" or os.name == "dos":
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
    if IS_MSFT:
        pid = subprocess.Popen(cmd, startupinfo=startupinfo).pid
    else:
        pid = subprocess.Popen(cmd).pid
    if not pid:
        return False
    GObject.timeout_add(2000, _wait_for_bgnd_cmd_timeout, pid)
    return True

# Some generalized lambdas to assisting in constructing commands
OPTNL_FLAG = lambda val, flag: [flag] if val else []
OPTNL_FLAGS = lambda val, flags: flags if val else []
OPTNL_FLAG_WITH_ARG = lambda flag, arg: [flag, arg] if arg is not None else []
OPTNL_ARG = lambda arg: [arg] if arg is not None else []
OPTNL_ARG_LIST = lambda arg_list: arg_list if arg_list is not None else []

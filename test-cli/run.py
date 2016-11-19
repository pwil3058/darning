#!/usr/bin/python3
### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
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

import shlex
import re
import subprocess
import os
import sys
import signal
import argparse
import tempfile
import atexit
import shutil

class Result(object):
    @staticmethod
    def _convert_std_arg(arg):
        if arg is None:
            return list()
        elif isinstance(arg, bytes):
            return arg.decode().splitlines()
        elif isinstance(arg, str):
            return arg.splitlines()
        else:
            return arg
    def __init__(self, ecode=0, stdout=None, stderr=None):
        self.ecode = ecode
        self.stdout = self._convert_std_arg(stdout)
        self.stderr = self._convert_std_arg(stderr)
    def __eq__(self, other):
        if self.ecode != other.ecode:
            return False
        if self.stdout != other.stdout:
            return False
        if self.stderr != other.stderr:
            return False
        return True

class Command(object):
    IS_POSIX = os.name == "posix"
    def __init__(self, arg):
        self.cmd_line_str = arg
        assert self.cmd_line_str
        self.cmd_line = shlex.split(self.cmd_line_str)
        self.input_text = ""
        try:
            red_index = self.cmd_line.index(">")
            self.red_file_path = self.cmd_line[red_index + 1]
            del self.cmd_line[red_index:red_index + 2]
        except:
            self.red_file_path = None
    def __str__(self):
        return self.cmd_line_str
    def append_input_line(self, line):
        self.input_text += line + "\n"
    def _run(self):
        if self.IS_POSIX:
            savedsh = signal.getsignal(signal.SIGPIPE)
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        sub = subprocess.Popen(self.cmd_line, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
              stderr=subprocess.PIPE, close_fds=self.IS_POSIX, bufsize=-1)
        sout, serr = sub.communicate(self.input_text)
        if self.IS_POSIX:
            signal.signal(signal.SIGPIPE, savedsh)
        if self.red_file_path:
            open(self.red_file_path, "wb").write(sout)
            sout = ""
        return Result(ecode=sub.returncode, stdout=sout, stderr=serr)
    def run(self):
        if self.cmd_line[0] == "umask":
            os.umask(int(self.cmd_line[1], 8))
        elif self.cmd_line[0] == "cd":
            try:
                os.chdir(self.cmd_line[1])
                os.environ["PWD"] = os.getcwd()
            except OSError as edata:
                return Result(ecode=1, stderr=str(edata))
        elif self.cmd_line[0] == "export":
            ename, evalue = self.cmd_line[1].split("=")
            os.environ[ename] = evalue
        elif self.cmd_line[0] == "unset":
            if self.cmd_line[0] in os.environ:
                del os.environ[self.cmd_line[0]]
        elif self.cmd_line[0] == "mkfile":
            if len(self.cmd_line) == 2:
                try:
                    open(self.cmd_line[1], "w").write(self.input_text)
                except OSError as edata:
                    return Result(ecode=1, stderr=str(edata))
            if len(self.cmd_line) == 3:
                if self.cmd_line[1] != "-b":
                    return Result(ecode=1, stderr="mkfile: Unrecognized option: {0}.".format(self.cmd_line[1]))
                # For the time being just stick a char 0 in the middle
                midpoint = len(self.input_text) // 2
                data = self.input_text[:midpoint] + "\000" + self.input_text[midpoint:]
                try:
                    open(self.cmd_line[2], "wb").write(data.encode())
                except OSError as edata:
                    return Result(ecode=1, stderr=str(edata))
            else:
                Result(ecode=1, stderr="mkfile: Missing file name.")
        elif self.cmd_line[0] == "create_file_tree":
            for dindex in range(6):
                if dindex:
                    dname = "dir{0}/".format(dindex)
                    os.mkdir(dname)
                else:
                    dname = ""
                for sdindex in range(6):
                    if sdindex:
                        if not dindex:
                            continue
                        sdname = "subdir{0}/".format(sdindex)
                        os.mkdir(dname + sdname)
                    else:
                        sdname = ""
                    for findex in range(1, 6):
                        tfpath = dname + sdname + "file{0}".format(findex)
                        open(tfpath, "w").write("{0}:\nis a text file.\n".format(tfpath))
                        bfpath = dname + sdname + "binary{0}".format(findex)
                        open(bfpath, "w").write("{0}:\000is a binary file.\n".format(bfpath))
        else:
            try:
                return self._run()
            except OSError as edata:
                return Result(stderr=str(edata))
        return Result()

if sys.stderr.isatty():
    def green(text):
        return "\033[32m" + text + "\033[m"
    def red(text):
        return "\033[31m" + text + "\033[m"
else:
    def red(text):
        return text
    def green(text):
        return text

class ParseError(Exception): pass

class Test(object):
    LINE_CRE = re.compile("^\s*([$<>!?]) ?(.*)")
    @staticmethod
    def get_next_test(lines, index):
        test = None
        while index < len(lines):
            match = Test.LINE_CRE.match(lines[index])
            if match:
                token, line = match.groups()
                if token == "$":
                    index += 1
                    test = Test(index, line)
                    break
                else:
                    raise ParseError('{0}: unexpected "{1}"'.format(index, match[1]))
            index += 1
        if not test:
            return (test, index)
        while index < len(lines):
            match = Test.LINE_CRE.match(lines[index])
            if match:
                token, line = match.groups()
                if token == "$":
                    break
                elif token == "<":
                    test.command.append_input_line(line)
                elif token == ">":
                    test.expected.stdout.append(line)
                elif token == "!":
                    test.expected.stderr.append(line)
                elif token == "?":
                    test.expected.ecode = int(line)
                else:
                    raise ParseError('{0}: unexpected "{1}"'.format(index, token))
            index += 1
        return (test, index)
    @staticmethod
    def parse_text(text):
        lines = text.splitlines()
        index = 0
        tests = []
        while index < len(lines):
            test, index = Test.get_next_test(lines, index)
            if test is not None:
                tests.append(test)
        return tests
    def __init__(self, line_no, command_line_str):
        self.line_no = line_no
        self.command = Command(command_line_str)
        self.expected = Result()
        self.result = None
    def execute(self):
        self.result = self.command.run()
        return self.result == self.expected
    def report_details(self):
        def report_lists(prefix, left, right):
            for index in range(min(len(left), len(right))):
                if left[index] == right[index]:
                    sys.stdout.write("{0}: {1} == {2}\n".format(prefix, left[index], right[index]))
                else:
                    sys.stdout.write(red("{0}: {1} != {2}\n".format(prefix, left[index], right[index])))
            if len(left) > len(right):
                for line in left[len(right):]:
                    sys.stdout.write(red("{0}: {1} != \n".format(prefix, line)))
            elif len(left) < len(right):
                for line in right[len(left):]:
                    sys.stdout.write(red("{0}: != {1}\n".format(prefix, line)))
        if self.result.ecode == self.expected.ecode:
            sys.stdout.write("RETN: {0} == {1}\n".format(self.result.ecode, self.expected.ecode))
        else:
            sys.stdout.write(red("RETN: {0} != {1}\n".format(self.result.ecode, self.expected.ecode)))
        report_lists("SOUT", self.result.stdout, self.expected.stdout)
        report_lists("SERR", self.result.stderr, self.expected.stderr)
    def report(self, quiet=False, verbose=False):
        if self.result == self.expected:
            sys.stdout.write("[{0}] {1} [{2}]\n".format(self.line_no, str(self.command), green("OK")))
            if verbose:
                self.report_details()
        else:
            sys.stdout.write("[{0}] {1} [{2}]\n".format(self.line_no, str(self.command), red("ERROR")))
            if not quiet:
                self.report_details()


PARSER = argparse.ArgumentParser(description="Run and evaluate a test script.")

PARSER.add_argument(
    "arg_script_file",
    metavar="script",
    help="name of the file containing the script to be run.",
)

PARSER.add_argument(
    "-q", "--quiet",
    dest="opt_quiet",
    action="store_true",
    help="operate in quiet mode.",
)

PARSER.add_argument(
    "-v", "--verbose",
    dest="opt_verbose",
    action="store_true",
    help="operate in verbose mode.",
)
# Main program starts here
args = PARSER.parse_args()

TESTS = Test.parse_text(open(args.arg_script_file).read())
HEADER = args.arg_script_file

ORIGDIR = os.getcwd()
WORKDIR = tempfile.mkdtemp()
os.chdir(WORKDIR)
os.environ["PWD"] = os.getcwd()
atexit.register(shutil.rmtree, WORKDIR)

fail_count = 0
for test in TESTS:
    if test.execute() == False:
        fail_count += 1

if fail_count == 0:
    sys.stdout.write("{0} [{1}]\n".format(HEADER, green("PASSED")))
    if args.opt_verbose:
        for test in TESTS:
            test.report(quiet=args.opt_quiet, verbose=args.opt_verbose)
    sys.exit(0)

sys.stdout.write("{0} [{1}]\n".format(HEADER, red("FAILED")))
for test in TESTS:
    test.report(quiet=args.opt_quiet, verbose=args.opt_verbose)
sys.exit(1)

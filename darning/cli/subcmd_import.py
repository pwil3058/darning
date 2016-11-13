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

'''Import an external patch and place it in the series behind the current top patch.'''

import os
import sys

from ..bab import CmdResult

from ..patch_diff import patchlib

from . import cli_args
from . import db_utils

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'import',
    description=_('''Import an external patch and place it in the series
        after the current top patch. Unless otherwise specified the
        name of the imported file will be used as the patch name.'''),
)

PARSER.add_argument(
    '--as',
    help=_('the name to be assigned to the imported patch.'),
    dest = 'patchname',
    metavar=_('patch'),
)

PARSER.add_argument(
    '-p',
    help=_('the number of path components to be stripped from file paths.'),
    dest = 'opt_strip_level',
    metavar=_('strip_level'),
    choices = ['0', '1'],
)

PARSER.add_argument(
    'patchfile',
    help=_('the name of the patch file to be imported.'),
)

def run_import(args):
    '''Execute the "import" sub command using the supplied args'''
    PM = db_utils.get_pm_db()
    db_utils.set_report_context(verbose=True)
    if not args.patchname:
        args.patchname = os.path.basename(args.patchfile)
    try:
        epatch = patchlib.Patch.parse_text(open(args.patchfile).read())
    except patchlib.ParseError as edata:
        if edata.lineno is None:
            sys.stderr.write(_('Parse Error: {0}.\n').format(edata.message))
        else:
            sys.stderr.write(_('Parse Error: {0}: {1}.\n').format(edata.lineno, edata.message))
        return CmdResult.ERROR
    except IOError as edata:
        if edata.filepath is None:
            sys.stderr.write(_('IO Error: {0}.\n').format(edata.strerror))
        else:
            sys.stderr.write(_('IO Error: {0}: {1}.\n').format(edata.strerror, edata.filepath))
        return CmdResult.ERROR
    if args.opt_strip_level is None:
        args.opt_strip_level = epatch.estimate_strip_level()
        if args.opt_strip_level is None:
            sys.stderr.write(_('Strip level auto detection failed.  Please use -p option.'))
            return CmdResult.ERROR
    epatch.set_strip_level(int(args.opt_strip_level))
    eflags = PM.do_import_patch(epatch, args.patchname)
    if eflags & CmdResult.ERROR:
        return eflags
    sys.stdout.write(_('Imported "{0}" as patch "{1}".\n').format(args.patchfile, args.patchname))
    return eflags

PARSER.set_defaults(run_cmd=run_import)

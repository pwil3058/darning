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

'''Import an external patch and place it in the series behind the current top patch.'''

import os

from darning import patch_db
from darning import patchlib
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'import',
    description='''Import an external patch and place it in the series
        after the current top patch. Unless otherwise specified the
        name of the imported file will be used as the patch name.''',
)

PARSER.add_argument(
    '--as',
    help='the name to be assigned to the imported patch.',
    dest = 'patchname',
    metavar = 'patch',
)

PARSER.add_argument(
    '-p',
    help='the number of path components to be stripped from file paths.',
    dest = 'opt_strip_level',
    metavar = 'strip_level',
    choices = ['0', '1'],
)

PARSER.add_argument(
    'patchfile',
    help='the name of the patch file to be imported.',
)

def run_import(args):
    '''Execute the "import" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if not args.patchname:
        args.patchname = os.path.basename(args.patchfile)
    if patch_db.patch_is_in_series(args.patchname):
        return msg.Error('patch "{0}" already exists', args.patchname)
    try:
        epatch = patchlib.Patch.parse_text(open(args.patchfile).read())
    except patchlib.ParseError as edata:
        if edata.lineno is None:
            return msg.Error(edata.message)
        else:
            return msg.Error('{0}: Line:{1}.', edata.message, edata.lineno)
    except IOError as edata:
        if edata.filename is None:
            return msg.Error(edata.strerror)
        else:
            return msg.Error('{0}: {1}.', edata.strerror, edata.filename)
    if args.opt_strip_level is None:
        args.opt_strip_level = epatch.estimate_strip_level()
        if args.opt_strip_level is None:
            return msg.Error('Strip level auto detection failed.  Please use -p option.')
    epatch.set_strip_level(int(args.opt_strip_level))
    patch_db.import_patch(epatch, args.patchname)
    warn = patch_db.top_patch_needs_refresh()
    if warn:
        old_top = patch_db.get_top_patch_name()
    msg.Info('Imported "{0}" as patch "{1}".', args.patchfile, args.patchname)
    if warn:
        msg.Warn('Previous top patch ("{0}") needs refreshing.', old_top)
    return msg.OK

PARSER.set_defaults(run_cmd=run_import)

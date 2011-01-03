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

'''Unapply the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'refresh',
    description='Refresh the top (or nominated) patch.',
)

cli_args.add_patch_option(PARSER, helptext='the name of the patch to be refreshed.')

def run_refresh(args):
    '''Execute the "refresh" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if not args.opt_patch:
        args.opt_patch = patch_db.get_top_patch_name()
        if not args.opt_patch:
            return msg.Error('No patches applied')
    elif not patch_db.patch_is_in_series(args.opt_patch):
        return msg.Error('patch "{0}" is unknown', args.opt_patch)
    results = patch_db.do_refresh_patch(args.opt_patch)
    highest_ecode = 0
    for filename in results:
        result = results[filename]
        highest_ecode = highest_ecode if result.ecode < highest_ecode else result.ecode
        for line in result.stdout.splitlines(False):
            msg.Info(line)
        if result.ecode in [0, 1]:
            for line in result.stderr.splitlines(False):
                msg.Warn(line)
        else:
            for line in result.stderr.splitlines(False):
                msg.Error(line)
    if highest_ecode > 1:
        return msg.Error('Patch "{0}" requires another refresh after issues are resolved.', args.opt_patch)
    return msg.Info('Patch "{0}" refreshed.', args.opt_patch)

PARSER.set_defaults(run_cmd=run_refresh)

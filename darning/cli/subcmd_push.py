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

'''Apply the next patch in the series.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'push',
    description='Apply the next patch in the series.',
)

cli_args.add_force_option(PARSER, helptext='incorporate uncommitted/unrefreshed changes to overlapped files into the pushed patch.')

def run_push(args):
    '''Execute the "push" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if not patch_db.is_pushable():
        top_patch = patch_db.get_top_patch_name()
        if top_patch:
            return msg.Error('no pushable patches. "{0}" is on top.', top_patch)
        else:
            return msg.Error('no pushable patches.')
    is_ok = True
    if args.opt_force:
        ol_report = msg.Info
    else:
        ol_report = msg.Error
    overlaps = patch_db.get_next_patch_overlap_data()
    if len(overlaps.uncommitted) > 0:
        is_ok = False
        ol_report('The following (overlapped) files have uncommitted SCM changes:')
        for filename in sorted(overlaps.uncommitted):
            ol_report('\t{0}', filename)
    if len(overlaps.unrefreshed) > 0:
        is_ok = False
        ol_report('The following (overlapped) files have unrefreshed changes (in an applied patch):')
        for filename in sorted(overlaps.unrefreshed):
            ol_report('\t{0} : in patch "{1}"', filename, overlaps.unrefreshed[filename])
    if not is_ok:
        if args.opt_force:
            msg.Info('Uncommited/unrefreshed changes incorporated into pushed patch.')
        else:
            return msg.Error('Aborting')
    _db_ok, results = patch_db.apply_patch(force=args.opt_force)
    highest_ecode = 0
    for filename in results:
        result = results[filename]
        highest_ecode = highest_ecode if result.ecode < highest_ecode else result.ecode
        for line in result.stdout.splitlines(False):
            msg.Info(line)
        if result.ecode == 0:
            for line in result.stderr.splitlines(False):
                msg.Warn(line)
        else:
            for line in result.stderr.splitlines(False):
                msg.Error(line)
    msg.Info('Patch "{0}" is now on top.', patch_db.get_top_patch_name())
    if highest_ecode > 1:
        return msg.Error('A refresh is required after issues are resolved.')
    if highest_ecode > 0:
        return msg.Error('A refresh is required.')
    return msg.OK

PARSER.set_defaults(run_cmd=run_push)

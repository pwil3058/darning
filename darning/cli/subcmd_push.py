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

'''Apply the next patch in the series.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'push',
    description='Apply the next patch in the series.',
)

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
    overlaps = patch_db.get_next_patch_overlap_data()
    if len(overlaps.uncommitted) > 0:
        is_ok = False
        msg.Error('The following (overlapped) files have uncommited SCM changes:')
        for filename in sorted(overlaps.uncommitted):
            msg.Error('\t{0}', filename)
    if len(overlaps.unrefreshed) > 0:
        is_ok = False
        msg.Error('The following (overlapped) files have unrefreshed changes (in an applied patch):')
        for filename in sorted(overlaps.unrefreshed):
            msg.Error('\t{0} : in patch "{1}"', filename, overlaps.unrefreshed[filename])
    if not is_ok:
        return msg.Error('Aborting')
    _db_ok, results = patch_db.apply_patch()
    highest_ecode = 0
    for filename in results:
        print filename
        result = results[filename]
        print result
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

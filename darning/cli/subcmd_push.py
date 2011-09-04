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

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'push',
    description=_('Apply the next patch in the series.'),
    epilog=_('''If any of the nominated files have uncommitted changes from
    the point of view of the SCM controlling the sources or unrefreshed changes
    in an applied patch below the top path the push will be aborted unless
    either the force or the absorb option is specified.'''),
)

GROUP = PARSER.add_mutually_exclusive_group()

cli_args.add_force_option(GROUP, helptext=_('force the operation and leave uncommitted/unrefreshed changes to the pushed patch\'s files out of the pushed patch.'))

cli_args.add_absorb_option(GROUP, helptext=_('absorb/incorporate uncommitted/unrefreshed changes to the pushed patch\'s files into the pushed patch.'))

def run_push(args):
    '''Execute the "push" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    return patch_db.do_apply_next_patch(absorb=args.opt_absorb, force=args.opt_force)

PARSER.set_defaults(run_cmd=run_push)

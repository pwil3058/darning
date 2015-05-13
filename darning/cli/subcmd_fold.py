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

'''Fold the nominated patch into the current top patch.'''

from .. import patch_db

from . import cli_args
from . import db_utils
from . import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'fold',
    description=_('fold nominated patch into the top patch.'),
    epilog=_('''If any overlapped files have uncommitted changes from
    the point of view of the SCM controlling the sources or unrefreshed changes
    in an applied patch below the top patch the fold will be aborted unless
    either the force or the absorb option is specified.'''),
)

GROUP = PARSER.add_mutually_exclusive_group()

cli_args.add_force_option(GROUP, helptext=_('force the operation and discard uncommitted/unrefreshed changes in overlapped files in the top patch.'))

cli_args.add_absorb_option(GROUP, helptext=_('absorb/incorporate uncommitted/unrefreshed changes in overlapped files in the top patch.'))

PARSER.add_argument(
    'patchname',
    metavar=_('patchname'),
    help=_('the name of the patch to be folded.'),
)

def run_fold(args):
    '''Execute the "fold" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    db_utils.set_report_context(verbose=True)
    return patch_db.do_fold_named_patch(args.patchname, absorb=args.opt_absorb, force=args.opt_force)

PARSER.set_defaults(run_cmd=run_fold)

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
    'add',
    description='Add nominated file(s) to the top (or nominated) patch.',
)

cli_args.add_patch_option(PARSER, helptext='the name of the patch to add the file(s) to.')

cli_args.add_files_argument(PARSER, helptext='the file(s) to be added.')

def run_add(args):
    '''Execute the "add" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if not args.opt_patch:
        args.opt_patch = patch_db.get_top_patch_name()
        if not args.opt_patch:
            return msg.Error('No patches applied')
    elif not patch_db.patch_is_in_series(args.opt_patch):
        return msg.Error('patch "{0}" is unknown', args.opt_patch)
    is_ok = True
    db_utils.prepend_subdir(args.filenames)
    overlaps = patch_db.get_filelist_overlap_data(args.filenames, args.opt_patch)
    if len(overlaps.uncommitted) > 0:
        is_ok = False
        msg.Error('The following (overlapped) files have uncommitted SCM changes:')
        for filename in sorted(overlaps.uncommitted):
            msg.Error('\t{0}', db_utils.rel_subdir(filename))
    if len(overlaps.unrefreshed) > 0:
        is_ok = False
        msg.Error('The following (overlapped) files have unrefreshed changes (in an applied patch):')
        for filename in sorted(overlaps.unrefreshed):
            msg.Error('\t{0} : in patch "{1}"', db_utils.rel_subdir(filename), db_utils.rel_subdir(overlaps.unrefreshed[filename]))
    if not is_ok:
        return msg.Error('Aborting')
    already_in_patch = set(patch_db.get_filenames_in_patch(args.opt_patch, args.filenames))
    for filename in args.filenames:
        if filename not in already_in_patch:
            patch_db.add_file_to_patch(args.opt_patch, filename)
            already_in_patch.add(filename)
            msg.Info('file "{0}" added to patch "{1}".', db_utils.rel_subdir(filename), args.opt_patch)
        else:
            msg.Warn('file "{0}" already in patch "{1}". Ignored.', db_utils.rel_subdir(filename), args.opt_patch)
    return msg.OK

PARSER.set_defaults(run_cmd=run_add)

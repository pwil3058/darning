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

'''Unapply the current top patch.'''

from darning import patch_db
from darning.cli import cli_args
from darning.cli import db_utils
from darning.cli import msg

PARSER = cli_args.SUB_CMD_PARSER.add_parser(
    'add',
    description=_('Add nominated file(s) to the top (or nominated) patch.'),
)

cli_args.add_patch_option(PARSER, helptext=_('the name of the patch to add the file(s) to.'))

cli_args.add_force_option(PARSER, helptext=_('incorporate uncommitted/unrefreshed changes to named files into the top (or nominated) patch.'))

cli_args.add_files_argument(PARSER, helptext=_('the file(s) to be added.'))

def run_add(args):
    '''Execute the "add" sub command using the supplied args'''
    db_utils.open_db(modifiable=True)
    if not args.opt_patch:
        args.opt_patch = patch_db.get_top_patch_name()
        if not args.opt_patch:
            return msg.Error(_('No patches applied'))
    elif not patch_db.patch_is_in_series(args.opt_patch):
        return msg.Error(_('patch "{0}" is unknown'), args.opt_patch)
    is_ok = True
    if args.opt_force:
        ol_report = msg.Info
    else:
        ol_report = msg.Error
    db_utils.prepend_subdir(args.filepaths)
    overlaps = patch_db.get_filelist_overlap_data(args.filepaths, args.opt_patch)
    if len(overlaps.uncommitted) > 0:
        is_ok = False
        ol_report(_('The following (overlapped) files have uncommitted SCM changes:'))
        for filepath in sorted(overlaps.uncommitted):
            ol_report('\t{0}', db_utils.rel_subdir(filepath))
    if len(overlaps.unrefreshed) > 0:
        is_ok = False
        ol_report(_('The following (overlapped) files have unrefreshed changes (in an applied patch):'))
        for filepath in sorted(overlaps.unrefreshed):
            ol_report(_('\t{0} : in patch "{1}"'), db_utils.rel_subdir(filepath), db_utils.rel_subdir(overlaps.unrefreshed[filepath]))
    if not is_ok:
        if args.opt_force:
            msg.Info(_('Uncommited/unrefreshed changes incorporated into patch "{0}".'), args.opt_patch)
        else:
            return msg.Error(_('Aborting'))
    already_in_patch = set(patch_db.get_filepaths_in_patch(args.opt_patch, args.filepaths))
    for filepath in args.filepaths:
        if filepath not in already_in_patch:
            patch_db.add_file_to_patch(args.opt_patch, filepath, force=args.opt_force)
            already_in_patch.add(filepath)
            msg.Info(_('file "{0}" added to patch "{1}".'), db_utils.rel_subdir(filepath), args.opt_patch)
        else:
            msg.Warn(_('file "{0}" already in patch "{1}". Ignored.'), db_utils.rel_subdir(filepath), args.opt_patch)
    return msg.OK

PARSER.set_defaults(run_cmd=run_add)

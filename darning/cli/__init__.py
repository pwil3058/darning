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

'''
Library functions that are ony of interest CLI programs
'''

# This should be the only place that subcmd_* modules should be imported
# as this is sufficient to activate them.
import darning.cli.subcmd_init
import darning.cli.subcmd_new
import darning.cli.subcmd_push
import darning.cli.subcmd_pop
import darning.cli.subcmd_add
import darning.cli.subcmd_refresh
import darning.cli.subcmd_import
import darning.cli.subcmd_drop
import darning.cli.subcmd_remove
import darning.cli.subcmd_files
import darning.cli.subcmd_series
import darning.cli.subcmd_export
import darning.cli.subcmd_diff
import darning.cli.subcmd_copy
import darning.cli.subcmd_move

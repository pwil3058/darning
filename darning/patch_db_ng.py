### -*- coding: utf-8 -*-
###
###  Copyright (C) 2016 Peter Williams <pwil3058@gmail.com>
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

# NB: this module's purpose is to allow existing next generation patch data bases to be read
# NB: this module should NOT be imported directly by code (only pickle is allowed to import it)
from .patch_db import *
from .patch_db import _DataBaseData
from .patch_db import _PatchData
from .patch_db import _FileData
from .patch_db import _EssentialFileData
from .patch_db import _CombinedFileData
from .patch_db import _CombinedPatchData

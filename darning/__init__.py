#  Copyright 2010-2016 Peter Williams <pwil3058@gmail.com>
#
# This software is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License only.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software; if not, write to:
#  The Free Software Foundation, Inc., 51 Franklin Street,
#  Fifth Floor, Boston, MA 02110-1301 USA

"""Python package providing support for darn and gdarn programs"""

__all__ = []
__author__ = "Peter Williams <pwil3058@gmail.com>"
__version__ = "0.0"

import os
import gettext

HOME = os.path.expanduser("~")
APP_NAME = "darning"
CONFIG_DIR_PATH = os.path.join(HOME, ".config", APP_NAME + os.extsep + "d")
PGND_CONFIG_DIR_PATH = os.path.join(os.curdir, "." + APP_NAME + os.extsep + "d")

if not os.path.exists(CONFIG_DIR_PATH):
    os.makedirs(CONFIG_DIR_PATH, 0o775)

ISSUES_URL = "<https://github.com/pwil3058/darning/issues>"
ISSUES_EMAIL = __author__
ISSUES_VERSION = __version__

from . import option_defs

# import SCM CLI level backend interfaces here
from .wsm.git import git_ifce
from .wsm.hg import hg_ifce

# import PM backend interfaces here
from . import pm_ifce_darning

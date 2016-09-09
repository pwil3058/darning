### Copyright (C) 2010-2015 Peter Williams <pwil3058@gmail.com>
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

import os
import gettext


HOME = os.path.expanduser("~")
APP_NAME = "darning"
CONFIG_DIR_PATH = os.sep.join([HOME, "." + APP_NAME + ".d"])
PGND_CONFIG_DIR_PATH = os.sep.join([os.curdir, "." + APP_NAME + ".d"])

if not os.path.exists(CONFIG_DIR_PATH):
    os.mkdir(CONFIG_DIR_PATH, 0o775)

ISSUES_URL = "<https://github.com/pwil3058/darning/issues>"

import aipoed

# Lets tell those details to gettext
gettext.install(APP_NAME, localedir=aipoed.i18n.find_locale_dir())

aipoed.options.initialize(CONFIG_DIR_PATH, PGND_CONFIG_DIR_PATH)
from . import option_defs

# import SCM backend interfaces here
from . import scm_ifce_git
from . import scm_ifce_hg

# import PM backend interfaces here
from . import pm_ifce_darning

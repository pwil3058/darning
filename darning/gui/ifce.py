### Copyright (C) 2007-2015 Peter Williams <pwil3058@gmail.com>

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
import email.utils

from ..cmd_result import CmdResult
from ..config_data import APP_NAME

from .. import scm_ifce
from .. import utils
from .. import options

from . import pdb_ifce as PM
from . import ws_event
from .console import LOG

E_NEW_SCM, E_NEW_PM, E_NEW_SCM_OR_PM = ws_event.new_event_flags_and_mask(2)

E_CHANGE_WD = ws_event.new_event_flag()

SCM = scm_ifce.get_ifce()
_cached_pm_in_valid_pgnd = PM.in_valid_pgnd

CURDIR = os.getcwd()

def init(log=False):
    global SCM
    global CURDIR
    global _cached_pm_in_valid_pgnd
    options.load_global_options()
    result = PM.init()
    _cached_pm_in_valid_pgnd = PM.in_valid_pgnd
    SCM = scm_ifce.get_ifce()
    curdir = os.getcwd()
    options.load_pgnd_options()
    if log or PM.in_valid_pgnd:
        LOG.start_cmd(APP_NAME + " {0}\n".format(os.getcwd()))
        LOG.end_cmd(result)
    # NB: need to send either E_CHANGE_WD or E_NEW_SCM_OR_PM to ensure action sates get set
    if not utils.samefile(CURDIR, curdir):
        CURDIR = curdir
        ws_event.notify_events(E_CHANGE_WD, new_wd=curdir)
    else:
        ws_event.notify_events(E_NEW_SCM_OR_PM)
    return result

def close():
    PM.close_db()

def chdir(new_dir=None):
    global SCM
    global CURDIR
    global _cached_pm_in_valid_pgnd
    result = PM.do_chdir(new_dir)
    _cached_pm_in_valid_pgnd = PM.in_valid_pgnd
    options.reload_pgnd_options()
    SCM  = scm_ifce.get_ifce()
    CURDIR = os.getcwd()
    LOG.start_cmd(_('New Playground: {0}\n').format(CURDIR))
    LOG.end_cmd(result)
    ws_event.notify_events(E_CHANGE_WD, new_wd=CURDIR)
    return result

def check_interfaces(args):
    global SCM
    global CURDIR
    global _cached_pm_in_valid_pgnd
    events = 0
    if _cached_pm_in_valid_pgnd != PM.in_valid_pgnd:
        _cached_pm_in_valid_pgnd = PM.in_valid_pgnd
        events |= E_NEW_PM
        options.load_pgnd_options()
    scm = scm_ifce.get_ifce()
    if scm != SCM:
        SCM = scm
        events |= E_NEW_SCM
    curdir = os.getcwd()
    if not utils.samefile(CURDIR, curdir):
        args["new_wd"] = curdir
        CURDIR = curdir
        return E_CHANGE_WD # don't send ifce changes and wd change at the same time
    return events

DEFAULT_NAME_EVARS = ["GIT_AUTHOR_NAME", "GECOS"]
DEFAULT_EMAIL_VARS = ["GIT_AUTHOR_EMAIL", "EMAIL_ADDRESS"]

def get_author_name_and_email():
    # Do some 'configuration' stuff here
    # TODO: major overhaul of get_author_name_and_email()
    name = options.get('user', 'name')
    if not name:
        name = utils.get_first_in_envar(DEFAULT_NAME_EVARS)
    email_addr = options.get('user', 'email')
    if not email_addr:
        email_addr = utils.get_first_in_envar(DEFAULT_EMAIL_VARS)
    if not email_addr:
        user = os.environ.get('LOGNAME', None)
        host = os.environ.get('HOSTNAME', None)
        email_addr = '@'.join([user, host]) if user and host else None
    if email_addr:
        return email.utils.formataddr((name, email_addr,))
    else:
        return None

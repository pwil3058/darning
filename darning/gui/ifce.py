### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>
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
import email.utils

from ..cmd_result import CmdResult

from .. import scm_ifce as SCM
from .. import utils
from .. import options

from . import pdb_ifce as PM
from . import ws_event
from . import terminal
from .console import LOG

TERM = None

def init(log=False):
    global TERM
    if terminal.AVAILABLE:
        TERM = terminal.Terminal()
    options.load_global_options()
    result = PM.init()
    options.load_pgnd_options()
    SCM.reset_back_end()
    if log or PM.in_valid_pgnd:
        LOG.start_cmd('gdarn {0}\n'.format(os.getcwd()))
        LOG.end_cmd(result)
    ws_event.notify_events(ws_event.CHANGE_WD)
    return result

def close():
    PM.close_db()

def chdir(new_dir=None):
    old_wd = os.getcwd()
    result = PM.do_chdir(new_dir)
    options.reload_pgnd_options()
    SCM.reset_back_end()
    ws_event.notify_events(ws_event.CHANGE_WD)
    new_wd = os.getcwd()
    if not utils.samefile(new_wd, old_wd):
        if TERM:
            TERM.set_cwd(new_wd)
    LOG.start_cmd(_('New Playground: {0}\n').format(new_wd))
    LOG.end_cmd(result)
    return result

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

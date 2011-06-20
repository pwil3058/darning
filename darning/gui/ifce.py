### Copyright (C) 2011 Peter Williams <peter@users.sourceforge.net>
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

in_valid_repo = False
in_valid_pgnd = False

import os

from darning import scm_ifce as SCM
from darning import cmd_result
from darning import utils

from darning.gui import pdb_ifce as PM
from darning.gui import ws_event
from darning.gui import terminal
from darning.gui.console import LOG

TERM = terminal.Terminal() if terminal.AVAILABLE else None

def init():
    global in_valid_repo, in_valid_pgnd
    root, _ = PM.find_base_dir()
    result = cmd_result.Result(cmd_result.OK, "", "")
    if root:
        os.chdir(root)
        result = PM.open_db()
        in_valid_pgnd = result.eflags == cmd_result.OK
    else:
        in_valid_pgnd = False
    SCM.reset_back_end()
    in_valid_repo = SCM.is_valid_repo()
    return result

def close():
    PM.close_db()

def chdir(newdir=None):
    global in_valid_repo, in_valid_pgnd
    old_wd = os.getcwd()
    retval = cmd_result.Result(cmd_result.OK, "", "")
    PM.close_db()
    if newdir:
        try:
            os.chdir(newdir)
        except OSError as err:
            import errno
            ecode = errno.errorcode[err.errno]
            emsg = err.strerror
            retval = cmd_result.Result(cmd_result.ERROR, '', '%s: "%s" :%s' % (ecode, newdir, emsg))
    root, _ = PM.find_base_dir()
    if root:
        os.chdir(root)
        retval = PM.open_db()
        in_valid_pgnd = retval.eflags == cmd_result.OK
        if in_valid_pgnd:
            from darning.gui import config
            config.PgndPathTable.append_saved_pgnd(root)
    else:
        in_valid_pgnd = False
    SCM.reset_back_end()
    in_valid_repo = SCM.is_valid_repo()
    ws_event.notify_events(ws_event.CHANGE_WD)
    new_wd = os.getcwd()
    if not utils.samefile(new_wd, old_wd):
        if TERM:
            TERM.set_cwd(new_wd)
        if LOG:
            LOG.append_entry("New Playground: %s" % new_wd)
    return retval

def new_playground(description, pgdir=None):
    global in_valid_pgnd
    if pgdir is not None:
        result = chdir(pgdir)
        if result.eflags != cmd_result.OK:
            return result
    if in_valid_pgnd:
        return cmd_result.Result(cmd_result.WARNING, '', 'Already initialized')
    result = PM.do_initialization(description)
    if result is not True:
        return cmd_result.Result(cmd_result.ERROR, '', str(result))
    retval = PM.open_db()
    in_valid_pgnd = retval.eflags == cmd_result.OK
    if in_valid_pgnd:
        from darning.gui import config
        config.PgndPathTable.append_saved_pgnd(os.getcwd())
        ws_event.notify_events(ws_event.PGND_MOD)
    return retval

DEFAULT_NAME_EVARS = ["GIT_AUTHOR_NAME", "GECOS"]
DEFAULT_EMAIL_VARS = ["GIT_AUTHOR_EMAIL", "EMAIL_ADDRESS"]

def get_author_name_and_email():
    # Do some 'configuration' stuff here
    name = utils.get_first_in_envar(DEFAULT_NAME_EVARS)
    if not name:
        name = "UNKNOWN"
    email = utils.get_first_in_envar(DEFAULT_EMAIL_VARS)
    if not email:
        email = "UNKNOWN"
    return "%s <%s>" % (name, email)

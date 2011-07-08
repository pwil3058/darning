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
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

in_valid_repo = False
in_valid_pgnd = False
pgnd_is_mutable = False

import os

from darning import scm_ifce as SCM
from darning import cmd_result
from darning import utils
from darning import options

from darning.gui import pdb_ifce as PM
from darning.gui import ws_event
from darning.gui import terminal
from darning.gui.console import LOG

TERM = terminal.Terminal() if terminal.AVAILABLE else None

def init(log=False):
    global in_valid_repo, in_valid_pgnd, pgnd_is_mutable
    options.load_global_options()
    root, _ = PM.find_base_dir()
    result = cmd_result.Result(cmd_result.OK, "", "")
    if root:
        os.chdir(root)
        result = PM.open_db()
        in_valid_pgnd = PM.is_readable()
        pgnd_is_mutable = PM.is_writable()
    else:
        in_valid_pgnd = False
        pgnd_is_mutable = False
    options.load_pgnd_options()
    SCM.reset_back_end()
    in_valid_repo = SCM.is_valid_repo()
    if log or root:
        LOG.start_cmd('gdarn {0}'.format(os.getcwd()))
        LOG.append_stdout(result.stdout)
        LOG.append_stderr(result.stderr)
        LOG.end_cmd()
    return result

def close():
    PM.close_db()

def chdir(newdir=None):
    global in_valid_repo, in_valid_pgnd, pgnd_is_mutable
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
        in_valid_pgnd = PM.is_readable()
        pgnd_is_mutable = PM.is_writable()
        if in_valid_pgnd:
            from darning.gui import config
            config.PgndPathTable.append_saved_pgnd(root)
    else:
        in_valid_pgnd = False
        pgnd_is_mutable = False
    options.reload_pgnd_options()
    SCM.reset_back_end()
    in_valid_repo = SCM.is_valid_repo()
    ws_event.notify_events(ws_event.CHANGE_WD)
    new_wd = os.getcwd()
    if not utils.samefile(new_wd, old_wd):
        if TERM:
            TERM.set_cwd(new_wd)
    LOG.start_cmd("New Playground: %s" % new_wd)
    LOG.append_stdout(retval.stdout)
    LOG.append_stderr(retval.stderr)
    LOG.end_cmd()
    return retval

def new_playground(description, pgdir=None):
    global in_valid_pgnd, pgnd_is_mutable
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
    in_valid_pgnd = PM.is_readable()
    pgnd_is_mutable = PM.is_writable()
    if in_valid_pgnd:
        from darning.gui import config
        config.PgndPathTable.append_saved_pgnd(os.getcwd())
        ws_event.notify_events(ws_event.PGND_MOD)
    return retval

DEFAULT_NAME_EVARS = ["GIT_AUTHOR_NAME", "GECOS"]
DEFAULT_EMAIL_VARS = ["GIT_AUTHOR_EMAIL", "EMAIL_ADDRESS"]

def get_author_name_and_email():
    # Do some 'configuration' stuff here
    name = options.get('user', 'name')
    if not name:
        name = utils.get_first_in_envar(DEFAULT_NAME_EVARS)
    email = options.get('user', 'email')
    if not email:
        email = utils.get_first_in_envar(DEFAULT_EMAIL_VARS)
    if not email:
        user = os.environ.get('LOGNAME', None)
        host = os.environ.get('HOSTNAME', None)
        email = '@'.join([user, host]) if user and host else None
    if name and email:
        return '{0} <{1}>'.format(name, email)
    elif email:
        return email
    else:
        return None

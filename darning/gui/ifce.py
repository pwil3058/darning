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

from darning.gui import pdb_ifce as PM
from darning.gui import ws_event

TERM = None
LOG = None

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
        from darning.gui import config
        config.append_saved_pgnd(root)
    else:
        in_valid_pgnd = False
    SCM.reset_back_end()
    in_valid_repo = SCM.is_valid_repo()
    ws_event.notify_events(ws_event.CHANGE_WD)
    new_wd = os.getcwd()
    if not os.path.samefile(new_wd, old_wd):
        if TERM:
            TERM.set_cwd(new_wd)
        if LOG:
            LOG.append_entry("New Playground: %s" % new_wd)
    return retval
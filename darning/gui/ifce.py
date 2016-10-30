### Copyright (C) 2007-2015 Peter Williams <pwil3058@gmail.com>
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

from ..wsm.bab import CmdResult
from ..wsm.bab import enotify
from ..wsm.bab import options

from ..wsm.gtx import dialogue

from .. import APP_NAME

from ..wsm.scm_gui import ifce as scm_ifce
from ..wsm.pm_gui import ifce as pm_ifce
from .. import utils
from .. import rctx

from . import recollect
from ..wsm.gtx.console import LOG, RCTX

from ..wsm.pm import E_NEW_PM
from ..wsm.scm import E_NEW_SCM

E_NEW_SCM_OR_PM = E_NEW_SCM | E_NEW_PM

def report_backend_requirements():
    dialogue.main_window.inform_user(pm_ifce.backend_requirements())

SCM = scm_ifce.get_ifce()
PM = pm_ifce.get_ifce()

CURDIR = os.getcwd()

def init(log=False):
    global SCM
    global PM
    global CURDIR
    rctx.reset(RCTX.stdout, RCTX.stderr)
    options.load_global_options()
    PM = pm_ifce.get_ifce()
    if PM.in_valid_pgnd:
        root = PM.get_playground_root()
        os.chdir(root)
        from . import config
        config.PgndPathView.append_saved_path(root)
        recollect.set(APP_NAME, "last_pgnd", root)
    SCM = scm_ifce.get_ifce()
    curdir = os.getcwd()
    options.load_pgnd_options()
    if log or PM.in_valid_pgnd:
        LOG.start_cmd(APP_NAME + " {0}\n".format(curdir))
        LOG.end_cmd()
    # NB: need to send either enotify.E_CHANGE_WD or E_NEW_SCM_OR_PM to ensure action sates get set
    if not utils.samefile(CURDIR, curdir):
        CURDIR = curdir
        enotify.notify_events(enotify.E_CHANGE_WD, new_wd=curdir)
    else:
        enotify.notify_events(E_NEW_SCM_OR_PM)
    from ..wsm.gtx import auto_update
    auto_update.set_initialize_event_flags(check_interfaces)
    return CmdResult.ok()

def choose_backend():
    bel = pm_ifce.avail_backends()
    if len(bel) == 0:
        report_backend_requirements()
        return None
    elif len(bel) == 1:
        return bel[0]
    return dialogue.SelectFromListDialog(olist=bel, prompt=_('Choose back end:')).make_selection()

def init_current_dir(backend):
    global SCM
    global PM
    result = pm_ifce.create_new_playground(os.getcwd(), backend)
    events = 0
    pm = pm_ifce.get_ifce()
    if pm != PM:
        PM = pm
        events |= E_NEW_PM
    scm = scm_ifce.get_ifce()
    if scm != SCM:
        SCM = scm
        events |= E_NEW_SCM
    if PM.in_valid_pgnd:
        from . import config
        config.PgndPathView.append_saved_path(CURDIR)
        recollect.set(APP_NAME, "last_pgnd", CURDIR)
    if events:
        enotify.notify_events(events)
    return result

def create_new_playground(new_pgnd_path, backend=None):
    if backend is None:
        result = PM.create_new_playground(new_pgnd_path)
    else:
        result = pm_ifce.create_new_playground(new_pgnd_path, backend)
    return result

def chdir(newdir):
    global SCM
    global PM
    global CURDIR
    retval = CmdResult.ok()
    events = 0
    if newdir:
        try:
            os.chdir(newdir)
        except OSError as err:
            import errno
            ecode = errno.errorcode[err.errno]
            emsg = err.strerror
            retval = CmdResult.error(stderr="{0}: \"{1}\" : {2}".format(ecode, newdir, emsg))
            newdir = os.getcwd()
    PM = pm_ifce.get_ifce()
    if PM.in_valid_pgnd:
        newdir = PM.get_playground_root()
        os.chdir(newdir)
        from . import config
        config.PgndPathView.append_saved_path(newdir)
        recollect.set(APP_NAME, "last_pgnd", newdir)
    SCM = scm_ifce.get_ifce()
    options.reload_pgnd_options()
    CURDIR = os.getcwd()
    LOG.start_cmd(_('New Playground: {0}\n').format(CURDIR))
    LOG.end_cmd(retval)
    enotify.notify_events(enotify.E_CHANGE_WD, new_wd=CURDIR)
    return retval

def check_interfaces(args):
    global SCM
    global PM
    global CURDIR
    events = 0
    pm = pm_ifce.get_ifce()
    if pm != PM:
        events |= E_NEW_PM
        PM = pm
    if PM.in_valid_pgnd:
        newdir = PM.get_playground_root()
        os.chdir(newdir)
        from . import config
        options.load_pgnd_options()
    scm = scm_ifce.get_ifce()
    if scm != SCM:
        SCM = scm
        events |= E_NEW_SCM
    curdir = os.getcwd()
    if not utils.samefile(CURDIR, curdir):
        if PM.in_valid_pgnd:
            config.PgndPathView.append_saved_path(newdir)
            recollect.set(APP_NAME, "last_pgnd", newdir)
        args["new_wd"] = curdir
        CURDIR = curdir
        return enotify.E_CHANGE_WD # don't send ifce changes and wd change at the same time
    return events

def get_author_name_and_email():
    import email.utils
    from .. import utils
    DEFAULT_NAME_EVARS = ["GECOS", "GIT_AUTHOR_NAME", "LOGNAME"]
    DEFAULT_EMAIL_EVARS = ["EMAIL_ADDRESS", "GIT_AUTHOR_EMAIL"]
    # first check for OUR definitions in the current pgnd
    email_addr = options.get('user', 'email', pgnd_only=True)
    if email_addr:
        name = options.get('user', 'name')
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    # then ask the managers in order of relevance
    for mgr in [PM, SCM]:
        anae = mgr.get_author_name_and_email()
        if anae:
            return anae
    # then check for OUR global definitions
    email_addr = options.get('user', 'email')
    if email_addr:
        name = options.get('user', 'name')
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    email_addr = utils.get_first_in_envar(DEFAULT_EMAIL_EVARS, default=None)
    if email_addr:
        name = options.get('user', 'name')
        return email.utils.formataddr((name if name else utils.get_first_in_envar(DEFAULT_NAME_EVARS, default="unknown"), email_addr,))
    user = os.environ.get('LOGNAME', None)
    host = os.environ.get('HOSTNAME', None)
    if user and host:
        return email.utils.formataddr((user, "@".join([user, host]),))
    else:
        return _("Who knows? :-)")

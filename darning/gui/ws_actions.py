### Copyright (C) 2011 Peter Williams <peter_ono@users.sourceforge.net>

### This program is free software; you can redistribute it and/or modify
### it under the terms of the GNU General Public License as published by
### the Free Software Foundation; version 2 of the License only.

### This program is distributed in the hope that it will be useful,
### but WITHOUT ANY WARRANTY; without even the implied warranty of
### MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
### GNU General Public License for more details.

### You should have received a copy of the GNU General Public License
### along with this program; if not, write to the Free Software
### Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

'''
Workspace status action groups
'''

import collections

import gtk

from darning.gui import actions
from darning.gui import ws_event
from darning.gui import gutils
from darning.gui import ifce

AC_NOT_IN_PGND, AC_IN_PGND, AC_IN_PGND_MUTABLE, AC_IN_PGND_MASK = actions.ActionCondns.new_flags_and_mask(3)
AC_NOT_IN_REPO, AC_IN_REPO, AC_IN_REPO_MASK = actions.ActionCondns.new_flags_and_mask(2)
AC_NOT_PMIC, AC_PMIC, AC_PMIC_MASK = actions.ActionCondns.new_flags_and_mask(2)

def get_in_pgnd_condns():
    if ifce.PM.in_valid_pgnd:
        if ifce.PM.pgnd_is_mutable:
            conds = AC_IN_PGND | AC_IN_PGND_MUTABLE
        else:
            conds = AC_IN_PGND
    else:
        conds = AC_NOT_IN_PGND
    return actions.MaskedCondns(conds, AC_IN_PGND_MASK)

def get_in_repo_condns():
    return actions.MaskedCondns(AC_IN_REPO if ifce.SCM.in_valid_pgnd else AC_NOT_IN_REPO, AC_IN_REPO_MASK)

def get_pmic_condns():
    return actions.MaskedCondns(AC_PMIC if ifce.PM.get_in_progress() else AC_NOT_PMIC, AC_PMIC_MASK)

def _update_class_indep_cwd_cb(_arg=None):
    condns = get_in_pgnd_condns() | get_in_repo_condns()
    actions.CLASS_INDEP_AGS.update_condns(condns)

def _update_class_indep_pgnd_cb(_arg=None):
    actions.CLASS_INDEP_AGS.update_condns(get_in_pgnd_condns())

def _update_class_indep_pmic_cb(_arg=None):
    actions.CLASS_INDEP_AGS.update_condns(get_pmic_condns())

ws_event.add_notification_cb(ws_event.CHANGE_WD, _update_class_indep_cwd_cb)
ws_event.add_notification_cb(ws_event.PGND_MOD, _update_class_indep_pgnd_cb)
ws_event.add_notification_cb(ws_event.PATCH_PUSH|ws_event.PATCH_POP|ws_event.CHANGE_WD, _update_class_indep_pmic_cb)

class AGandUIManager(actions.CAGandUIManager, ws_event.Listener):
    def __init__(self, selection=None, popup=None):
        actions.CAGandUIManager.__init__(self, selection=selection, popup=popup)
        ws_event.Listener.__init__(self)
        self.add_notification_cb(ws_event.CHANGE_WD, self.cwd_condns_change_cb)
        self.add_notification_cb(ws_event.PGND_MOD, self.pgnd_condns_change_cb)
        self.add_notification_cb(ws_event.PATCH_PUSH|ws_event.PATCH_POP|ws_event.CHANGE_WD, self.pmic_condns_change_cb)
        self.init_action_states()
    def cwd_condns_change_cb(self, _arg=None):
        condns = get_in_pgnd_condns() | get_in_repo_condns()
        self.action_groups.update_condns(condns)
    def pgnd_condns_change_cb(self, _arg=None):
        self.action_groups.update_condns(get_in_pgnd_condns())
    def pmic_condns_change_cb(self, _arg=None):
        self.action_groups.update_condns(get_pmic_condns())
    def init_action_states(self):
        condn_set = get_in_pgnd_condns() | get_in_repo_condns() | get_pmic_condns()
        self.action_groups.update_condns(condn_set)

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("actions_playground_menu", None, _('_Playground')),
        ("actions_quit", gtk.STOCK_QUIT, _('_Quit'), "",
         _('Quit'), gtk.main_quit),
    ])

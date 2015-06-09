### Copyright (C) 2011-2015 Peter Williams <pwil3058@gmail.com>
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

'''
Workspace status action groups
'''

import collections

import gtk

from . import actions
from . import ws_event
from . import ifce
from .. import scm_ifce
from .. import pm_ifce

AC_NOT_IN_PM_PGND, AC_IN_PM_PGND, AC_IN_PM_PGND_MUTABLE, AC_IN_PM_PGND_MASK = actions.ActionCondns.new_flags_and_mask(3)
AC_NOT_IN_SCM_PGND, AC_IN_SCM_PGND, AC_IN_SCM_PGND_MASK = actions.ActionCondns.new_flags_and_mask(2)
AC_NOT_PMIC, AC_PMIC, AC_PMIC_MASK = actions.ActionCondns.new_flags_and_mask(2)

def get_in_pm_pgnd_condns():
    if ifce.PM.in_valid_pgnd:
        if ifce.PM.pgnd_is_mutable:
            conds = AC_IN_PM_PGND | AC_IN_PM_PGND_MUTABLE
        else:
            conds = AC_IN_PM_PGND
    else:
        conds = AC_NOT_IN_PM_PGND
    return actions.MaskedCondns(conds, AC_IN_PM_PGND_MASK)

def get_in_scm_pgnd_condns():
    return actions.MaskedCondns(AC_IN_SCM_PGND if ifce.SCM.in_valid_pgnd else AC_NOT_IN_SCM_PGND, AC_IN_SCM_PGND_MASK)

def get_pmic_condns():
    return actions.MaskedCondns(AC_PMIC if ifce.PM.get_in_progress() else AC_NOT_PMIC, AC_PMIC_MASK)

def _update_class_indep_pm_pgnd_cb(**kwargs):
    actions.CLASS_INDEP_AGS.update_condns(get_in_pm_pgnd_condns())

def _update_class_indep_scm_pgnd_cb(**kwargs):
    actions.CLASS_INDEP_AGS.update_condns(get_in_scm_pgnd_condns())

def _update_class_indep_pmic_cb(**kwargs):
    actions.CLASS_INDEP_AGS.update_condns(get_pmic_condns())

ws_event.add_notification_cb(ifce.E_CHANGE_WD|ifce.E_NEW_SCM, _update_class_indep_scm_pgnd_cb)
ws_event.add_notification_cb(ifce.E_CHANGE_WD|ifce.E_NEW_PM, _update_class_indep_pm_pgnd_cb)
ws_event.add_notification_cb(pm_ifce.E_PATCH_STACK_CHANGES|ifce.E_NEW_PM|ifce.E_CHANGE_WD, _update_class_indep_pmic_cb)

class AGandUIManager(actions.CAGandUIManager, ws_event.Listener):
    def __init__(self, selection=None, popup=None):
        actions.CAGandUIManager.__init__(self, selection=selection, popup=popup)
        ws_event.Listener.__init__(self)
        self.add_notification_cb(ifce.E_CHANGE_WD|ifce.E_NEW_SCM, self.scm_pgnd_conds_change_cb)
        self.add_notification_cb(ifce.E_CHANGE_WD|ifce.E_NEW_PM, self.pm_pgnd_condns_change_cb)
        self.add_notification_cb(pm_ifce.E_PATCH_STACK_CHANGES|ifce.E_NEW_PM|ifce.E_CHANGE_WD, self.pmic_condns_change_cb)
        self.init_action_states()
    def scm_pgnd_conds_change_cb(self, **kwargs):
        self.action_groups.update_condns(get_in_scm_pgnd_condns())
    def pm_pgnd_condns_change_cb(self, **kwargs):
        self.action_groups.update_condns(get_in_pm_pgnd_condns())
    def pmic_condns_change_cb(self, **kwargs):
        self.action_groups.update_condns(get_pmic_condns())
    def init_action_states(self):
        condn_set = get_in_pm_pgnd_condns() | get_in_scm_pgnd_condns() | get_pmic_condns()
        self.action_groups.update_condns(condn_set)

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("actions_wd_menu", None, _('_Working Directory')),
        ("actions_quit", gtk.STOCK_QUIT, _('_Quit'), "",
         _('Quit'), gtk.main_quit),
    ])

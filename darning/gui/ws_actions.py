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

from gi.repository import Gtk

from ..wsm.bab import enotify

from ..wsm.gtx import actions

from .. import scm_ifce
from .. import pm_ifce

from . import ifce

AC_NOT_IN_PM_PGND, AC_IN_PM_PGND, AC_IN_PM_PGND_MASK = actions.ActionCondns.new_flags_and_mask(2)
AC_NOT_IN_SCM_PGND, AC_IN_SCM_PGND, AC_IN_SCM_PGND_MASK = actions.ActionCondns.new_flags_and_mask(2)
AC_NOT_PMIC, AC_PMIC, AC_PMIC_MASK = actions.ActionCondns.new_flags_and_mask(2)

def get_in_pm_pgnd_condns():
    if ifce.PM.in_valid_pgnd:
        conds = AC_IN_PM_PGND
    else:
        conds = AC_NOT_IN_PM_PGND
    return actions.MaskedCondns(conds, AC_IN_PM_PGND_MASK)

def get_in_scm_pgnd_condns():
    return actions.MaskedCondns(AC_IN_SCM_PGND if ifce.SCM.in_valid_pgnd else AC_NOT_IN_SCM_PGND, AC_IN_SCM_PGND_MASK)

def get_pmic_condns():
    return actions.MaskedCondns(AC_PMIC if ifce.PM.is_poppable else AC_NOT_PMIC, AC_PMIC_MASK)

def _update_class_indep_pm_pgnd_cb(**kwargs):
    condns = get_in_pm_pgnd_condns()
    actions.CLASS_INDEP_AGS.update_condns(condns)
    actions.CLASS_INDEP_BGS.update_condns(condns)

def _update_class_indep_scm_pgnd_cb(**kwargs):
    condns = get_in_scm_pgnd_condns()
    actions.CLASS_INDEP_AGS.update_condns(condns)
    actions.CLASS_INDEP_BGS.update_condns(condns)

def _update_class_indep_pmic_cb(**kwargs):
    condns = get_pmic_condns()
    actions.CLASS_INDEP_AGS.update_condns(condns)
    actions.CLASS_INDEP_BGS.update_condns(condns)

enotify.add_notification_cb(enotify.E_CHANGE_WD|ifce.E_NEW_SCM, _update_class_indep_scm_pgnd_cb)
enotify.add_notification_cb(enotify.E_CHANGE_WD|ifce.E_NEW_PM, _update_class_indep_pm_pgnd_cb)
enotify.add_notification_cb(pm_ifce.E_PATCH_STACK_CHANGES|ifce.E_NEW_PM|enotify.E_CHANGE_WD, _update_class_indep_pmic_cb)

class WSListenerMixin:
    def __init__(self):
        self.add_notification_cb(enotify.E_CHANGE_WD|ifce.E_NEW_SCM, self.scm_pgnd_conds_change_cb)
        self.add_notification_cb(enotify.E_CHANGE_WD|ifce.E_NEW_PM, self.pm_pgnd_condns_change_cb)
        self.add_notification_cb(pm_ifce.E_PATCH_STACK_CHANGES|ifce.E_NEW_PM|enotify.E_CHANGE_WD, self.pmic_condns_change_cb)
        self.init_action_states()
    def scm_pgnd_conds_change_cb(self, **kwargs):
        condns = get_in_scm_pgnd_condns()
        self.action_groups.update_condns(condns)
        try:
            self.button_groups.update_condns(condns)
        except AttributeError:
            pass
    def pm_pgnd_condns_change_cb(self, **kwargs):
        condns = get_in_pm_pgnd_condns()
        self.action_groups.update_condns(condns)
        try:
            self.button_groups.update_condns(condns)
        except AttributeError:
            pass
    def pmic_condns_change_cb(self, **kwargs):
        condns = get_pmic_condns()
        self.action_groups.update_condns(condns)
        try:
            self.button_groups.update_condns(condns)
        except AttributeError:
            pass
    def init_action_states(self):
        condn_set = get_in_pm_pgnd_condns() | get_in_scm_pgnd_condns() | get_pmic_condns()
        self.action_groups.update_condns(condn_set)
        try:
            self.button_groups.update_condns(condn_set)
        except AttributeError:
            pass

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("actions_wd_menu", None, _('_Working Directory')),
        ("actions_quit", Gtk.STOCK_QUIT, _('_Quit'), "",
         _('Quit'), Gtk.main_quit),
    ])

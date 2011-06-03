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
### Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gtk

from darning.gui import ws_event, gutils
from darning.gui import ifce

class Condns(int):
    DONT_CARE = 0
    NCONDS = 9
    NOT_IN_PGND, IN_PGND, \
    NOT_IN_REPO, IN_REPO, \
    NO_SELN, SELN, UNIQUE_SELN, \
    NOT_PMIC, PMIC = [2 ** n for n in range(NCONDS)]
    IN_PGND_CONDS = NOT_IN_PGND | IN_PGND
    IN_REPO_CONDS = NOT_IN_REPO | IN_REPO
    SELN_CONDNS = NO_SELN | SELN | UNIQUE_SELN
    PMIC_CONDNS = NOT_PMIC | PMIC

class MaskedCondns(object):
    @staticmethod
    def get_in_pgnd_condns():
        return MaskedCondns(Condns.IN_PGND if ifce.in_valid_pgnd else Condns.NOT_IN_PGND, Condns.IN_PGND_CONDS)
    @staticmethod
    def get_in_repo_condns():
        return MaskedCondns(Condns.IN_REPO if ifce.in_valid_repo else Condns.NOT_IN_REPO, Condns.IN_REPO_CONDS)
    @staticmethod
    def get_pmic_condns():
        return MaskedCondns(Condns.PMIC if ifce.PM.get_in_progress() else Condns.NOT_PMIC, Condns.PMIC_CONDNS)
    @staticmethod
    def get_seln_condns(seln):
        if seln is None:
            return MaskedCondns(Condns.DONT_CARE, Condns.SELN_CONDNS)
        selsz = seln.count_selected_rows()
        if selsz == 0:
            return MaskedCondns(Condns.NO_SELN, Condns.SELN_CONDNS)
        elif selsz == 1:
            return MaskedCondns(Condns.SELN + Condns.UNIQUE_SELN, Condns.SELN_CONDNS)
        else:
            return MaskedCondns(Condns.SELN, Condns.SELN_CONDNS)
    def __init__(self, condns, mask):
        self.condns = condns
        self.mask = mask
    def __or__(self, other):
        return MaskedCondns(self.condns | other.condns, self.mask | other.mask)
    def __ior__(self, other):
        self.condns |= other.condns
        self.mask |= other.mask
        return self

class ConditionalActions:
    def __init__(self, name, ui_mgrs=None, condns=0):
        self.groups = dict()
        self.current_condns = condns
        self.ui_mgrs = [] if ui_mgrs is None else ui_mgrs[:]
        self.name = name
    def _group_name(self, condns):
        return '{0}:{1:x}'.format(self.name, condns)
    def _new_group(self, condns):
        assert condns not in self.groups
        self.groups[condns] = gtk.ActionGroup(self._group_name(condns))
        self.groups[condns].set_sensitive((condns & self.current_condns) == condns)
        for ui_mgr in self.ui_mgrs:
            ui_mgr.insert_action_group(self.groups[condns], -1)
    def add_action(self, condns, action):
        if condns not in self.groups:
            self._new_group(condns)
        self.groups[condns].add_action(action)
    def add_actions(self, condns, actions):
        if condns not in self.groups:
            self._new_group(condns)
        self.groups[condns].add_actions(actions)
    def copy_action(self, new_condns, action_name):
        action = self.get_action_by_name(action_name)
        if action:
            self.add_action(new_condns, action)
            return True
        return False
    def move_action(self, new_condns, action_name):
        for agrp in self.groups.values():
            action = agrp.get_action(action_name)
            if action:
                agrp.remove_action(action)
                self.add_action(new_condns, action)
                return True
        return False
    def set_sensitivity_for_condns(self, condns_set):
        condns = condns_set.condns | (self.current_condns & ~condns_set.mask)
        for key_condns, group in self.groups.items():
            if condns_set.mask & key_condns:
                group.set_sensitive((key_condns & condns) == key_condns)
        self.current_condns = condns
    def set_visibility_for_condns(self, condns, visible):
        self.groups[condns].set_visible(visible)
    def add_ui_mgr(self, ui_mgr):
        self.ui_mgrs.append(ui_mgr)
        for agrp in self.groups.values():
            ui_mgr.insert_action_group(agrp, -1)
    def get_action_by_name(self, action_name):
        for agrp in self.groups.values():
            action = agrp.get_action(action_name)
            if action:
                return action
        return None
    def __str__(self):
        string = 'ConditionalActions({0})\n'.format(self.name)
        for condns, group in self.groups.items():
            name = group.get_name()
            member_names = '['
            for member_name in [action.get_name() for action in group.list_actions()]:
                member_names += '{0}, '.format(member_name)
            member_names += ']'
            string += '\tGroup({0:x},{1}): {2}\n'.format(condns, name, member_names)
        return string

_CLASS_INDEP_AGS = ConditionalActions('class_indep')

def _update_class_indep_cwd_cb(_arg=None):
    condns = MaskedCondns.get_in_pgnd_condns() | MaskedCondns.get_in_repo_condns()
    _CLASS_INDEP_AGS.set_sensitivity_for_condns(condns)

def _update_class_indep_pmic_cb(_arg=None):
    _CLASS_INDEP_AGS.set_sensitivity_for_condns(MaskedCondns.get_pmic_condns())

def add_class_indep_action(condns, action):
    assert (condns & Condns.SELN_CONDNS) == 0
    _CLASS_INDEP_AGS.add_action(condns, action)

def add_class_indep_actions(condns, actions):
    assert (condns & Condns.SELN_CONDNS) == 0
    _CLASS_INDEP_AGS.add_actions(condns, actions)

def get_class_indep_action(action_name):
    return _CLASS_INDEP_AGS.get_action_by_name(action_name)

def set_class_indep_sensitivity_for_condns(condns):
    _CLASS_INDEP_AGS.set_sensitivity_for_condns(condns)

ws_event.add_notification_cb(ws_event.CHANGE_WD, _update_class_indep_cwd_cb)
ws_event.add_notification_cb(ws_event.PMIC_CHANGE|ws_event.CHANGE_WD, _update_class_indep_pmic_cb)

class AGandUIManager(ws_event.Listener):
    def __init__(self, selection=None):
        ws_event.Listener.__init__(self)
        self.ui_manager = gutils.UIManager()
        _CLASS_INDEP_AGS.add_ui_mgr(self.ui_manager)
        self.seln = selection
        name = '{0}:{1:x}'.format(self.__class__.__name__, self.__hash__())
        self._action_groups = ConditionalActions(name, ui_mgrs=[self.ui_manager])
        if self.seln:
            self.seln.connect('changed', self.seln_condns_change_cb)
        self.add_notification_cb(ws_event.CHANGE_WD, self.cwd_condns_change_cb)
        self.add_notification_cb(ws_event.PMIC_CHANGE|ws_event.CHANGE_WD, self.pmic_condns_change_cb)
        self.init_action_states()
    def seln_condns_change_cb(self, seln):
        self._action_groups.set_sensitivity_for_condns(MaskedCondns.get_seln_condns(seln))
    def cwd_condns_change_cb(self, _arg=None):
        condns = MaskedCondns.get_in_pgnd_condns() | MaskedCondns.get_in_repo_condns()
        self._action_groups.set_sensitivity_for_condns(condns)
    def pmic_condns_change_cb(self, _arg=None):
        self._action_groups.set_sensitivity_for_condns(MaskedCondns.get_pmic_condns())
    def set_sensitivity_for_condns(self, condns):
        self._action_groups.set_sensitivity_for_condns(condns)
    def add_conditional_action(self, condns, action):
        self._action_groups.add_action(condns, action)
    def add_conditional_actions(self, condns, actions):
        self._action_groups.add_actions(condns, actions)
    def get_conditional_action(self, action_name):
        return self._action_groups.get_action_by_name(action_name)
    def copy_conditional_action(self, action_name, new_cond):
        return self._action_groups.copy_action(new_cond, action_name)
    def move_conditional_action(self, action_name, new_cond):
        return self._action_groups.move_action(new_cond, action_name)
    def init_action_states(self):
        condn_set = MaskedCondns.get_in_pgnd_condns() | MaskedCondns.get_in_repo_condns() | MaskedCondns.get_pmic_condns()
        if self.seln is not None:
            condn_set |= MaskedCondns.get_seln_condns(self.seln)
        self._action_groups.set_sensitivity_for_condns(condn_set)
    def create_action_button(self, action_name, use_underline=True):
        action = self.get_conditional_action(action_name)
        return gutils.ActionButton(action, use_underline=use_underline)
    def create_action_button_box(self, action_name_list, use_underline=True,
                                 horizontal=True,
                                 expand=True, fill=True, padding=0):
        if horizontal:
            box = gtk.HBox()
        else:
            box = gtk.VBox()
        for action_name in action_name_list:
            button = self.create_action_button(action_name, use_underline)
            box.pack_start(button, expand, fill, padding)
        return box
    def set_visibility_for_condns(self, condns, visible):
        self._action_groups.set_visibility_for_condns(condns, visible)

add_class_indep_actions(Condns.DONT_CARE,
    [
        ("actions_playground_menu", None, "_Playground"),
        ("actions_quit", gtk.STOCK_QUIT, "_Quit", "",
         "Quit", gtk.main_quit),
    ])

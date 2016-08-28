### Copyright (C) 2005-2016 Peter Williams <pwil3058@gmail.com>
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
Conditionally enabled GTK action groups
'''

import collections

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk

class MaskedCondns(collections.namedtuple('MaskedCondns', ['condns', 'mask'])):
    __slots__ = ()

    def __or__(self, other):
        return MaskedCondns(self.condns | other.condns, self.mask | other.mask)
    def __str__(self):
        return "MaskedCondns(condns={0:x}, mask={1:x})".format(self.condns, self.mask)

class ActionCondns:
    from .. import utils
    _flag_generator = utils.create_flag_generator()
    @staticmethod
    def new_flags_and_mask(count):
        """
        Return "count" new condition flags and their mask as a tuple
        """
        flags = [next(ActionCondns._flag_generator) for _i in range(count)]
        mask = sum(flags)
        return tuple(flags + [mask])
    @staticmethod
    def new_flag():
        return next(ActionCondns._flag_generator)

AC_DONT_CARE = 0
AC_SELN_NONE, \
AC_SELN_MADE, \
AC_SELN_UNIQUE, \
AC_SELN_PAIR, \
AC_SELN_MASK = ActionCondns.new_flags_and_mask(4)

def get_masked_seln_conditions(seln):
    if seln is None:
        return MaskedCondns(AC_DONT_CARE, AC_SELN_MASK)
    selsz = seln.count_selected_rows()
    if selsz == 0:
        return MaskedCondns(AC_SELN_NONE, AC_SELN_MASK)
    elif selsz == 1:
        return MaskedCondns(AC_SELN_MADE + AC_SELN_UNIQUE, AC_SELN_MASK)
    elif selsz == 2:
        return MaskedCondns(AC_SELN_MADE + AC_SELN_PAIR, AC_SELN_MASK)
    else:
        return MaskedCondns(AC_SELN_MADE, AC_SELN_MASK)

class ButtonGroup:
    def __init__(self, is_sensitive=True, is_visible=True, **kwargs):
        self._buttons = dict()
        self._is_visible = is_visible
        self._is_sensitive = is_sensitive
    def __getitem__(self, button_name):
        return self._buttons[button_name]
    def add_button(self, name, button, tooltip, callbacks=None):
        button.set_visible(self._is_visible)
        button.set_sensitive(self._is_sensitive)
        button.set_tooltip_text(tooltip)
        self._buttons[name] = button
        if callbacks:
            for callback_data in callbacks:
                button.connect(*callback_data)
    def add_buttons(self, button_list):
        for name, button, tooltip, callbacks in button_list:
            self.add_button(name, button, tooltip, callbacks)
    def set_sensitive(self, value):
        for button in self._buttons.values():
            button.set_sensitive(value)
        self._is_sensitive = value
    def set_visible(self, value):
        for button in self._buttons.values():
            button.set_visible(value)
        self._is_visible = value
    def get_button(self, button_name, blowup=False):
        if blowup:
            return self._buttons[button_name]
        else:
            return self._buttons.get(button_name, None)
    def __str__(self):
        ostr = "["
        first = True
        for button_name in sorted(self._buttons.keys()):
            if first:
                first = False
            else:
                ostr += ", "
            ostr += button_name
        ostr += "]"
    def create_button_box(self, button_name_list, horizontal=True, expand=True, fill=True, padding=0):
        if horizontal:
            box = Gtk.HBox()
        else:
            box = Gtk.VBox()
        for button_name in button_name_list:
            box.pack_start(self._buttons[button_name], expand=expand, fill=fill, padding=padding)
        return box

class BGUserMixin:
    def __init__(self):
        self.button_group = ButtonGroup()
        self.populate_button_group()
    def populate_button_group(self):
        pass
    def create_button_box(self, button_name_list):
        return self.button_group.create_button_box(button_name_list)

class ConditionalButtonGroups:
    class UnknownButton(Exception): pass
    def __init__(self, selection=None):
        self.groups = dict()
        self.current_condns = 0
        self.set_selection(selection)
    def _seln_condns_change_cb(self, seln):
        self.update_condns(get_masked_seln_conditions(seln))
    def set_selection(self, seln):
        if seln is None:
            return None
        self.update_condns(get_masked_seln_conditions(seln))
        return seln.connect('changed', self._seln_condns_change_cb)
    def __getitem__(self, condns):
        if condns not in self.groups:
            self.groups[condns] = ButtonGroup(is_sensitive=(condns & self.current_condns) == condns)
        return self.groups[condns]
    def update_condns(self, changed_condns):
        """
        Update the current condition state
        changed_condns: is a MaskedCondns instance
        """
        condns = changed_condns.condns | (self.current_condns & ~changed_condns.mask)
        for key_condns, group in self.groups.items():
            if changed_condns.mask & key_condns:
                group.set_sensitive((key_condns & condns) == key_condns)
        self.current_condns = condns
    def set_visibility_for_condns(self, condns, visible):
        self.groups[condns].set_visible(visible)
    def get_button(self, button_name):
        for bgrp in self.groups.values():
            button = bgrp.get_button(button_name)
            if button:
                return button
        raise self.UnknownButton(button_name)
    def connect_signal(self, button_name, signal, callback, *args, **kwargs):
        """
        Connect the callback to the "activate" signal of the named action
        """
        return self.get_button(button_name).connect(signal, callback, *args, **kwargs)
    def __str__(self):
        string = 'ConditionalButtonGroup\n'.format(self.name)
        for condns, group in self.groups.items():
            string += '\tGroup({0:x}): {2}\n'.format(condns, str(group))
        return string
    def create_button_box(self, button_name_list, horizontal=True, expand=True, fill=True, padding=0):
        if horizontal:
            box = Gtk.HBox()
        else:
            box = Gtk.VBox()
        for button_name in button_name_list:
            button = self.get_button(button_name)
            box.pack_start(button, expand=expand, fill=fill, padding=padding)
        return box

CLASS_INDEP_BGS = ConditionalButtonGroups()

# TODO: change method names to avoid accidental conflicts with other mixins
class CBGUserMixin:
    def __init__(self, selection=None):
        self.button_groups = ConditionalButtonGroups(selection)
        self.populate_button_groups()
    def populate_button_groups(self):
        pass
    def create_button_box(self, button_name_list):
        return self.button_groups.create_button_box(button_name_list)

class ClientAndButtonsWidget(Gtk.VBox):
    __g_type_name__ = "ClientAndButtonsWidget"
    CLIENT = CBGUserMixin
    BUTTONS = []
    SCROLLABLE = False
    def __init__(self, **kwargs):
        Gtk.VBox.__init__(self)
        self.client = self.CLIENT(**kwargs)
        if self.SCROLLABLE:
            from . import gutils
            self.pack_start(gutils.wrap_in_scrolled_window(self.client), expand=True, fill=True, padding=0)
        else:
            self.pack_start(self.client, expand=True, fill=True, padding=0)
        self.pack_start(self.client.create_button_box(self.BUTTONS), expand=False, fill=True, padding=0)
        self.show_all()

class ConditionalActionGroups:
    class UnknownAction(Exception): pass
    def __init__(self, name, ui_mgrs=None, selection=None):
        self.groups = dict()
        self.current_condns = 0
        self.ui_mgrs = [] if ui_mgrs is None else ui_mgrs[:]
        self.name = name
        self.set_selection(selection)
    def _group_name(self, condns):
        return '{0}:{1:x}'.format(self.name, condns)
    def _seln_condns_change_cb(self, seln):
        self.update_condns(get_masked_seln_conditions(seln))
    def set_selection(self, seln):
        if seln is None:
            return None
        self.update_condns(get_masked_seln_conditions(seln))
        return seln.connect('changed', self._seln_condns_change_cb)
    def __getitem__(self, condns):
        if condns not in self.groups:
            self.groups[condns] = Gtk.ActionGroup(self._group_name(condns))
            self.groups[condns].set_sensitive((condns & self.current_condns) == condns)
            for ui_mgr in self.ui_mgrs:
                ui_mgr.insert_action_group(self.groups[condns], -1)
        return self.groups[condns]
    def copy_action(self, new_condns, action_name):
        action = self.get_action(action_name)
        if not action:
            raise self.UnknownAction(action)
        self[new_condns].add_action(action)
    def move_action(self, new_condns, action_name):
        for agrp in self.groups.values():
            action = agrp.get_action(action_name)
            if not action:
                continue
            agrp.remove_action(action)
            self[new_condns].add_action(action)
            return
        raise self.UnknownAction(action)
    def update_condns(self, changed_condns):
        """
        Update the current condition state
        changed_condns: is a MaskedCondns instance
        """
        condns = changed_condns.condns | (self.current_condns & ~changed_condns.mask)
        for key_condns, group in self.groups.items():
            if changed_condns.mask & key_condns:
                group.set_sensitive((key_condns & condns) == key_condns)
        self.current_condns = condns
    def set_visibility_for_condns(self, condns, visible):
        self.groups[condns].set_visible(visible)
    def add_ui_mgr(self, ui_mgr):
        self.ui_mgrs.append(ui_mgr)
        for agrp in self.groups.values():
            ui_mgr.insert_action_group(agrp, -1)
    def get_action(self, action_name):
        for agrp in self.groups.values():
            action = agrp.get_action(action_name)
            if action:
                return action
        return None
    def connect_activate(self, action_name, callback, *user_data):
        """
        Connect the callback to the "activate" signal of the named action
        """
        return self.get_action(action_name).connect('activate', callback, *user_data)
    def __str__(self):
        string = 'ConditionalActionGroups({0}): condns={1:x}\n'.format(self.name, self.current_condns)
        for condns, group in self.groups.items():
            name = group.get_name()
            member_names = '['
            for member_name in [action.get_name() for action in group.list_actions()]:
                member_names += '{0}, '.format(member_name)
            member_names += ']'
            string += '\tGroup({0:x},{1}): {2}\n'.format(condns, name, member_names)
        return string
    def create_action_button(self, action_name, use_underline=True):
        from . import gutils
        action = self.get_action(action_name)
        return gutils.creat_button_from_action(action, use_underline=use_underline)
    def create_action_button_box(self, action_name_list, use_underline=True,
                                 horizontal=True,
                                 expand=True, fill=True, padding=0):
        if horizontal:
            box = Gtk.HBox()
        else:
            box = Gtk.VBox()
        for action_name in action_name_list:
            button = self.create_action_button(action_name, use_underline)
            box.pack_start(button, expand, fill, padding)
        return box

CLASS_INDEP_AGS = ConditionalActionGroups('class_indep')

class UIManager(Gtk.UIManager):
    __g_type_name__ = "UIManager"
    # TODO: check to see if this workaround is still necessary
    def __init__(self):
        Gtk.UIManager.__init__(self)
        self.connect('connect-proxy', self._ui_manager_connect_proxy)
    @staticmethod
    def _ui_manager_connect_proxy(_ui_mgr, action, widget):
        tooltip = action.get_property('tooltip')
        if isinstance(widget, Gtk.MenuItem) and tooltip:
            widget.set_tooltip_text(tooltip)

# TODO: change method names to avoid accidental conflicts with other mixins
class CAGandUIManager:
    '''This is a "mix in" class and needs to be merged with a Gtk.Widget() descendant'''
    UI_DESCR = '''<ui></ui>'''
    def __init__(self, selection=None, popup=None):
        self.ui_manager = UIManager()
        CLASS_INDEP_AGS.add_ui_mgr(self.ui_manager)
        name = '{0}:{1:x}'.format(self.__class__.__name__, self.__hash__())
        self.action_groups = ConditionalActionGroups(name, ui_mgrs=[self.ui_manager], selection=selection)
        self.populate_action_groups()
        self.ui_manager.add_ui_from_string(self.UI_DESCR)
        self._popup_cb_id = self._popup = None
        self.set_popup(popup)
    def populate_action_groups(self):
        assert False, _("should be derived in subclass")
    @staticmethod
    def _button_press_cb(widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            if event.button == 3 and widget._popup:
                menu = widget.ui_manager.get_widget(widget._popup)
                menu.popup(None, None, None, None, event.button, event.time)
                return True
        return False
    def set_popup(self, popup):
        if self._popup_cb_id is None:
            self._popup_cb_id = self.connect('button_press_event', self._button_press_cb)
            if popup is None:
                self.enable_popup(False)
        elif self._popup is None and popup is not None:
            self.enable_popup(True)
        elif popup is None:
            self.enable_popup(False)
        self._popup = popup
    def enable_popup(self, enable):
        if self._popup_cb_id is not None:
            if enable:
                self.handler_unblock(self._popup_cb_id)
            else:
                self.handler_block(self._popup_cb_id)
    def set_visibility_for_condns(self, condns, visible):
        self.action_groups.set_visibility_for_condns(condns, visible)

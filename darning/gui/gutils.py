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

import collections

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk

def get_gtk_window(widget):
    gtk_window = widget
    while True:
        temp = gtk_window.get_parent()
        if temp:
            gtk_window = temp
        else:
            break
    return gtk_window

class FramedScrollWindow(Gtk.Frame):
    __g_type_name__ = "FramedScrollWindow"
    def __init__(self, policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)):
        Gtk.Frame.__init__(self)
        self._sw = Gtk.ScrolledWindow()
        Gtk.Frame.add(self, self._sw)
    def add(self, widget):
        self._sw.add(widget)
    def set_policy(self, hpolicy, vpolicy):
        return self._sw.set_policy(hpolicy, vpolicy)
    def get_hscrollbar(self):
        return self._sw.get_hscrollbar()
    def get_vscrollbar(self):
        return self._sw.get_hscrollbar()
    def set_min_content_width(self, width):
        return self._sw.set_min_content_width(width)
    def set_min_content_height(self, height):
        return self._sw.set_min_content_height(height)

def wrap_in_scrolled_window(widget, policy=(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC), with_frame=False, use_widget_size=False):
    scrw = FramedScrollWindow() if with_frame else Gtk.ScrolledWindow()
    scrw.set_policy(policy[0], policy[1])
    scrw.add(widget)
    if use_widget_size:
        vw, vh = widget.get_size_request()
        if vw > 0:
            scrw.set_min_content_width(vw)
        if vh > 0:
            scrw.set_min_content_height(vh)
    scrw.show_all()
    return scrw

class RadioButtonFramedVBox(Gtk.Frame):
    def __init__(self, title, labels):
        Gtk.Frame.__init__(self, title)
        self.vbox = Gtk.VBox()
        self.buttons = [Gtk.RadioButton(label=labels[0], group=None)]
        for label in labels[1:]:
            self.buttons.append(Gtk.RadioButton(label=label, group=self.buttons[0]))
        for button in self.buttons:
            self.vbox.pack_start(button, expand=True, fill=False, padding=0)
        self.buttons[0].set_active(True)
        self.add(self.vbox)
        self.show_all()
    def get_selected_index(self):
        for index in range(len(self.buttons)):
            if self.buttons[index].get_active():
                return index
        return None

class PopupUser:
    def __init__(self):
        self._gtk_window = None
    def _get_gtk_window(self):
        if not self._gtk_window:
            try:
                temp = self.get_parent()
            except AttributeError:
                return None
            while temp:
                self._gtk_window = temp
                try:
                    temp = temp.get_parent()
                except AttributeError:
                    return None
        return self._gtk_window

class MappedManager:
    def __init__(self):
        self.is_mapped = False
        self.connect("map", self._map_cb)
        self.connect("unmap", self._unmap_cb)
    def _map_cb(self, widget=None):
        self.is_mapped = True
        self.map_action()
    def _unmap_cb(self, widget=None):
        self.is_mapped = False
        self.unmap_action()
    def map_action(self):
        pass
    def unmap_action(self):
        pass

_KEYVAL_UP_ARROW = Gdk.keyval_from_name('Up')
_KEYVAL_DOWN_ARROW = Gdk.keyval_from_name('Down')

class EntryWithHistory(Gtk.Entry):
    def __init__(self, max_chars=0):
        Gtk.Entry.__init__(self)
        self.set_max_width_chars(max_chars)
        self._history_list = []
        self._history_index = 0
        self._history_len = 0
        self._saved_text = ''
        self._key_press_cb_id = self.connect("key_press_event", self._key_press_cb)
    def _key_press_cb(self, widget, event):
        if event.keyval in [_KEYVAL_UP_ARROW, _KEYVAL_DOWN_ARROW]:
            if event.keyval == _KEYVAL_UP_ARROW:
                if self._history_index < self._history_len:
                    if self._history_index == 0:
                        self._saved_text = self.get_text()
                    self._history_index += 1
                    self.set_text(self._history_list[-self._history_index])
                    self.set_position(-1)
            elif event.keyval == _KEYVAL_DOWN_ARROW:
                if self._history_index > 0:
                    self._history_index -= 1
                    if self._history_index > 0:
                        self.set_text(self._history_list[-self._history_index])
                    else:
                        self.set_text(self._saved_text)
                    self.set_position(-1)
            return True
        else:
            return False
    def clear_to_history(self):
        self._history_index = 0
        # beware the empty command string
        text = self.get_text().rstrip()
        self.set_text("")
        # don't save empty entries or ones that start with white space
        if not text or text[0] in [' ', '\t']:
            return
        # no adjacent duplicate entries allowed
        if (self._history_len == 0) or (text != self._history_list[-1]):
            self._history_list.append(text)
            self._history_len = len(self._history_list)
    def get_text_and_clear_to_history(self):
        text = self.get_text().rstrip()
        self.clear_to_history()
        return text

def _combo_entry_changed_cb(combo, entry):
    if combo.get_active() == -1:
        combo.saved_text = entry.get_text()
    else:
        text = combo.saved_text.rstrip()
        # no duplicates, empty strings or strings starting with white space
        if text and text[0] not in [' ', '\t'] and text not in combo.entry_set:
            combo.entry_set.add(text)
            combo.prepend_text(text)
        combo.saved_text = ''
    return False

def _combo_get_text(combo):
    return combo.get_child().get_text()

def _combo_set_text(combo, text):
    text = text.rstrip()
    if text and text[0] not in [' ', '\t'] and text not in combo.entry_set:
        combo.prepend_text(text)
        combo.set_active(0)
        combo.entry_set.add(text)
    else:
        combo.get_child().set_text(text)

# WORKAROUND: can't extend a ComboBox with entry
def new_mutable_combox_text_with_entry(entries=None):
    combo = Gtk.ComboBoxText.new_with_entry()
    combo.get_text = lambda : _combo_get_text(combo)
    combo.set_text = lambda text: _combo_set_text(combo, text)
    combo.saved_text = ""
    combo.entry_set = set()
    for entry in entries if entries else []:
        if entry not in combo.entry_set:
            combo.append_text(entry)
            combo.entry_set.add(entry)
    combo.set_active(-1)
    combo.get_child().connect('changed', lambda entry: _combo_entry_changed_cb(combo, entry))
    return combo

class ActionButton(Gtk.Button):
    def __init__(self, action, use_underline=True):
        Gtk.Button.__init__(self)
        label = action.get_label()
        icon_name = action.get_icon_name()
        stock_id = action.get_stock_id()
        if label:
            self.set_label(label)
            self.set_use_stock(False)
            if icon_name:
                self.set_image(Gtk.Image.new_from_icon_name(icon_name))
        elif stock_id:
            self.set_label(stock_id)
            self.set_use_stock(True)
        elif icon_name:
            self.set_image(Gtk.Image.new_from_icon_name(icon_name))
        self.set_use_underline(use_underline)
        self.set_tooltip_text(action.get_property("tooltip"))
        self.connect("clicked", lambda _button: action.activate())

class ActionCheckButton(Gtk.CheckButton):
    def __init__(self, action, use_underline=True):
        Gtk.CheckButton.__init__(self, label=action.get_property("label"), use_underline=use_underline)
        self.set_tooltip_text(action.get_property("tooltip"))
        self.connect("toggled", lambda _button: action.activate())

def creat_button_from_action(action, use_underline=True):
    if isinstance(action, Gtk.ToggleAction):
        return ActionCheckButton(action)
    else:
        return ActionButton(action, use_underline)

class ActionButtonList:
    def __init__(self, action_group_list, action_name_list=None, use_underline=True):
        self.list = []
        self.dict = {}
        if action_name_list:
            for a_name in action_name_list:
                for a_group in action_group_list:
                    action = a_group.get_action(a_name)
                    if action:
                        button = creat_button_from_action(action, use_underline)
                        self.list.append(button)
                        self.dict[a_name] = button
                        break
        else:
            for a_group in action_group_list:
                for action in a_group.list_actions():
                    button = creat_button_from_action(action, use_underline)
                    self.list.append(button)
                    self.dict[action.get_name()] = button

class ActionHButtonBox(Gtk.HBox):
    def __init__(self, action_group_list, action_name_list=None,
                 use_underline=True, expand=True, fill=True, padding=0):
        Gtk.HBox.__init__(self)
        self.button_list = ActionButtonList(action_group_list, action_name_list, use_underline)
        for button in self.button_list.list:
            self.pack_start(button, expand=expand, fill=fill, padding=padding)

class TimeOutController:
    ToggleData = collections.namedtuple('ToggleData', ['name', 'label', 'tooltip', 'stock_id'])
    def __init__(self, toggle_data, function=None, is_on=True, interval=10000):
        self._interval = abs(interval)
        self._timeout_id = None
        self._function = function
        self.toggle_action = Gtk.ToggleAction(
                toggle_data.name, toggle_data.label,
                toggle_data.tooltip, toggle_data.stock_id
            )
        # TODO: find out how to do this in PyGTK3
        #self.toggle_action.set_menu_item_type(Gtk.CheckMenuItem)
        #self.toggle_action.set_tool_item_type(Gtk.ToggleToolButton)
        self.toggle_action.connect("toggled", self._toggle_acb)
        self.toggle_action.set_active(is_on)
    def _toggle_acb(self, _action=None):
        if self.toggle_action.get_active():
            self._restart_cycle()
        else:
            self._stop_cycle()
    def _timeout_cb(self):
        if self._function:
            self._function()
        return self.toggle_action.get_active()
    def _stop_cycle(self):
        if self._timeout_id:
            GObject.source_remove(self._timeout_id)
            self._timeout_id = None
    def _restart_cycle(self):
        self._stop_cycle()
        self._timeout_id = GObject.timeout_add(self._interval, self._timeout_cb)
    def set_function(self, function):
        self._stop_cycle()
        self._function = function
        self._toggle_acb()
    def set_interval(self, interval):
        if interval > 0 and interval != self._interval:
            self._interval = interval
            self._toggle_acb()
    def get_interval(self):
        return self._interval

TOC_DEFAULT_REFRESH_TD = TimeOutController.ToggleData("auto_refresh_toggle", _('Auto _Refresh'), _('Turn data auto refresh on/off'), Gtk.STOCK_REFRESH)

class RefreshController(TimeOutController):
    def __init__(self, toggle_data=None, function=None, is_on=True, interval=10000):
        if toggle_data is None:
            toggle_data = TOC_DEFAULT_REFRESH_TD
        TimeOutController.__init__(self, toggle_data, function=function, is_on=is_on, interval=interval)

TOC_DEFAULT_SAVE_TD = TimeOutController.ToggleData("auto_save_toggle", _('Auto _Save'), _('Turn data auto save on/off'), Gtk.STOCK_SAVE)

class SaveController(TimeOutController):
    def __init__(self, toggle_data=None, function=None, is_on=True, interval=10000):
        if toggle_data is None:
            toggle_data = TOC_DEFAULT_SAVE_TD
        TimeOutController.__init__(self, toggle_data, function=function, is_on=is_on, interval=interval)

class LabelledEntry(Gtk.HBox):
    def __init__(self, label="", max_chars=0, text=""):
        Gtk.HBox.__init__(self)
        self.label = Gtk.Label(label=label)
        self.pack_start(self.label, expand=False, fill=True, padding=0)
        self.entry = EntryWithHistory(max_chars)
        self.pack_start(self.entry, expand=True, fill=True, padding=0)
        self.entry.set_text(text)
    def get_text_and_clear_to_history(self):
        return self.entry.get_text_and_clear_to_history()
    def set_label(self, text):
        self.label.set_text(text)

class LabelledText(Gtk.HBox):
    def __init__(self, label="", text="", min_chars=0):
        Gtk.HBox.__init__(self)
        self.label = Gtk.Label(label=label)
        self.pack_start(self.label, expand=False, fill=True, padding=0)
        self.entry = Gtk.Entry()
        self.entry.set_width_chars(min_chars)
        self.pack_start(self.entry, expand=True, fill=True, padding=0)
        self.entry.set_text(text)
        self.entry.set_editable(False)

class SplitBar(Gtk.HBox):
    __g_type_name__ = "SplitBar"
    def __init__(self, expand_lhs=True, expand_rhs=False):
        Gtk.HBox.__init__(self)
        self.lhs = Gtk.HBox()
        self.pack_start(self.lhs, expand=expand_lhs, fill=True, padding=0)
        self.rhs = Gtk.HBox()
        self.pack_end(self.rhs, expand=expand_rhs, fill=True, padding=0)

def _ui_manager_connect_proxy(_ui_mgr, action, widget):
    tooltip = action.get_property('tooltip')
    if isinstance(widget, Gtk.MenuItem) and tooltip:
        widget.set_tooltip_text(tooltip)

def yield_to_pending_events():
    while True:
        Gtk.main_iteration()
        if not Gtk.events_pending():
            break

class UIManager(Gtk.UIManager):
    def __init__(self):
        Gtk.UIManager.__init__(self)
        self.connect('connect-proxy', _ui_manager_connect_proxy)

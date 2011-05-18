### Copyright (C) 2007 Peter Williams <peter_ono@users.sourceforge.net>

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

import gtk, gobject

def pygtk_version_ge(version):
    for index in range(len(version)):
        if gtk.pygtk_version[index] >  version[index]:
            return True
        elif gtk.pygtk_version[index] <  version[index]:
            return False
    return True

if pygtk_version_ge((2, 12)):
    def set_widget_tooltip_text(widget, text):
        widget.set_tooltip_text(text)
else:
    tooltips = gtk.Tooltips()
    tooltips.enable()

    def set_widget_tooltip_text(widget, text):
        tooltips.set_tip(widget, text)

def wrap_in_scrolled_window(widget, policy=(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC), with_frame=True, label=None):
    scrw = gtk.ScrolledWindow()
    scrw.set_policy(policy[0], policy[1])
    scrw.add(widget)
    if with_frame:
        frame = gtk.Frame(label)
        frame.add(scrw)
        frame.show_all()
        return frame
    else:
        scrw.show_all()
        return scrw

class RadioButtonFramedVBox(gtk.Frame):
    def __init__(self, title, labels):
        gtk.Frame.__init__(self, title)
        self.vbox = gtk.VBox()
        self.buttons = [gtk.RadioButton(label=labels[0], group=None)]
        for label in labels[1:]:
            self.buttons.append(gtk.RadioButton(label=label, group=self.buttons[0]))
        for button in self.buttons:
            self.vbox.pack_start(button, fill=False)
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

_KEYVAL_UP_ARROW = gtk.gdk.keyval_from_name('Up')
_KEYVAL_DOWN_ARROW = gtk.gdk.keyval_from_name('Down')

class EntryWithHistory(gtk.Entry):
    def __init__(self, max_chars=0):
        gtk.Entry.__init__(self, max_chars)
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

class ActionButton(gtk.Button):
    def __init__(self, action, use_underline=True):
        label = action.get_property("label")
        stock_id = action.get_property("stock-id")
        if label is "":
            # Empty (NB not None) label means use image only
            gtk.Button.__init__(self, use_underline=use_underline)
            image = gtk.Image()
            image.set_from_stock(stock_id, gtk.ICON_SIZE_BUTTON)
            self.add(image)
        else:
            gtk.Button.__init__(self, stock=stock_id, label=label, use_underline=use_underline)
        set_widget_tooltip_text(self, action.get_property("tooltip"))
        action.connect_proxy(self)

class ActionButtonList:
    def __init__(self, action_group_list, action_name_list=None, use_underline=True):
        self.list = []
        self.dict = {}
        if action_name_list:
            for a_name in action_name_list:
                for a_group in action_group_list:
                    action = a_group.get_action(a_name)
                    if action:
                        button = ActionButton(action, use_underline)
                        self.list.append(button)
                        self.dict[a_name] = button
                        break
        else:
            for a_group in action_group_list:
                for action in a_group.list_actions():
                    button = ActionButton(action, use_underline)
                    self.list.append(button)
                    self.dict[action.get_name()] = button

class ActionHButtonBox(gtk.HBox):
    def __init__(self, action_group_list, action_name_list=None,
                 use_underline=True, expand=True, fill=True, padding=0):
        gtk.HBox.__init__(self)
        self.button_list = ActionButtonList(action_group_list, action_name_list, use_underline)
        for button in self.button_list.list:
            self.pack_start(button, expand, fill, padding)

TOC_NAME, TOC_LABEL, TOC_TOOLTIP, TOC_STOCK_ID = list(range(4))

class TimeOutController():
    def __init__(self, toggle_data, function=None, is_on=True, interval=10000):
        self._interval = abs(interval)
        self._timeout_id = None
        self._function = function
        self.toggle_action = gtk.ToggleAction(
                toggle_data[TOC_NAME], toggle_data[TOC_LABEL],
                toggle_data[TOC_TOOLTIP], toggle_data[TOC_STOCK_ID]
            )
        self.toggle_action.connect("toggled", self._toggle_acb)
        self.toggle_action.set_active(is_on)
        self._toggle_acb()
    def _toggle_acb(self, _action=None):
        if self.toggle_action.get_active():
            self._timeout_id = gobject.timeout_add(self._interval, self._timeout_cb)
    def _timeout_cb(self):
        if self._function:
            self._function()
        return self.toggle_action.get_active()
    def stop_cycle(self):
        if self._timeout_id:
            gobject.source_remove(self._timeout_id)
            self._timeout_id = None
    def restart_cycle(self):
        self.stop_cycle()
        self._toggle_acb()
    def set_function(self, function):
        self.stop_cycle()
        self._function = function
        self._toggle_acb()
    def set_interval(self, interval):
        if interval > 0 and interval != self._interval:
            self._interval = interval
            self.restart_cycle()
    def get_interval(self):
        return self._interval
    def set_active(self, active=True):
        if active != self.toggle_action.get_active():
            self.toggle_action.set_active(active)
        self.restart_cycle()

TOC_DEFAULT_REFRESH_TD = ["auto_refresh_toggle", "Auto _Refresh", "Turn data auto refresh on/off", gtk.STOCK_REFRESH]

class RefreshController(TimeOutController):
    def __init__(self, toggle_data=None, function=None, is_on=True, interval=10000):
        if toggle_data is None:
            toggle_data = TOC_DEFAULT_REFRESH_TD
        TimeOutController.__init__(self, toggle_data, function=function, is_on=is_on, interval=interval)

TOC_DEFAULT_SAVE_TD = ["auto_save_toggle", "Auto _Save", "Turn data auto save on/off", gtk.STOCK_SAVE]

class SaveController(TimeOutController):
    def __init__(self, toggle_data=None, function=None, is_on=True, interval=10000):
        if toggle_data is None:
            toggle_data = TOC_DEFAULT_SAVE_TD
        TimeOutController.__init__(self, toggle_data, function=function, is_on=is_on, interval=interval)

class LabelledEntry(gtk.HBox):
    def __init__(self, label="", max_chars=0, text=""):
        gtk.HBox.__init__(self)
        self.label = gtk.Label(label)
        self.pack_start(self.label, expand=False)
        self.entry = EntryWithHistory(max_chars)
        self.pack_start(self.entry, expand=True, fill=True)
        self.entry.set_text(text)

class LabelledText(gtk.HBox):
    def __init__(self, label="", text="", min_chars=0):
        gtk.HBox.__init__(self)
        self.label = gtk.Label(label)
        self.pack_start(self.label, expand=False)
        self.entry = gtk.Entry()
        self.entry.set_width_chars(min_chars)
        self.pack_start(self.entry, expand=True, fill=True)
        self.entry.set_text(text)
        self.entry.set_editable(False)

class SplitBar(gtk.HBox):
    def __init__(self, expand_lhs=True, expand_rhs=False):
        gtk.HBox.__init__(self)
        self.lhs = gtk.HBox()
        self.pack_start(self.lhs, expand=expand_lhs)
        self.rhs = gtk.HBox()
        self.pack_end(self.rhs, expand=expand_rhs)

def _ui_manager_connect_proxy(_ui_mgr, action, widget):
    tooltip = action.get_property('tooltip')
    if isinstance(widget, gtk.MenuItem) and tooltip:
        widget.set_tooltip_text(tooltip)

class UIManager(gtk.UIManager):
    def __init__(self):
        gtk.UIManager.__init__(self)
        self.connect('connect-proxy', _ui_manager_connect_proxy)

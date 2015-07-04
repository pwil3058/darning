### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>

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

import gtk

from .. import utils

from . import dialogue
from . import ws_event

try:
    import vte

    AVAILABLE = True

    class Terminal(gtk.HBox, ws_event.Listener):
        def __init__(self):
            from . import ifce
            gtk.HBox.__init__(self, False, 4)
            ws_event.Listener.__init__(self)
            self._vte = vte.Terminal()
            self._vte.set_size(self._vte.get_column_count(), 10)
            self._vte.set_size_request(200, 50)
            self._vte.set_scrollback_lines(-1)
            self._vte.show()
            self._vte.connect('button_press_event', self._button_press_cb)
            scrbar = gtk.VScrollbar(self._vte.get_adjustment())
            scrbar.show()
            self.pack_start(self._vte)
            self.pack_start(scrbar, False, False, 0)
            self.show_all()
            self._pid = self._vte.fork_command()
            self.add_notification_cb(ifce.E_CHANGE_WD, self._cwd_cb)
        def _cwd_cb(self, **kwargs):
            self.set_cwd(os.getcwd())
        def set_cwd(self, path):
            self._vte.feed_child("cd %s\n" % utils.path_rel_home(path))
        def _button_press_cb(self, widget, event):
            if event.type == gtk.gdk.BUTTON_PRESS:
                if event.button == 3:
                    menu = gtk.Menu()
                    copy_item = gtk.MenuItem(label=_('Copy'))
                    copy_item.set_sensitive(widget.get_has_selection())
                    copy_item.connect_object('activate', vte.Terminal.copy_clipboard, widget)
                    paste_item = gtk.MenuItem(label=_('Paste'))
                    paste_item.set_sensitive(gtk.Clipboard().wait_is_text_available())
                    paste_item.connect_object('activate', vte.Terminal.paste_clipboard, widget)
                    menu.append(copy_item)
                    menu.append(paste_item)
                    menu.show_all()
                    menu.popup(None, None, None, event.button, event.time)
                    return True
            return False
except ImportError:
    AVAILABLE = False

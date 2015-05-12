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

'''A scrollable text view widget that uses right margin marker
(if available) and also ensures text is utf-8 friendly before
insertion'''

import hashlib

import gtk
import pango

from .. import utils

try:
    from gtksourceview2 import Buffer as _Buffer
    from gtksourceview2 import View as _View
except ImportError:
    try:
        from gtksourceview import SourceBuffer as _Buffer
        from gtksourceview import SourceView as _SourceView
        class _View(_SourceView):
            def __init__(self, buffer=None):
                _SourceView.__init__(self, buffer=buffer if buffer else _Buffer())
            def set_right_margin_position(self, val):
                self.set_margin(val)
            def set_show_right_margin(self, val):
                self.set_show_margin(val)
    except ImportError:
        class _Buffer(gtk.TextBuffer):
            def __init__(self):
                gtk.TextBuffer.__init__(self)
            def begin_not_undoable_action(self):
                pass
            def end_not_undoable_action(self):
                pass
        class _View(gtk.TextView):
            def __init__(self, buffer=None):
                gtk.TextView.__init__(self, buffer=buffer if buffer else _Buffer())
            def set_right_margin_position(self, val):
                pass
            def set_show_right_margin(self, val):
                pass

class Buffer(_Buffer):
    def __init__(self):
        _Buffer.__init__(self)
    def set_text(self, text, undoable=False):
        return _Buffer.set_text(self, utils.make_utf8_compliant(text))
    def insert(self, text_iter, text):
        return _Buffer.insert(self, text_iter, utils.make_utf8_compliant(text))
    def insert_at_cursor(self, text):
        return _Buffer.insert_at_cursor(self, utils.make_utf8_compliant(text))
    def insert_interactive(self, text_iter, text, default_editable):
        return _Buffer.insert_interactive(self, text_iter, utils.make_utf8_compliant(text), default_editable)
    def insert_interactive_at_cursor(self, text, default_editable):
        return _Buffer.insert_interactive_at_cursor(self, utils.make_utf8_compliant(text), default_editable)
    def insert_with_tags(self, text_iter, text, *args):
        return _Buffer.insert_with_tags(self, text_iter, utils.make_utf8_compliant(text), *args)
    def insert_with_tags_by_name(self, text_iter, text, *args):
        return _Buffer.insert_with_tags_by_name(self, text_iter, utils.make_utf8_compliant(text), *args)

class View(_View):
    def __init__(self, buffer=None, width_in_chars=81, aspect_ratio=0.33, fdesc=None):
        _View.__init__(self, buffer=buffer if buffer else Buffer())
        self._fdesc = fdesc if fdesc is not None else pango.FontDescription("mono 10")
        self.modify_font(self._fdesc)
        self._width_in_chars = width_in_chars
        self._aspect_ratio = aspect_ratio
        self._adjust_size_request()
    def _adjust_size_request(self):
        context = self.get_pango_context()
        metrics = context.get_metrics(self._fdesc)
        width = pango.PIXELS(metrics.get_approximate_char_width() * self._width_in_chars)
        height = int(width * self._aspect_ratio)
        x, y = self.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT, width, height)
        self.set_size_request(x, y)
    def set_width_in_chars(self, width_in_chars):
        self._width_in_chars = width_in_chars
        self._adjust_size_request()
    def set_aspect_ratio(self, aspect_ratio):
        self._aspect_ratio = aspect_ratio
        self._adjust_size_request()
    def set_font(self, fdesc):
        self._fdesc = fdesc
        self.modify_font(self._fdesc)
        self._adjust_size_request()

class Widget(gtk.VBox):
    TEXT_VIEW = View
    def __init__(self, width_in_chars=81, aspect_ratio=0.33, fdesc=None):
        gtk.VBox.__init__(self)
        # Space to add stuff at the top
        self.top_hbox = gtk.HBox()
        self.pack_start(self.top_hbox, expand=False)
        # Set up text buffer and view
        self.view = self.TEXT_VIEW(width_in_chars=width_in_chars, aspect_ratio=aspect_ratio, fdesc=fdesc)
        self._initialize_contents()
        self._scrolled_window = gtk.ScrolledWindow()
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self._scrolled_window.add(self.view)
        self.pack_start(self._scrolled_window)
        # Space to add stuff at the bottom
        self.bottom_hbox = gtk.HBox()
        self.pack_start(self.bottom_hbox, expand=False)
    @property
    def bfr(self):
        return self.view.get_buffer()
    @property
    def digest(self):
        return hashlib.sha256(self.get_contents()).digest()
    def set_policy(self, hpol, vpol):
        return self._scrolled_window.set_policy(hpol, vpol)
    def set_contents(self, text, undoable=False):
        if not undoable:
            self.bfr.begin_not_undoable_action()
        result = self.bfr.set_text(text)
        if not undoable:
            self.bfr.end_not_undoable_action()
        return result
    def _initialize_contents(self):
        self.set_contents('')
    def get_contents(self):
        start_iter = self.bfr.get_start_iter()
        end_iter = self.bfr.get_end_iter()
        return self.bfr.get_text(start_iter, end_iter)

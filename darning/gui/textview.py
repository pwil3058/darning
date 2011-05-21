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

'''A scrollable text view widget that uses right margin marker
(if available) and also ensures text is utf-8 friendly before
insertion'''

import gtk
import pango

from darning import utils

try:
    try:
        import gtksourceview2
        class Buffer(gtksourceview2.Buffer):
            def __init__(self):
                gtksourceview2.Buffer.__init__(self)
            def set_text(self, text, undoable=False):
                return gtksourceview2.Buffer.set_text(self, utils.make_utf8_compliant(text))
            def insert(self, text_iter, text):
                return gtksourceview2.Buffer.insert(self, text_iter, utils.make_utf8_compliant(text))
            def insert_at_cursor(self, text):
                return gtksourceview2.Buffer.insert_at_cursor(self, utils.make_utf8_compliant(text))
            def insert_interactive(self, text_iter, text, default_editable):
                return gtksourceview2.Buffer.insert_interactive(self, text_iter, utils.make_utf8_compliant(text), default_editable)
            def insert_interactive_at_cursor(self, text, default_editable):
                return gtksourceview2.Buffer.insert_interactive_at_cursor(self, utils.make_utf8_compliant(text), default_editable)
            def insert_with_tags(self, text_iter, text, *args):
                return gtksourceview2.Buffer.insert_with_tags(self, text_iter, utils.make_utf8_compliant(text), *args)
            def insert_with_tags_by_name(self, text_iter, text, *args):
                return gtksourceview2.Buffer.insert_with_tags_by_name(self, text_iter, utils.make_utf8_compliant(text), *args)
        class View(gtksourceview2.View):
            def __init__(self, buffer=None):
                gtksourceview2.View.__init__(self, buffer=buffer if buffer else Buffer())
    except ImportError:
        import gtksourceview
        class Buffer(gtksourceview.SourceBuffer):
            def __init__(self):
                gtksourceview.SourceBuffer.__init__(self)
            def set_text(self, text, undoable=False):
                return gtksourceview.SourceBuffer.set_text(self, utils.make_utf8_compliant(text))
            def insert(self, text_iter, text):
                return gtksourceview.SourceBuffer.insert(self, text_iter, utils.make_utf8_compliant(text))
            def insert_at_cursor(self, text):
                return gtksourceview.SourceBuffer.insert_at_cursor(self, utils.make_utf8_compliant(text))
            def insert_interactive(self, text_iter, text, default_editable):
                return gtksourceview.SourceBuffer.insert_interactive(self, text_iter, utils.make_utf8_compliant(text), default_editable)
            def insert_interactive_at_cursor(self, text, default_editable):
                return gtksourceview.SourceBuffer.insert_interactive_at_cursor(self, utils.make_utf8_compliant(text), default_editable)
            def insert_with_tags(self, text_iter, text, *args):
                return gtksourceview.SourceBuffer.insert_with_tags(self, text_iter, utils.make_utf8_compliant(text), *args)
            def insert_with_tags_by_name(self, text_iter, text, *args):
                return gtksourceview.SourceBuffer.insert_with_tags_by_name(self, text_iter, utils.make_utf8_compliant(text), *args)
        class View(gtksourceview.SourceView):
            def __init__(self, buffer=None):
                gtksourceview.SourceView.__init__(self, buffer=buffer if buffer else Buffer())
            def set_right_margin_position(self, val):
                self.set_margin(val)
            def set_show_right_margin(self, val):
                self.set_show_margin(val)
except ImportError:
    class Buffer(gtk.TextBuffer):
        def __init__(self):
            gtk.TextBuffer.__init__(self)
        def begin_not_undoable_action(self):
            pass
        def end_not_undoable_action(self):
            pass
        def set_text(self, text, undoable=False):
            return gtk.TextBuffer.set_text(self, utils.make_utf8_compliant(text))
        def insert(self, text_iter, text):
            return gtk.TextBuffer.insert(self, text_iter, utils.make_utf8_compliant(text))
        def insert_at_cursor(self, text):
            return gtk.TextBuffer.insert_at_cursor(self, utils.make_utf8_compliant(text))
        def insert_interactive(self, text_iter, text, default_editable):
            return gtk.TextBuffer.insert_interactive(self, text_iter, utils.make_utf8_compliant(text), default_editable)
        def insert_interactive_at_cursor(self, text, default_editable):
            return gtk.TextBuffer.insert_interactive_at_cursor(self, utils.make_utf8_compliant(text), default_editable)
        def insert_with_tags(self, text_iter, text, *args):
            return gtk.TextBuffer.insert_with_tags(self, text_iter, utils.make_utf8_compliant(text), *args)
        def insert_with_tags_by_name(self, text_iter, text, *args):
            return gtk.TextBuffer.insert_with_tags_by_name(self, text_iter, utils.make_utf8_compliant(text), *args)
    class View(gtk.TextView):
        def __init__(self, buffer=None):
            gtk.TextView.__init__(self, buffer=buffer if buffer else Buffer())
        def set_right_margin_position(self, val):
            pass
        def set_show_margin(self, val):
            pass

class Widget(gtk.ScrolledWindow):
    def __init__(self, width_in_chars=81, fdesc=None):
        gtk.ScrolledWindow.__init__(self)
        # Set up text buffer and view
        self.view = View()
        self.text_buffer = self.view.get_buffer()
        if fdesc is None:
            fdesc = pango.FontDescription("mono, 10")
        self.view.modify_font(fdesc)
        self._width_in_chars = width_in_chars
        self.set_width_in_chars(self._width_in_chars)
        self._initialize_contents()
        self.add(self.view)
    def _adjust_size_request(self):
        context = self.view.get_pango_context()
        fdesc = context.get_font_description()
        metrics = context.get_metrics(fdesc)
        width = pango.PIXELS(metrics.get_approximate_char_width() * self._width_in_chars)
        x, y = self.view.buffer_to_window_coords(gtk.TEXT_WINDOW_TEXT, width, width / 3)
        self.view.set_size_request(x, y)
    def set_width_in_chars(self, width_in_chars):
        self._width_in_chars = width_in_chars
        self._adjust_size_request()
    def set_font(self, fdesc):
        self.view.modify_font(fdesc)
        self._adjust_size_request()
    def set_contents(self, text, undoable=False):
        if not undoable:
            self.text_buffer.begin_not_undoable_action()
        result = self.text_buffer.set_text(text)
        if not undoable:
            self.text_buffer.end_not_undoable_action()
        return result
    def _initialize_contents(self):
        self.set_contents('')
    def get_contents(self):
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start_iter, end_iter)

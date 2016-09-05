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

import os
from contextlib import contextmanager

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk

from .. import enotify

from . import icons
from . import gutils

from ..config_data import APP_NAME

main_window = None

@contextmanager
def showing_busy():
    if main_window is None:
        yield
    else:
        main_window.show_busy()
        try:
            yield
        finally:
            main_window.unshow_busy()

def is_busy():
    return main_window is None or main_window.is_busy

def init(window):
    global main_window
    main_window = window

class BusyIndicator:
    def __init__(self, parent=None):
        self._bi_parent = parent
        self._count = 0
    def show_busy(self):
        if self._bi_parent:
            self._bi_parent.show_busy()
        self._count += 1
        if self._count == 1:
            window = self.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new(Gdk.CursorType.WATCH))
                gutils.yield_to_pending_events()
    def unshow_busy(self):
        if self._bi_parent:
            self._bi_parent.unshow_busy()
        self._count -= 1
        assert self._count >= 0
        if self._count == 0:
            window = self.get_window()
            if window is not None:
                window.set_cursor(None)
                gutils.yield_to_pending_events()
    @contextmanager
    def showing_busy(self):
        self.show_busy()
        try:
            yield
        finally:
            self.unshow_busy()
    @property
    def is_busy(self):
        return self._count > 0

class BusyIndicatorUser:
    def __init__(self, busy_indicator=None):
        self._busy_indicator = busy_indicator
    def _show_busy(self):
        if self._busy_indicator is not None:
            self._busy_indicator.show_busy()
        elif main_window is not None:
            main_window.show_busy()
    def _unshow_busy(self):
        if self._busy_indicator is not None:
            self._busy_indicator.unshow_busy()
        elif main_window is not None:
            main_window.unshow_busy()
    @contextmanager
    def showing_busy(self):
        self._show_busy()
        try:
            yield
        finally:
            self._unshow_busy()
    def set_busy_indicator(self, busy_indicator=None):
        self._busy_indicator = busy_indicator

class BusyDialog(Gtk.Dialog, BusyIndicator):
    __g_type_name__ = "BusyDialog"
    def __init__(self, title=None, parent=None, flags=0, buttons=None):
        if not parent:
            parent = main_window
        Gtk.Dialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons if buttons else ())
        if not parent:
            self.set_icon(icons.APP_ICON_PIXBUF)
        BusyIndicator.__init__(self)
    def report_any_problems(self, result):
        report_any_problems(result, self)
    def inform_user(self, msg):
        inform_user(msg, parent=self)
    def warn_user(self, msg):
        warn_user(msg, parent=self)
    def alert_user(self, msg):
        alert_user(msg, parent=self)

class ListenerDialog(BusyDialog, enotify.Listener):
    __g_type_name__ = "ListenerDialog"
    def __init__(self, title=None, parent=None, flags=0, buttons=None):
        flags &= ~Gtk.DialogFlags.MODAL
        BusyDialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons)
        enotify.Listener.__init__(self)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        self.add_notification_cb(enotify.E_CHANGE_WD, self._self_destruct_cb)
    def _self_destruct_cb(self, **kwargs):
        self.destroy()

class MessageDialog(BusyDialog):
    __g_type_name__ = "MessageDialog"
    icons = {
        Gtk.MessageType.INFO: Gtk.STOCK_DIALOG_INFO,
        Gtk.MessageType.WARNING: Gtk.STOCK_DIALOG_WARNING,
        Gtk.MessageType.QUESTION: Gtk.STOCK_DIALOG_QUESTION,
        Gtk.MessageType.ERROR: Gtk.STOCK_DIALOG_ERROR,
    }
    labels = {
        Gtk.MessageType.INFO: _("FYI"),
        Gtk.MessageType.WARNING: _("Warning"),
        Gtk.MessageType.QUESTION: _("Question"),
        Gtk.MessageType.ERROR: _("Error"),
    }
    @staticmethod
    def copy_cb(tview):
        tview.get_buffer().copy_clipboard(Gtk.clipboard_get())
    def __init__(self, parent=None, flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT, type=Gtk.MessageType.INFO, buttons=None, message=None, explanation=None):
        if not parent:
            parent = main_window
        BusyDialog.__init__(self, title=APP_NAME + ": {0}".format(self.labels[type]), parent=parent, flags=flags, buttons=buttons)
        self.set_property("skip-taskbar-hint", True)
        hbox = Gtk.HBox()
        icon = Gtk.Image()
        icon.set_from_stock(self.icons[type], Gtk.IconSize.DIALOG)
        hbox.pack_start(icon, expand=False, fill=False, padding=0)
        label = Gtk.Label()
        label.set_markup("<big><b>" + self.labels[type] + "</b></big>")
        hbox.pack_start(label, expand=False, fill=False, padding=0)
        self.get_content_area().pack_start(hbox, expand=False, fill=False, padding=0)
        m_label = Gtk.Label()
        m_label.set_markup("<b>" + message + "</b>")
        self.get_content_area().pack_start(m_label, expand=True, fill=True, padding=0)
        if explanation:
            e_label = Gtk.Label(explanation)
            e_label.set_justify(Gtk.Justification.LEFT)
            self.get_content_area().pack_start(e_label, expand=True, fill=True, padding=0)
        self.show_all()
        self.set_resizable(True)

class FileChooserDialog(Gtk.FileChooserDialog):
    __g_type_name__ = "FileChooserDialog"
    def __init__(self, title=None, parent=None, action=Gtk.FileChooserAction.OPEN, buttons=None, backend=None):
        if not parent:
            parent = main_window
        Gtk.FileChooserDialog.__init__(self, title=title, parent=parent, action=action, buttons=buttons, backend=backend)

class SelectFromListDialog(BusyDialog):
    __g_type_name__ = "SelectFromListDialog"
    def __init__(self, olist=list(), prompt=_('Select from list:'), parent=None):
        BusyDialog.__init__(self, "{0}: {1}".format(config_data.APP_NAME, os.getcwd()), parent,
                        Gtk.DialogFlags.DESTROY_WITH_PARENT,
                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK))
        if parent is None:
            self.set_position(Gtk.WindowPosition.MOUSE)
        else:
            self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.cbox = Gtk.ComboBoxText()
        self.cbox.append_text(prompt)
        for i in olist:
            self.cbox.append_text(i)
        self.cbox.set_active(0)
        self.vbox.add(self.cbox)
        self.cbox.show()
    def make_selection(self):
        res = self.run()
        index = self.cbox.get_active()
        seln = self.cbox.get_model()[index][0] if index > 0 else None
        self.destroy()
        return seln

class QuestionDialog(BusyDialog):
    __g_type_name__ = "QuestionDialog"
    def __init__(self, title=None, parent=None, flags=0, buttons=None, question="", explanation=""):
        if title is None:
            title = APP_NAME
        BusyDialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons)
        self.set_property("skip-taskbar-hint", True)
        hbox = Gtk.HBox()
        self.vbox.add(hbox)
        hbox.show()
        self.image = Gtk.Image()
        self.image.set_from_stock(Gtk.STOCK_DIALOG_QUESTION, Gtk.IconSize.DIALOG)
        hbox.pack_start(self.image, expand=False, fill=True, padding=0)
        self.image.show()
        q_label = Gtk.Label()
        q_label.set_markup("<big><b>" + question + "</b></big>")
        if explanation:
            vbox = Gtk.VBox()
            e_label = Gtk.Label(explanation)
            e_label.set_justify(Gtk.Justification.LEFT)
            vbox.pack_start(q_label, expand=True, fill=True, padding=0)
            vbox.pack_start(e_label, expand=True, fill=True, padding=0)
            hbox.add(vbox)
        else:
            hbox.add(q_label)
        self.show_all()

def ask_question(question, explanation="", parent=None,
                 buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                          Gtk.STOCK_OK, Gtk.ResponseType.OK)):
    dialog = QuestionDialog(parent=parent,
                            flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            buttons=buttons, question=question, explanation=explanation)
    response = dialog.run()
    dialog.destroy()
    return response

def ask_ok_cancel(question, explanation="", parent=None):
    return ask_question(question, explanation, parent) == Gtk.ResponseType.OK

def ask_yes_no(question, explanation="", parent=None):
    buttons = (Gtk.STOCK_NO, Gtk.ResponseType.NO, Gtk.STOCK_YES, Gtk.ResponseType.YES)
    return ask_question(question, explanation, parent, buttons) == Gtk.ResponseType.YES

def inform_user(msg, expln=None, parent=None, problem_type=Gtk.MessageType.INFO):
    dialog = MessageDialog(parent=parent,
                           flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT,
                           type=problem_type, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE),
                           message=msg, explanation=expln)
    dialog.run()
    dialog.destroy()

def warn_user(msg, expln=None, parent=None):
    inform_user(msg, expln, parent=parent, problem_type=Gtk.MessageType.WARNING)

def alert_user(msg, expln=None, parent=None):
    inform_user(msg, expln, parent=parent, problem_type=Gtk.MessageType.ERROR)

def confirm_list_action(alist, question, parent=None):
    return ask_ok_cancel('\n'.join(alist + ['\n', question]), parent=parent)

def report_any_problems(result, parent=None):
    if result.is_ok:
        return
    elif result.is_warning:
        problem_type = Gtk.MessageType.WARNING
    else:
        problem_type = Gtk.MessageType.ERROR
    inform_user("\n".join(result[1:]), parent=parent, problem_type=problem_type)

def report_failure(failure, parent=None):
    inform_user(failure.result, parent, Gtk.MessageType.ERROR)

def report_exception_as_error(edata, parent=None):
    alert_user(str(edata), parent=parent)

class UndecoratedMessage(Gtk.Dialog):
    __g_type_name__ = "UndecoratedMessage"
    def __init__(self, message, parent=None):
        Gtk.Dialog.__init__(self, "", main_window if not parent else parent, 0)
        self.set_decorated(False)
        label = Gtk.Label()
        label.set_markup("<big><b>" + message + "</b></big>")
        self.get_content_area().add(label)
        self.show_all()

@contextmanager
def comforting_message(message, spinner=False, parent=None):
    # TODO: Fix this mess and get going need to know how to force mapping of window
    dialog = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    dialog.set_decorated(False)
    dialog.set_destroy_with_parent(True)
    label = Gtk.Label()
    label.set_can_focus(True)
    label.set_markup("<big><b>" + message + "</b></big>")
    dialog.add(label)
    dialog.show_all()
    dialog.show()
    dialog.set_keep_above(True)
    dialog.present()
    try:
        os.sched_yield()
    except:
        import time
        time.sleep(1)
    try:
        yield dialog
    finally:
        dialog.destroy()
        pass

class CancelOKDialog(BusyDialog):
    __g_type_name__ = "CancelOKDialog"
    def __init__(self, title=None, parent=None):
        if not parent:
            parent = main_window
        flags = Gtk.DialogFlags.DESTROY_WITH_PARENT
        buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        BusyDialog.__init__(self, title, parent, flags, buttons)

class ReadTextWidget(Gtk.HBox):
    __g_type_name__ = "ReadTextWidget"
    def __init__(self, prompt=None, suggestion="", width_chars=32):
        Gtk.HBox.__init__(self)
        if prompt:
            p_label = Gtk.Label()
            p_label.set_markup(prompt)
            self.pack_start(p_label, expand=False, fill=True, padding=0)
        self.entry = Gtk.Entry()
        if suggestion:
            self.entry.set_text(suggestion)
            self.entry.set_width_chars(max(width_chars, len(suggestion)))
        else:
            self.entry.set_width_chars(width_chars)
        self.pack_start(self.entry, expand=True, fill=True, padding=0)
        self.show_all()
    def _do_pulse(self):
        self.entry.progress_pulse()
        return True
    def start_busy_pulse(self):
        self.entry.set_progress_pulse_step(0.2)
        self._timeout_id = GObject.timeout_add(100, self._do_pulse, priority=GObject.PRIORITY_HIGH)
    def stop_busy_pulse(self):
        GObject.source_remove(self._timeout_id)
        self._timeout_id = None
        self.entry.set_progress_pulse_step(0)

class FileChooserDialog(Gtk.FileChooserDialog):
    __g_type_name__ = "FileChooserDialog"
    def __init__(self, title=None, parent=None, action=Gtk.FileChooserAction.OPEN, buttons=None, backend=None):
        if not parent:
            parent = main_window
        Gtk.FileChooserDialog.__init__(self, title, parent, action, buttons, backend)

class Response:
    SKIP = 1
    SKIP_ALL = 2
    FORCE = 3
    REFRESH = 4
    RECOVER = 5
    RENAME = 6
    DISCARD = 7
    ABSORB = 8
    EDIT = 9
    MERGE = 10
    OVERWRITE = 11

def _form_question(result):
    if not result[2]:
        return result[1]
    elif not result[1]:
        return result[2]
    else:
        return '\n'.join(result[1:])

def ask_discard_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, _('_Discard'), Response.DISCARD)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_force_refresh_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_refresh:
        buttons += (_('_Refresh and Retry'), Response.REFRESH)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_force_refresh_absorb_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_refresh:
        buttons += (_('_Refresh and Retry'), Response.REFRESH)
    if result.suggests_absorb:
        buttons += (_('_Absorb Changes'), Response.ABSORB)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_force_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, _('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_force_skip_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, _('_Skip'), Response.SKIP, _('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_merge_discard_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_merge:
        buttons += (_('_Merge'), Response.MERGE)
    if result.suggests_discard:
        buttons += (_('_Discard Changes'), Response.DISCARD)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_recover_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, _('_Recover'), Response.RECOVER)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_edit_force_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_edit:
        buttons += (_('_Edit'), Response.EDIT)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_rename_force_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_rename_force_or_skip(result, clarification=None, parent=None):
    buttons = ()
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    buttons += (_('_Skip'), Response.SKIP, _('Skip _All'), Response.SKIP_ALL)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_rename_overwrite_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_overwrite:
        buttons += (_('_Overwrite'), Response.OVERWRITE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def ask_rename_overwrite_force_or_cancel(result, clarification=None, parent=None):
    buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_overwrite:
        buttons += (_('_Overwrite'), Response.OVERWRITE)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result)
    return ask_question(question, clarification, parent, buttons)

def select_file(prompt, suggestion=None, existing=True, absolute=False, parent=None):
    if existing:
        mode = Gtk.FileChooserAction.OPEN
        if suggestion and not os.path.exists(suggestion):
            suggestion = None
    else:
        mode = Gtk.FileChooserAction.SAVE
    dialog = FileChooserDialog(prompt, parent, mode,
                               (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                Gtk.STOCK_OK, Gtk.ResponseType.OK))
    dialog.set_default_response(Gtk.ResponseType.OK)
    if suggestion:
        if os.path.isdir(suggestion):
            dialog.set_current_folder(suggestion)
        else:
            dirname, basename = os.path.split(suggestion)
            if dirname:
                dialog.set_current_folder(dirname)
            else:
                dialog.set_current_folder(os.getcwd())
            if basename:
                dialog.set_current_name(basename)
    else:
        dialog.set_current_folder(os.getcwd())
    response = dialog.run()
    if dialog.run() == Gtk.ResponseType.OK:
        if absolute:
            new_file_path = dialog.get_filename()
        else:
            new_file_path = os.path.relpath(dialog.get_filename())
    else:
        new_file_path = None
    dialog.destroy()
    return new_file_path

def select_directory(prompt, suggestion=None, existing=True, absolute=False, parent=None):
    if existing:
        if suggestion and not os.path.exists(suggestion):
            suggestion = None
    dialog = FileChooserDialog(prompt, parent, Gtk.FileChooserAction.SELECT_FOLDER,
                               (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                Gtk.STOCK_OK, Gtk.ResponseType.OK))
    dialog.set_default_response(Gtk.ResponseType.OK)
    if suggestion:
        if os.path.isdir(suggestion):
            dialog.set_current_folder(suggestion)
        else:
            dirname = os.path.dirname(suggestion)
            if dirname:
                dialog.set_current_folder(dirname)
            else:
                dialog.set_current_folder(os.getcwd())
    else:
        dialog.set_current_folder(os.getcwd())
    response = dialog.run()
    if response == Gtk.ResponseType.OK:
        if absolute:
            new_dir_path = dialog.get_filename()
        else:
            new_dir_path = os.path.relpath(dialog.get_filename())
    else:
        new_dir_path = None
    dialog.destroy()
    return new_dir_path

def ask_uri_name(prompt, suggestion=None, parent=None):
    if suggestion and not os.path.exists(suggestion):
        suggestion = None
    dialog = FileChooserDialog(prompt, parent, Gtk.FileChooserAction.SELECT_FOLDER,
                               (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                Gtk.STOCK_OK, Gtk.ResponseType.OK))
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.set_local_only(False)
    if suggestion:
        if os.path.isdir(suggestion):
            dialog.set_current_folder(suggestion)
        else:
            dirname = os.path.dirname(suggestion)
            if dirname:
                dialog.set_current_folder(dirname)
    else:
        dialog.set_current_folder(os.getcwd())
    response = dialog.run()
    if response == Gtk.ResponseType.OK:
        uri = os.path.relpath(dialog.get_uri())
    else:
        uri = None
    dialog.destroy()
    return uri

# TODO: put auto completion into the text entry component
class _EnterPathWidget(Gtk.HBox):
    __g_type_name__ = "_EnterPathWidget"
    SELECT_FUNC = None
    SELECT_TITLE = None
    def __init__(self, prompt=None, suggestion=None, existing=True, width_chars=32, parent=None):
        Gtk.HBox.__init__(self)
        self._parent = parent
        self._path = ReadTextWidget(prompt=prompt, suggestion=suggestion, width_chars=width_chars)
        self._path.entry.set_activates_default(True)
        self._existing = existing
        self.b_button = Gtk.Button.new_with_label(_("Browse"))
        self.b_button.connect("clicked", self._browse_cb)
        self.pack_start(self._path, expand=True, fill=True, padding=0)
        self.pack_end(self.b_button, expand=False, fill=True, padding=0)
        self.show_all()
    @property
    def path(self):
        return os.path.expanduser(self._path.entry.get_text())
    def set_sensitive(self, sensitive):
        self._path.entry.set_editable(sensitive)
        self.b_button.set_sensitive(sensitive)
    def _browse_cb(self, button=None):
        suggestion = self._path.entry.get_text()
        path = self.SELECT_FUNC(self.SELECT_TITLE, suggestion=suggestion, existing=self._existing, parent=self._parent, absolute=False)
        if path:
            self._path.entry.set_text(path)
    def start_busy_pulse(self):
        self._path.start_busy_pulse()
    def stop_busy_pulse(self):
        self._path.stop_busy_pulse()

class _EnterPathDialog(CancelOKDialog):
    __g_type_name__ = "_EnterPathDialog"
    WIDGET = None
    def __init__(self, title=None, prompt=None, suggestion="", existing=True, parent=None):
        CancelOKDialog.__init__(self, title, parent)
        self.entry = self.WIDGET(prompt, suggestion, existing, parent=self)
        self.get_content_area().add(self.entry)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.show_all()
    @property
    def path(self):
        return self.entry.path
    def start_busy_pulse(self):
        ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        ok_button.set_label("Wait...")
        self.entry.start_busy_pulse()
    def stop_busy_pulse(self):
        self.entry.stop_busy_pulse()

class EnterDirPathWidget(_EnterPathWidget):
    __g_type_name__ = "EnterDirPathWidget"
    SELECT_FUNC = lambda s, *args, **kwargs: select_directory(*args, **kwargs)
    SELECT_TITLE = _("Browse for Directory")

class EnterDirPathDialog(_EnterPathDialog):
    __g_type_name__ = "EnterDirPathDialog"
    WIDGET = EnterDirPathWidget

class EnterFilePathWidget(_EnterPathWidget):
    __g_type_name__ = "EnterFilePathWidget"
    SELECT_FUNC = lambda s, *args, **kwargs: select_file(*args, **kwargs)
    SELECT_TITLE = _("Browse for File")

class EnterFilePathDialog(_EnterPathDialog):
    __g_type_name__ = "EnterFilePathDialog"
    WIDGET = EnterFilePathWidget

def ask_dir_path(prompt, suggestion=None, existing=True, parent=None):
    dialog = EnterDirPathDialog(title=_("Enter Directory Path"), prompt=prompt, suggestion=suggestion, existing=existing, parent=parent)
    dir_path = dialog.path if dialog.run() == Gtk.ResponseType.OK else None
    dialog.destroy()
    return dir_path

def ask_file_path(prompt, suggestion=None, existing=True, parent=None):
    dialog = EnterFilePathDialog(title=_("Enter File Path"), prompt=prompt, suggestion=suggestion, existing=existing, parent=parent)
    file_path = dialog.path if dialog.run() == Gtk.ResponseType.OK else None
    dialog.destroy()
    return file_path

class ReadTextDialog(CancelOKDialog):
    __g_type_name__ = "ReadTextDialog"
    def __init__(self, title=None, prompt=None, suggestion="", parent=None):
        CancelOKDialog.__init__(self, title, parent)
        self._rtw = ReadTextWidget(prompt, suggestion, width_chars=32)
        self.vbox.pack_start(self._rtw, expand=False, fill=True, padding=0)
        self.show_all()
    @property
    def entry(self):
        return self._rtw.entry

class ReadTextAndToggleDialog(ReadTextDialog):
    __g_type_name__ = "ReadTextAndToggleDialog"
    def __init__(self, title=None, prompt=None, suggestion="", toggle_prompt=None, toggle_state=False, parent=None):
        ReadTextDialog.__init__(self, title=title, prompt=prompt, suggestion=suggestion, parent=parent)
        self.toggle = Gtk.CheckButton(label=toggle_prompt)
        self.toggle.set_active(toggle_state)
        self._rtw.pack_start(self.toggle, expand=True, fill=True, padding=0)
        self.show_all()

def get_modified_string(title, prompt, string):
    dialog = ReadTextDialog(title, prompt, string)
    string = dialog.entry.get_text() if dialog.run() == Gtk.ResponseType.OK else ""
    dialog.destroy()
    return string

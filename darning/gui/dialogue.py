### Copyright (C) 2005-2015 Peter Williams <pwil3058@gmail.com>
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

import gtk
import pango

from .. import config_data

from . import icons
from . import ws_event
from . import gutils

main_window = None

def show_busy():
    if main_window is not None:
        main_window.show_busy()

def unshow_busy():
    if main_window is not None:
        main_window.unshow_busy()

def is_busy():
    return main_window is None or main_window.is_busy

def init(window):
    global main_window
    main_window = window

class BusyIndicator:
    def __init__(self, parent=None):
        self.parent_indicator = parent
        self._count = 0
    def show_busy(self):
        if self.parent:
            self.parent.show_busy()
        self._count += 1
        if self._count == 1 and self.window:
            self.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))
            while gtk.events_pending():
                gtk.main_iteration()
    def unshow_busy(self):
        if self.parent:
            self.parent.unshow_busy()
        self._count -= 1
        assert self._count >= 0
        if self._count == 0 and self.window:
            self.window.set_cursor(None)
    @property
    def is_busy(self):
        return self._count > 0

class BusyIndicatorUser:
    def __init__(self, busy_indicator=None):
        self._busy_indicator = busy_indicator
    def show_busy(self):
        if self._busy_indicator is not None:
            self._busy_indicator.show_busy()
        else:
            show_busy()
    def unshow_busy(self):
        if self._busy_indicator is not None:
            self._busy_indicator.unshow_busy()
        else:
            unshow_busy()
    def set_busy_indicator(self, busy_indicator=None):
        self._busy_indicator = busy_indicator

class Dialog(gtk.Dialog, BusyIndicator):
    def __init__(self, title=None, parent=None, flags=0, buttons=None):
        if not parent:
            parent = main_window
        gtk.Dialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons)
        if not parent:
            self.set_icon_from_file(icons.APP_ICON_FILE)
        BusyIndicator.__init__(self)
    def report_any_problems(self, result):
        report_any_problems(result, self)
    def inform_user(self, msg):
        inform_user(msg, parent=self)
    def warn_user(self, msg):
        warn_user(msg, parent=self)
    def alert_user(self, msg):
        alert_user(msg, parent=self)

class AmodalDialog(Dialog, ws_event.Listener):
    def __init__(self, title=None, parent=None, flags=0, buttons=None):
        flags &= ~gtk.DIALOG_MODAL
        Dialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons)
        ws_event.Listener.__init__(self)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_NORMAL)
        from . import ifce
        self.add_notification_cb(ifce.E_CHANGE_WD, self._change_wd_cb)
    def _change_wd_cb(self, **kwargs):
        self.destroy()

class MessageDialog(Dialog):
    icons = {
        gtk.MESSAGE_INFO: gtk.STOCK_DIALOG_INFO,
        gtk.MESSAGE_WARNING: gtk.STOCK_DIALOG_WARNING,
        gtk.MESSAGE_QUESTION: gtk.STOCK_DIALOG_QUESTION,
        gtk.MESSAGE_ERROR: gtk.STOCK_DIALOG_ERROR,
    }
    labels = {
        gtk.MESSAGE_INFO: _('FYI'),
        gtk.MESSAGE_WARNING: _('Warning'),
        gtk.MESSAGE_QUESTION: _('Question'),
        gtk.MESSAGE_ERROR: _('Error'),
    }
    @staticmethod
    def copy_cb(tview):
        tview.get_buffer().copy_clipboard(gtk.clipboard_get())
    def __init__(self, parent=None, flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT, type=gtk.MESSAGE_INFO, buttons=None, message_format=None):
        if not parent:
            parent = main_window
        Dialog.__init__(self, title='gdarn: {0}'.format(self.labels[type]), parent=parent, flags=flags, buttons=buttons)
        hbox = gtk.HBox()
        icon = gtk.Image()
        icon.set_from_stock(self.icons[type], gtk.ICON_SIZE_DIALOG)
        hbox.pack_start(icon, expand=False, fill=False)
        label = gtk.Label(self.labels[type])
        label.modify_font(pango.FontDescription('bold 35'))
        hbox.pack_start(label, expand=False, fill=False)
        self.get_content_area().pack_start(hbox, expand=False, fill=False)
        sbw = gtk.ScrolledWindow()
        sbw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        tview = gtk.TextView()
        tview.set_size_request(480,120)
        tview.set_editable(False)
        tview.get_buffer().set_text(message_format.strip())
        tview.connect('copy-clipboard', MessageDialog.copy_cb)
        sbw.add(tview)
        self.get_content_area().pack_end(sbw, expand=True, fill=True)
        self.show_all()
        self.set_resizable(True)

class FileChooserDialog(gtk.FileChooserDialog):
    def __init__(self, title=None, parent=None, action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=None, backend=None):
        if not parent:
            parent = main_window
        gtk.FileChooserDialog.__init__(self, title=title, parent=parent, action=action, buttons=buttons, backend=backend)

class SelectFromListDialog(Dialog):
    def __init__(self, olist=list(), prompt=_('Select from list:'), parent=None):
        Dialog.__init__(self, "{0}: {1}".format(config_data.APP_NAME, os.getcwd()), parent,
                        gtk.DIALOG_DESTROY_WITH_PARENT,
                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                        gtk.STOCK_OK, gtk.RESPONSE_OK))
        if parent is None:
            self.set_position(gtk.WIN_POS_MOUSE)
        else:
            self.set_position(gtk.WIN_POS_CENTER_ON_PARENT)
        self.cbox = gtk.combo_box_new_text()
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

class QuestionDialog(Dialog):
    def __init__(self, title=None, parent=None, flags=0, buttons=None, question=""):
        Dialog.__init__(self, title=title, parent=parent, flags=flags, buttons=buttons)
        hbox = gtk.HBox()
        self.vbox.add(hbox)
        hbox.show()
        self.image = gtk.Image()
        self.image.set_from_stock(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
        hbox.pack_start(self.image, expand=False)
        self.image.show()
        self.tview = gtk.TextView()
        self.tview.set_cursor_visible(False)
        self.tview.set_editable(False)
        self.tview.set_size_request(320, 80)
        self.tview.show()
        self.tview.get_buffer().set_text(question)
        hbox.add(gutils.wrap_in_scrolled_window(self.tview))
    def set_question(self, question):
        self.tview.get_buffer().set_text(question)

def ask_question(question, parent=None,
                 buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                          gtk.STOCK_OK, gtk.RESPONSE_OK)):
    dialog = QuestionDialog(parent=parent,
                            flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
                            buttons=buttons, question=question)
    response = dialog.run()
    dialog.destroy()
    return response

def ask_ok_cancel(question, parent=None):
    return ask_question(question, parent) == gtk.RESPONSE_OK

def ask_yes_no(question, parent=None):
    buttons = (gtk.STOCK_NO, gtk.RESPONSE_NO, gtk.STOCK_YES, gtk.RESPONSE_YES)
    return ask_question(question, parent, buttons) == gtk.RESPONSE_YES

def confirm_list_action(alist, question, parent=None):
    return ask_ok_cancel('\n'.join(alist + ['\n', question]), parent)

class Response(object):
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

def _form_question(result, clarification):
    if clarification:
        return '\n'.join(list(result[1:]) + [clarification])
    else:
        return '\n'.join(result[1:])

def ask_discard_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, _('_Discard'), Response.DISCARD)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_force_refresh_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_refresh:
        buttons += (_('_Refresh and Retry'), Response.REFRESH)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_force_refresh_absorb_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_refresh:
        buttons += (_('_Refresh and Retry'), Response.REFRESH)
    if result.suggests_absorb:
        buttons += (_('_Absorb Changes'), Response.ABSORB)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_force_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, _('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_force_skip_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, _('_Skip'), Response.SKIP, _('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_merge_discard_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_merge:
        buttons += (_('_Merge'), Response.MERGE)
    if result.suggests_discard:
        buttons += (_('_Discard Changes'), Response.DISCARD)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_recover_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, _('_Recover'), Response.RECOVER)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_edit_force_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_edit:
        buttons += (_('_Edit'), Response.EDIT)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_rename_force_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_rename_force_or_skip(result, clarification=None, parent=None):
    buttons = ()
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_force:
        buttons += (_('_Force'), Response.FORCE)
    buttons += (_('_Skip'), Response.SKIP, _('Skip _All'), Response.SKIP_ALL)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

def ask_rename_overwrite_or_cancel(result, clarification=None, parent=None):
    buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    if result.suggests_rename:
        buttons += (_('_Rename'), Response.RENAME)
    if result.suggests_overwrite:
        buttons += (_('_Overwrite'), Response.OVERWRITE)
    question = _form_question(result, clarification)
    return ask_question(question, parent, buttons)

# TODO: rename ask_file_name() and ask_dir_name()
def ask_file_name(prompt, suggestion=None, existing=True, parent=None):
    if existing:
        mode = gtk.FILE_CHOOSER_ACTION_OPEN
        if suggestion and not os.path.exists(suggestion):
            suggestion = None
    else:
        mode = gtk.FILE_CHOOSER_ACTION_SAVE
    dialog = FileChooserDialog(prompt, parent, mode,
                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                gtk.STOCK_OK, gtk.RESPONSE_OK))
    dialog.set_default_response(gtk.RESPONSE_OK)
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
    if response == gtk.RESPONSE_OK:
        new_file_name = os.path.relpath(dialog.get_filename())
    else:
        new_file_name = None
    dialog.destroy()
    return new_file_name

def ask_dir_name(prompt, suggestion=None, existing=True, parent=None):
    mode = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
    if existing and suggestion and not os.path.exists(suggestion):
        suggestion = None
    dialog = FileChooserDialog(prompt, parent, mode,
                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                gtk.STOCK_OK, gtk.RESPONSE_OK))
    dialog.set_default_response(gtk.RESPONSE_OK)
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
    if response == gtk.RESPONSE_OK:
        new_dir_name = os.path.relpath(dialog.get_filename())
    else:
        new_dir_name = None
    dialog.destroy()
    return new_dir_name

def ask_uri_name(prompt, suggestion=None, parent=None):
    if suggestion and not os.path.exists(suggestion):
        suggestion = None
    dialog = FileChooserDialog(prompt, parent, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                gtk.STOCK_OK, gtk.RESPONSE_OK))
    dialog.set_default_response(gtk.RESPONSE_OK)
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
    if response == gtk.RESPONSE_OK:
        uri = os.path.relpath(dialog.get_uri())
    else:
        uri = None
    dialog.destroy()
    return uri

def inform_user(msg, parent=None, problem_type=gtk.MESSAGE_INFO):
    dialog = MessageDialog(parent=parent,
                           flags=gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
                           type=problem_type, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE),
                           message_format=msg)
    dialog.run()
    dialog.destroy()

def warn_user(msg, parent=None):
    inform_user(msg, parent=parent, problem_type=gtk.MESSAGE_WARNING)

def alert_user(msg, parent=None):
    inform_user(msg, parent=parent, problem_type=gtk.MESSAGE_ERROR)

def report_any_problems(result, parent=None):
    if result.is_ok:
        return
    elif result.is_warning:
        problem_type = gtk.MESSAGE_WARNING
    else:
        problem_type = gtk.MESSAGE_ERROR
    inform_user('\n'.join(result[1:]), parent, problem_type)

def report_failure(failure, parent=None):
    inform_user(failure.result, parent, gtk.MESSAGE_ERROR)

def report_exception_as_error(edata, parent=None):
    problem_type = gtk.MESSAGE_ERROR
    inform_user(str(edata), parent, problem_type)

class CancelOKDialog(Dialog):
    def __init__(self, title=None, parent=None):
        flags = gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK)
        Dialog.__init__(self, title, parent, flags, buttons)

class ReadTextDialog(CancelOKDialog):
    def __init__(self, title=None, prompt=None, suggestion="", parent=None):
        CancelOKDialog.__init__(self, title, parent)
        self.hbox = gtk.HBox()
        self.vbox.pack_start(self.hbox, expand=False)
        self.hbox.show()
        if prompt:
            self.hbox.pack_start(gtk.Label(prompt), fill=False, expand=False)
        self.entry = gtk.Entry()
        self.entry.set_width_chars(32)
        self.entry.set_text(suggestion)
        self.hbox.pack_start(self.entry)
        self.show_all()

class ReadTextAndToggleDialog(ReadTextDialog):
    def __init__(self, title=None, prompt=None, suggestion="", toggle_prompt=None, toggle_state=False, parent=None):
        ReadTextDialog.__init__(self, title=title, prompt=prompt, suggestion=suggestion, parent=parent)
        self.toggle = gtk.CheckButton(label=toggle_prompt)
        self.toggle.set_active(toggle_state)
        self.hbox.pack_start(self.toggle)
        self.show_all()

def get_modified_string(title, prompt, string):
    dialog = ReadTextDialog(title, prompt, string)
    string = dialog.entry.get_text() if dialog.run() == gtk.RESPONSE_OK else ""
    dialog.destroy()
    return string

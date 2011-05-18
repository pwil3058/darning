# -*- python -*-

### Copyright (C) 2005 Peter Williams <peter_ono@users.sourceforge.net>

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

"""
Provide mechanism for notifying components of events that require them
to update their displayed/cached data
"""

import gobject

_NFLAGS = 16
FILE_ADD, \
FILE_DEL, \
FILE_MOD, \
FILE_HGIGNORE, \
REPO_MOD, \
REPO_HGRC, \
USER_HGRC, \
CHANGE_WD, \
CHECKOUT, \
PATCH_PUSH, \
PATCH_POP, \
PATCH_REFRESH, \
PATCH_CREATE, \
PATCH_DELETE, \
PATCH_MODIFY, \
PMIC_CHANGE = [2 ** flag_num for flag_num in range(_NFLAGS)]

ALL_EVENTS = 2 ** _NFLAGS - 1
ALL_BUT_CHANGE_WD = ALL_EVENTS &  ~CHANGE_WD

FILE_CHANGES = FILE_ADD | FILE_DEL | FILE_MOD | FILE_HGIGNORE
PATCH_CHANGES = PATCH_PUSH | PATCH_POP | PATCH_CREATE | PATCH_DELETE | PATCH_MODIFY

_NOTIFICATION_CBS = []


def add_notification_cb(events, callback):
    """
    Register a callback for notification of the specified events.

    Arguments:
    events   -- the set of events for which the callback should be callded.
    callback -- the procedure to be called.

    Return a token that identifies the callback to facilitate deletion.
    """
    cb_token = (events, callback)
    _NOTIFICATION_CBS.append(cb_token)
    return cb_token


def del_notification_cb(cb_token):
    """
    Cancel the registration of a notification callback.

    Argument:
    cb_token -- the token that specifies the callback to be cancelled.
    """
    index = _NOTIFICATION_CBS.index(cb_token)
    if index >= 0:
        del _NOTIFICATION_CBS[index]


def notify_events(events, data=None):
    """
    Notify interested parties of events that have occured.

    Argument:
    events -- a set of events that have just occured.

    Keyword Argument:
    data -- extra data the notifier thinks may be of use to the callback.
    """
    invalid_cbs = []
    for registered_events, callback in _NOTIFICATION_CBS:
        if registered_events & events:
            try:
                if data:
                    callback(data)
                else:
                    callback()
            except Exception:
                invalid_cbs.append((registered_events, callback))
    for cb_token in invalid_cbs:
        del_notification_cb(cb_token)


class Listener(gobject.GObject):
    """A base class for transient GTK object classes that wish to register
    event callbacks so that their callbacks are deleted when they are
    destroyed.
    """
    def __init__(self):
        gobject.GObject.__init__(self)
        self._listener_cbs = []
        self.connect('destroy', self._listener_destroy_cb)

    def add_notification_cb(self, events, callback):
        """
        Register a callback for notification of the specified events.
        Record a token to facilitate deletion at a later time.

        Arguments:
        events   -- the set of events for which the callback should be callded.
        callback -- the procedure to be called.

        Return a token that identifies the callback to facilitate deletion.
        """
        self._listener_cbs.append(add_notification_cb(events, callback))

    def _listener_destroy_cb(self, widget):
        """Remove all of my callbacks from the notification database"""
        for cb_token in self._listener_cbs:
            del_notification_cb(cb_token)


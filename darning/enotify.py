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

"""
Provide mechanism for notifying components of events that require them
to update their displayed/cached data
"""

from . import utils

_flag_generator = utils.create_flag_generator()

def new_event_flags_and_mask(count):
    flags = [next(_flag_generator) for _i in range(count)]
    return tuple(flags + [sum(flags)])

def new_event_flag():
    return next(_flag_generator)

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
    # this may have already been done as there are two invocation
    # paths - so we need to check
    try:
        index = _NOTIFICATION_CBS.index(cb_token)
        del _NOTIFICATION_CBS[index]
    except ValueError:
        pass

def notify_events(events, **kwargs):
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
                callback(**kwargs)
            except Exception as edata:
                # TODO: try to be more explicit in naming exception type to catch here
                # this is done to catch the race between a caller has going away and deleting its notifications
                if True: # NB: for debug assistance e.g . locating exceptions not due to caller going away
                    print("WS NOTIFY:\t edata: {}\n\t\t callback: {}\n\t\t kwargs: {}".format(edata, callback, kwargs))
                    raise edata
                invalid_cbs.append((registered_events, callback))
    for cb_token in invalid_cbs:
        del_notification_cb(cb_token)


class Listener:
    """A mixin for transient GTK object classes that wish to register
    event callbacks so that their callbacks are deleted when they are
    destroyed.
    """
    def __init__(self):
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
        # this callback seems to get called twice, so ...
        self._listener_cbs = []

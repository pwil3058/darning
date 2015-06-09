### Copyright (C) 2015 Peter Williams <pwil3058@gmail.com>
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

import gtk
import gobject

from . import gutils
from . import actions
from . import dialogue
from . import ws_event

def _check_interfaces(args):
    # NB: need extra level of function to avoid import loop/gridlock
    from . import ifce
    return ifce.check_interfaces(args)

_REGISTERED_CBS = []

def register_cb(callback):
    _REGISTERED_CBS.append(callback)

def deregister_cb(callback):
    # this may have already been done as there are two invocation
    # paths - so we need to check
    try:
        index = _REGISTERED_CBS.index(callback)
        del _REGISTERED_CBS[index]
    except ValueError:
        pass

def _auto_update_cb():
    invalid_cbs = []
    event_args = {}
    # make sure that the interfaces are up to date so that checks are valid
    event_flags = _check_interfaces(event_args)
    for callback in _REGISTERED_CBS:
        try:
            # pass event_flags in to give the client a chance to skip
            # any checks if existing flags would cause them to update anyway
            event_flags |= callback(event_flags, event_args)
        except Exception as edata:
            # TODO: try to be more explicit in naming exception type to catch here
            # this is done to catch the race between a caller has going away and deleting its registers
            if True: # NB: for debug assistance e.g . locating exceptions not due to caller going away
                print "AUTO UPDATE:", edata, callback, event_flags, event_args
                raise edata
            invalid_cbs.append(callback)
    if event_flags:
        ws_event.notify_events(event_flags, **event_args)
    for cb in invalid_cbs:
        deregister_cb(cb)

trigger_auto_update = _auto_update_cb

AUTO_UPDATE = gutils.TimeOutController(
    toggle_data=gutils.TimeOutController.ToggleData(
        name='config_auto_update',
        label=_('Auto Update'),
        tooltip=_('Enable/disable automatic updating of displayed data'),
        stock_id=gtk.STOCK_REFRESH
    ),
    function=_auto_update_cb, is_on=True, interval=10000
)

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_action(AUTO_UPDATE.toggle_action)

class AutoUpdater(gobject.GObject):
    """A base class for transient GTK object classes that wish to register
    auto update callbacks so that their callbacks are deleted when they are
    destroyed.
    """
    def __init__(self):
        gobject.GObject.__init__(self)
        self._auto_updater_cbs = []
        self.connect('destroy', self._auto_updater_destroy_cb)

    def register_auto_update_cb(self, callback):
        """
        Register a callback for register of the specified events.
        Record a token to facilitate deletion at a later time.

        Arguments:
        events   -- the set of events for which the callback should be callded.
        callback -- the procedure to be called.

        Return a token that identifies the callback to facilitate deletion.
        """
        self._auto_updater_cbs.append(register_cb(callback))

    def _auto_updater_destroy_cb(self, widget):
        """Remove all of my callbacks from the register database"""
        for cb in self._auto_updater_cbs:
            deregister_cb(cb)
        # this callback seems to get called twice, so ...
        self._auto_updater_cbs = []

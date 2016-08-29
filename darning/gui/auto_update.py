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

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .. import enotify

from . import gutils
from . import actions

initialize_event_flags = lambda args: 0

def set_initialize_event_flags(func):
    # NB: need extra level of function to avoid import loop/gridlock
    initialize_event_flags = func

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
    DEBUG = False # set to True to investigate unexpected activity
    invalid_cbs = []
    event_args = {}
    # do any necessary initialization of flags and arguments
    event_flags = initialize_event_flags(event_args)
    if DEBUG: print("AA START:", event_flags)
    for callback in _REGISTERED_CBS:
        try:
            # pass event_flags in to give the client a chance to skip
            # any checks if existing flags would cause them to update anyway
            if DEBUG:
                cb_flags = callback(event_flags, event_args)
                if cb_flags:
                    print("AA FIRE:", cb_flags, callback)
                event_flags |= cb_flags
            else:
                event_flags |= callback(event_flags, event_args)
        except Exception as edata:
            # TODO: try to be more explicit in naming exception type to catch here
            # this is done to catch the race between a caller has going away and deleting its registers
            if True: # NB: for debug assistance e.g . locating exceptions not due to caller going away
                print("AUTO UPDATE:", edata, callback, event_flags, event_args)
                raise edata
            invalid_cbs.append(callback)
    if DEBUG: print("AA END:", event_flags)
    if event_flags:
        enotify.notify_events(event_flags, **event_args)
    for cb in invalid_cbs:
        deregister_cb(cb)

trigger_auto_update = _auto_update_cb

AUTO_UPDATE = gutils.TimeOutController(
    toggle_data=gutils.TimeOutController.ToggleData(
        name='config_auto_update',
        label=_('Auto Update'),
        tooltip=_('Enable/disable automatic updating of displayed data'),
        stock_id=Gtk.STOCK_REFRESH
    ),
    function=_auto_update_cb, is_on=True, interval=10000
)

actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_action(AUTO_UPDATE.toggle_action)
actions.CLASS_INDEP_AGS[actions.AC_DONT_CARE].add_actions(
    [
        ("au_update_all", Gtk.STOCK_REFRESH, _("Freshen"), "",
         _("Freshen all views. Useful after external actions change workspace/playground state and auto update is disabled."),
         lambda _action=None: trigger_auto_update()
         ),
    ]
)

class AutoUpdater:
    """A base class for transient GTK object classes that wish to register
    auto update callbacks so that their callbacks are deleted when they are
    destroyed.
    """
    def __init__(self):
        self._auto_updater_cbs = []
        try:
            self.connect("destroy", self.auto_updater_destroy_cb)
        except TypeError:
            pass

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

    def auto_updater_destroy_cb(self, *args):
        """Remove all of my callbacks from the register database"""
        for cb in self._auto_updater_cbs:
            deregister_cb(cb)
        # this callback seems to get called twice, so ...
        self._auto_updater_cbs = []

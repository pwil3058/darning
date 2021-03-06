darning
=======

Patch series management.

Status
------

This software is still under development and is only Alpha standard at
this time.  The core functionality has been rewritten and is now
incompatible with legacy playgrounds.

Some script based testing has been undertaken.

Requirements
------------

This software requires:
 * Python 3.5 or later
 * PyGObject 3.0 or later

This software works better with:
 * meld 1.5 or later

This software works best when used with SCM managed sources where it
understands the SCM in use.  At present, it only has knowledge of the
following SCMs:
  * Mercurial
  * Git

Installation
------------

It is NOT necessary to install this software in order to use it.  All
that is necessary for the applications (darn and gdarn) to be usable is
for the base directory to be in the usere PATH environment variable.

However, if you wish to install it do:

    make install

on Unix like systems and:

    python3 setup.py install

on other systems (but be aware this has only been tested on Linux).

To run the test scripts do:

    make check

Usage
-----

This tool has both a GUI, `gdarn`, (which is the primary interface and
most complete) and a command line interface, `darn`, (very minimal at the
moment and mainly used for testing) for those who don't like GUIs.

Internationalization
--------------------

The code is extensively hooked for i18n but (at the moment) there is no
localization available for languages other than English.

Bugs
----

It would be greatly appreciated if any bugs encountered by users are
reported by creating an issue.

Feature Requests
----------------

Feature requests can be made by creating an issue.

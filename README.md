RunCommand
==========

When I started using Sublime Text I was curious to experiment with all the
possible commands I could use - but some of them were only accessible through
the Python console, which wasn't very handy. Thus, I created a plugin to call
arbitrary commands. Can also help with plugin development.

Command palette
===============
3 new commands are available:

- Run Application Command
- Run Window Command
- Run Text Command

They all work in the same way - display a list of commands of specified kind,
allowing to call them with arbitrary arguments. The syntax for arguments is
comma-separated list of JSON values, they can be specified by name the same way
as in Python.

Settings
========
There are 3 bool settings you can configure in Preferences.sublime-settings:

- runcmd\_show\_arguments
- runcmd\_show\_boring\_defaults
- runcmd\_show\_docstring

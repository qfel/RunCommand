from __future__ import division

import json
import re

import sublime

from collections import namedtuple
from functools import partial
from inspect import getargspec
from itertools import chain, izip
from operator import attrgetter
from types import BuiltinMethodType, MethodType

from sublime_plugin import ApplicationCommand, TextCommand, WindowCommand, \
    application_command_classes, text_command_classes, window_command_classes


CommandInfo = namedtuple('CommandInfo', 'name required_args optional_args doc '
                         'has_arbitrary_args')


g_settings = sublime.load_settings('RunCommand.sublime-settings')


def parse_arguments(args):
    ''' Parse string containing command arguments.

    args: A string of the form:
          JSON1, JSON2, ..., nameA = JSONA, nameB = JSONB, ...

    Returns a pair of positional and keyword arguments.
    '''
    varargs = []
    kwargs = {}
    decoder = json.JSONDecoder()
    arg_name = None
    args = args.lstrip()
    while args:
        kw_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*', args)
        if kw_match:
            arg_name = kw_match.group(1)
            args = args[kw_match.end():]
        elif arg_name:
            raise ValueError('Expected argument name: ' + args)
        arg, i = decoder.raw_decode(args)
        args = args[i:].lstrip()
        if arg_name:
            kwargs[arg_name] = arg
        else:
            varargs.append(arg)
        if args.startswith(','):
            args = args[1:].lstrip()
        elif args:
            raise ValueError('Expected ",": ' + args)
    return varargs, kwargs


def has_any_args(cmd):
    return bool(cmd.required_args or cmd.optional_args or
                cmd.has_arbitrary_args)


def format_arguments(cmd):
    show_boring = g_settings.get('show_boring_defaults')
    optional_args = []
    for name, value in cmd.optional_args:
        if show_boring or value:
            optional_args.append(u'{0}={1}'.format(name, json.dumps(value)))
        else:
            optional_args.append(name)
    if cmd.has_arbitrary_args:
        optional_args.append('...')
    return u', '.join(chain(cmd.required_args, optional_args))


class RunCommand(object):
    def get_builtin_command_info(self, cmd):
        required_args = []
        optional_args = []
        for arg in cmd.get('args', []):
            if isinstance(arg, list):
                if len(arg) != 2:
                    raise ValueError('Need exactly argument name and '
                                     'default value')
                optional_args.append(arg)
            elif not optional_args:
                required_args.append(arg)
            else:
                raise ValueError('Cannot specify required arguments after '
                                 'optional ones')
        return CommandInfo(name=cmd['name'], doc=cmd.get('doc'),
                           required_args=required_args,
                           optional_args=optional_args,
                           has_arbitrary_args=cmd.get('has_arbitrary_args',
                                                      False))

    def get_plugin_command_info(self, cmd_cls):
        # Optionally strip the "Command" suffix.
        SUFFIX = 'Command'
        name = cmd_cls.__name__
        if name.endswith(SUFFIX):
            name = name[:-len(SUFFIX)]

        # Translate SomeName into some_name.
        name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name).lower()

        # Create argument lists.
        spec = getargspec(cmd_cls.run)
        skip_args = self.SKIP_ARGS + \
            isinstance(cmd_cls.run, (MethodType, BuiltinMethodType))

        # Strip first skip_args.
        args = spec.args[skip_args:]
        if args:
            defaults = (spec.defaults or [])[-len(args):]
        else:
            defaults = []

        # Skip last len(defaults).
        required_args = args[: -len(defaults) or None]

        # Take last len(defaults).
        if defaults:
            optional_args = zip(args[-len(defaults):], defaults)
        else:
            optional_args = []

        return CommandInfo(name=name, required_args=required_args,
                           doc=cmd_cls.__doc__ or cmd_cls.run.__doc__,
                           optional_args=optional_args,
                           has_arbitrary_args=bool(spec.keywords))

    def run_command(self, cmd, args={}):
        try:
            self.get_command_runner().run_command(cmd, args)
        except Exception as e:
            sublime.error_message('Command caused an error: ' + unicode(e))
            raise  # Re-raise to get stack trace logged to Python console.

    def handle_command(self, commands, index):
        if index == -1:
            return

        cmd = commands[index]
        if has_any_args(cmd):
            self.get_window().show_input_panel(format_arguments(cmd) + ':', '',
                    partial(self.handle_complex_command, cmd), None, None)
        else:
            self.run_command(cmd.name)

    def handle_complex_command(self, cmd, args):
        try:
            positional_args, named_args = parse_arguments(args)
        except Exception as e:
            sublime.error_message(unicode(e))
            return

        # Translate positional arguments to named ones.
        positional_args = iter(positional_args)
        for name, value in izip(chain(cmd.required_args,
                                      (name for name, _ in cmd.optional_args)),
                                positional_args):
            if name in named_args:
                raise ValueError('Repeated value for argument "{0}"'.format(
                        name))
            named_args[name] = value

        try:
            next(positional_args)
        except StopIteration:
            pass
        else:
            raise ValueError('Too many positional arguments')

        # Finally, run the command
        self.run_command(cmd.name, named_args)

    def get_command_desc(self, cmd):
        desc = [cmd.name]
        if g_settings.get('show_arguments'):
            if has_any_args(cmd):
                desc.append(format_arguments(cmd))
            else:
                desc.append('No arguments')
        if g_settings.get('show_doc') and cmd.doc:
            desc.append(cmd.doc.strip().split('\n', 1)[0])
        return desc

    def run(self):
        # Build command list.
        commands = map(self.get_plugin_command_info, self.COMMANDS)
        commands.extend(self.get_builtin_command_info(cmd) for cmd
                        in g_settings.get(self.TYPE_NAME + '_commands', []))

        # Sort command names and display to the user.
        commands.sort(key=attrgetter('name'))
        self.get_window().show_quick_panel(
                [self.get_command_desc(cmd) for cmd in commands],
                partial(self.handle_command, commands))


class RunTextCommandCommand(RunCommand, TextCommand):
    COMMANDS = text_command_classes
    SKIP_ARGS = 1
    TYPE_NAME = 'text'

    def get_window(self):
        return self.view.window()

    def get_command_runner(self):
        return self.view

    def run(self, edit):
        RunCommand.run(self)


class RunWindowCommandCommand(RunCommand, WindowCommand):
    COMMANDS = window_command_classes
    SKIP_ARGS = 0
    TYPE_NAME = 'window'

    def get_window(self):
        return self.window

    def get_command_runner(self):
        return self.window


class RunApplicationCommandCommand(RunCommand, ApplicationCommand):
    COMMANDS = application_command_classes
    SKIP_ARGS = 0
    TYPE_NAME = 'application'

    def get_window(self):
        return sublime.active_window()

    def get_command_runner(self):
        return sublime

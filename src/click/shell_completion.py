import copy
import os
import re
from abc import ABC
from abc import abstractmethod
from collections import abc
from subprocess import PIPE
from subprocess import run

from .core import Argument
from .core import MultiCommand
from .core import Option
from .parser import split_arg_string
from .utils import echo

WORDBREAK = "="

# Note, only BASH version 4.4 and later have the nosort option.
COMPLETION_SCRIPT_BASH = """
%(complete_func)s() {
    local IFS=$'\n'
    local response

    response=$( env COMP_WORDS="${COMP_WORDS[*]}" \\
                   COMP_CWORD=$COMP_CWORD \\
                   %(autocomplete_var)s=complete $1 )

    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        if [[ $type == 'dir' ]]; then
            COMREPLY=()
            compopt -o dirnames
        elif [[ $type == 'file' ]]; then
            COMREPLY=()
            compopt -o default
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        fi
    done

    return 0
}

%(complete_func)s_setup() {
    complete -o nosort -F %(complete_func)s %(script_names)s
}

%(complete_func)s_setup
"""

COMPLETION_SCRIPT_ZSH = """
#compdef %(script_names)s

%(complete_func)s() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    (( ! $+commands[%(script_names)s] )) && return 1

    response=("${(@f)$( env COMP_WORDS=\"${words[*]}\" \\
                        COMP_CWORD=$((CURRENT-1)) \\
                        %(autocomplete_var)s=\"complete_zsh\" \\
                        %(script_names)s )}")

    for type key descr in ${response}; do
      if [[ "$type" == "plain" ]]; then
        if [[ "$descr" == "_" ]]; then
          completions+=("$key")
        else
          completions_with_descriptions+=("$key":"$descr")
        fi
      elif [[ "$type" == "dir" ]]; then
        _path_files -/
      elif [[ "$type" == "file" ]]; then
        _path_files -f
      fi
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ -n "$completions" ]; then
        compadd -U -V unsorted -a completions
    fi
    compstate[insert]="menucomplete"
}

compdef %(complete_func)s %(script_names)s
"""


COMPLETION_SCRIPT_FISH = """
function %(complete_func)s_complete;
    set -l response;
    for value in (env %(autocomplete_var)s=complete_fish \
        COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) \
        %(script_names)s);
        set response $response $value;
    end;

    for completion in $response;
        set -l metadata (string split "," $completion);
        if test $metadata[1] = "dir";
            __fish_complete_directories $metadata[2];
        else if test $metadata[1] = "file";
            __fish_complete_path $metadata[2];
        else if test $metadata[1] = "plain";
            echo $metadata[2];
        end;
    end;
end;

complete --no-files --command %(script_names)s --arguments \
    "(%(complete_func)s_complete)"
"""

_invalid_ident_char_re = re.compile(r"[^a-zA-Z0-9_]")


def start_of_option(param_str):
    """Returns whether or not this si the start of an option declaration
    (i.e, starts with "-" or "--")

    :param param_str: param_str to check
    """
    return param_str and param_str[:1] == "-"


class ShellComplete(ABC):
    """The ShellComplete class acts as the minimal API contract of a
    completion class.  It is not intended to be used directly as
    :meth:`source` and :meth:`complete` must be overridden.


    :param prog_name: the program name that should be used.  By default
                        the program name is constructed by taking the
                        file name from ``sys.argv[0]``.

    :param complete_var: the environment variable used to activate
                         shell completion.
    :param cli: command definition
    """

    def __init__(self, prog_name, complete_var, cli):
        # set shell-specific environment variables
        self.prog_name = prog_name
        self.complete_var = complete_var
        self.cli = cli

    @abstractmethod
    def source(self):
        """Returns the string to be echoed during activation, and is
        automatically invoked by :func:`shell_complete`. The string
        will also be formatted with the variables ``script_name``,
        ``autocomplete_var`` and ``complete_func`` first.

        The default implementation is raising a not implemented error.
        """
        pass

    @abstractmethod
    def complete(self):
        """This function is automatically invoked during completion by
        :func:`shell_complete`. It can be used to get completion responses
        from parameters/types, handle special commands in shell-specific ways,
        output other information for the command type, etc. Whatever the case
        may be, the function should also return ``True``.

        The default implementation is raising a not implemented error.
        """
        pass


class BashComplete(ShellComplete):
    def source(self):
        if bash_version_not_usable():
            raise Exception(
                "Shell completion is not supported for bash versions older than 4.4"
            )
        return COMPLETION_SCRIPT_BASH

    def complete(self):
        cwords = split_arg_string(os.environ["COMP_WORDS"])
        cword = int(os.environ["COMP_CWORD"])
        args = cwords[1:cword]
        try:
            incomplete = cwords[cword]
        except IndexError:
            incomplete = ""

        completions = do_complete(self.cli, self.prog_name, args, incomplete)
        for item in completions:
            echo(f"{item[0]},{item[1]}")

        return True


class ZshComplete(ShellComplete):
    def source(self):
        return COMPLETION_SCRIPT_ZSH

    def complete(self):
        cwords = split_arg_string(os.environ["COMP_WORDS"])
        cword = int(os.environ["COMP_CWORD"])
        args = cwords[1:cword]
        try:
            incomplete = cwords[cword]
        except IndexError:
            incomplete = ""

        completions = do_complete(self.cli, self.prog_name, args, incomplete)
        for item in completions:
            echo(item[0])
            echo(item[1])
            echo(item[2] if item[2] else "_")

        return True


class FishComplete(ShellComplete):
    def source(self):
        return COMPLETION_SCRIPT_FISH

    def complete(self):
        cwords = split_arg_string(os.environ["COMP_WORDS"])
        incomplete = os.environ["COMP_CWORD"]
        args = cwords[1:]

        # Fish is weird in that a partially completed path is registered in
        # both `COMP_WORDS` and `COMP_CWORD`.
        if incomplete and args and args[-1] == incomplete:
            args.pop()

        completions = do_complete(self.cli, self.prog_name, args, incomplete)
        for item in completions:
            if item[2]:
                echo(f"{item[0]},{item[1]}\t{item[2]}")
            else:
                echo(f"{item[0]},{item[1]}")

        return True


available_shells = {
    "bash": BashComplete,
    "fish": FishComplete,
    "zsh": ZshComplete,
}


def bash_version_not_usable():
    """Returns whether or not the user's bash version is older than 4.4.x"""
    output = run(["bash", "--version"], stdout=PIPE)
    match = re.search(r"\d\.\d\.\d", output.stdout.decode())
    if match:
        bash_version = match.group().split(".")
        if bash_version[0] < "4" or bash_version[0] == "4" and bash_version[1] < "4":
            return True
        return False


def do_complete(cli, prog_name, args, incomplete):
    """Given a list of current arguments and a partial value, return a list of
    metadata in the form of `(type, value, help)`.

    :param cli: the cli instance
    :param prog_name: the program name
    :param args: the list of arguments in the current command line
    :param incomplete: the partial value to be completed

    """
    all_args = copy.deepcopy(args)
    ctx = resolve_ctx(cli, prog_name, args)
    if ctx is None:
        return []

    partial_value, incomplete = resolve_partial_value(ctx, all_args, incomplete)
    return partial_value.shell_complete(ctx, all_args, incomplete)


def get_completion_script(cli, prog_name, complete_var, shell):
    """Returns a completion script formatted with the variables `complete_func`,
    `script_names`, and `autocomplete_var` based on the given shell

    :param cli: the cli instance
    :param prog_name: the program name
    :param complete_var: the environment variable used to activate shell completion
    :param shell: the current shell
    """
    cf_name = _invalid_ident_char_re.sub("", prog_name.replace("-", "_"))

    completion_source = get_completion_source(shell)
    completion_object = completion_source(prog_name, complete_var, cli)

    return (
        completion_object.source()
        % {
            "complete_func": f"_{cf_name}_completion",
            "script_names": prog_name,
            "autocomplete_var": complete_var,
        }
    ).strip() + ";"


def add_completion_class(name, completion_class):
    """Adds the given completion class to the dictionary of available
    shells under the given name. If the completion class does not
    extend :class:`ShellComplete`, an error is raised.

    :param name: the name of the shell. Must match the shell name used
                 during activation: `source_{shell}`.
    :param completion_class: the class to be instantiated for completion
    """
    global available_shells

    if not issubclass(completion_class, ShellComplete):
        raise TypeError("Completion class must extend 'ShellComplete'")

    available_shells[name] = completion_class


def get_completion_source(shell):
    """Returns the completion class using the given shell as the key, and
    defaults to the `ShellComplete` class otherwise.

    :param shell: the current shell
    """
    return available_shells.get(shell, ShellComplete)


def is_incomplete_argument(current_params, cmd_param):
    """Returns whether or not the last argument is complete and corresponds
    to `cmd_param`. In other words, determine if `cmd_param` can still accept
    values.

    :param current_params: the current params and values for this argument
                           as already entered
    :param cmd_param: the current command parameter
    """
    if not isinstance(cmd_param, Argument):
        return False
    current_param_values = current_params[cmd_param.name]
    if current_param_values is None:
        return True
    if cmd_param.nargs == -1:
        return True
    if (
        isinstance(current_param_values, abc.Iterable)
        and cmd_param.nargs > 1
        and len(current_param_values) < cmd_param.nargs
    ):
        return True
    return False


def is_incomplete_option(all_args, cmd_param):
    """Returns whether or not the last option declaration (i.e. starts with
    "-" or "--") is incomplete and corresponse to `cmd_param`. In other words,
    determine if `cmd_param` can still accept values.

    :param all_args: the full original list of args supplied
    :param cmd_param: the current command parameter
    """
    if not isinstance(cmd_param, Option):
        return False
    if cmd_param.is_flag:
        return False
    last_option = None
    for index, arg_str in enumerate(
        reversed([arg for arg in all_args if arg != WORDBREAK])
    ):
        if index + 1 > cmd_param.nargs:
            break
        if start_of_option(arg_str):
            last_option = arg_str

    return True if last_option and last_option in cmd_param.opts else False


def resolve_partial_value(ctx, all_args, incomplete):
    """Returns the click object that will handle the completion of the partial
    value and the partial value itself.

    :param all_args: full list of args
    :param ctx: the final context/command parsed
    :param incomplete: the incomplete text to autocomplete
    :return: the partial value and incomplete
    """
    has_double_dash = "--" in all_args

    # In newer versions of bash long opts with '='s are partitioned, but
    # it's easier to parse without the '='
    if start_of_option(incomplete) and WORDBREAK in incomplete:
        partition_incomplete = incomplete.partition(WORDBREAK)
        all_args.append(partition_incomplete[0])
        incomplete = partition_incomplete[2]
    elif incomplete == WORDBREAK:
        incomplete = ""

    if not has_double_dash and start_of_option(incomplete):
        return ctx.command, incomplete
    # completion for option values from user supplied values
    for param in ctx.command.get_params(ctx):
        if is_incomplete_option(all_args, param):
            return param, incomplete
    # completion for argument values from user supplied values
    for param in ctx.command.get_params(ctx):
        if is_incomplete_argument(ctx.params, param):
            return param, incomplete

    return ctx.command, incomplete


def resolve_ctx(cli, prog_name, args):
    """Parse into a hierarchy of contexts. Contexts are connected
    through the parent variable.

    :param cli: cli instance
    :param prog_name: program name
    :param args: full list of args
    :return: the final context/command parsed
    """
    ctx = cli.make_context(prog_name, args, resilient_parsing=True)
    args = ctx.protected_args + ctx.args
    while args:
        if isinstance(ctx.command, MultiCommand):
            if not ctx.command.chain:
                cmd_name, cmd, args = ctx.command.resolve_command(ctx, args)
                if cmd is None:
                    return ctx
                ctx = cmd.make_context(
                    cmd_name, args, parent=ctx, resilient_parsing=True
                )
                args = ctx.protected_args + ctx.args
            else:
                # Walk chained subcommand contexts saving the last one.
                while args:
                    cmd_name, cmd, args = ctx.command.resolve_command(ctx, args)
                    if cmd is None:
                        return ctx
                    sub_ctx = cmd.make_context(
                        cmd_name,
                        args,
                        parent=ctx,
                        allow_extra_args=True,
                        allow_interspersed_args=False,
                        resilient_parsing=True,
                    )
                    args = sub_ctx.args
                ctx = sub_ctx
                args = sub_ctx.protected_args + sub_ctx.args
        else:
            break
    return ctx


def shell_complete(cli, prog_name, complete_var, complete_instr):
    if "_" in complete_instr:
        command, shell = complete_instr.split("_", 1)
    else:
        command = complete_instr
        shell = "bash"

    if command == "source":
        echo(get_completion_script(cli, prog_name, complete_var, shell))
        return True
    elif command == "complete":
        completion_object = get_completion_source(shell)(prog_name, complete_var, cli)
        return completion_object.complete()

    return False

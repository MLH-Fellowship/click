import copy

import pytest

import click
from click.core import Command
from click.core import MultiCommand
from click.core import Parameter
from click.shell_completion import add_completion_class
from click.shell_completion import do_complete
from click.shell_completion import resolve_ctx
from click.shell_completion import resolve_partial_value


def get_completions(cli, args, incomplete):
    return [c[1] for c in do_complete(cli, cli.name, args, incomplete)]


def get_type(cli, args, incomplete):
    return [c[0] for c in do_complete(cli, cli.name, args, incomplete)]


def get_partial_value(cli, args, incomplete):
    prog_name = cli.name
    all_args = copy.deepcopy(args)
    ctx = resolve_ctx(cli, prog_name, args)
    if ctx is None:
        return []

    return resolve_partial_value(ctx, all_args, incomplete)[0]


def test_partial_value_command():
    @click.command()
    @click.option("--opt")
    def cli(opt):
        pass

    assert isinstance(get_partial_value(cli, [], ""), Command)
    assert isinstance(get_partial_value(cli, [], "-"), Command)
    assert isinstance(get_partial_value(cli, [], "--"), Command)


def test_partial_value_multi_value_option():
    @click.group()
    @click.option("--pos", nargs=2, type=float)
    def cli(local_opt):
        pass

    @cli.command()
    @click.option("--local-opt")
    def sub(local_opt):
        pass

    assert isinstance(get_partial_value(cli, [], ""), MultiCommand)
    assert isinstance(get_partial_value(cli, [], "-"), Command)
    assert isinstance(get_partial_value(cli, ["--pos"], ""), Parameter)
    assert isinstance(get_partial_value(cli, ["--pos", "1.0"], ""), Parameter)
    assert isinstance(get_partial_value(cli, ["--pos", "1.0", "1.0"], ""), Command)


def test_add_completion_class():
    from click.shell_completion import available_shells
    from click.shell_completion import ShellComplete

    class MyComplete(ShellComplete):
        def source(self):
            return 'complete -W "foo bar" cli'

        def complete(self):
            return True

    assert available_shells.get("myshell", None) is None

    add_completion_class("myshell", MyComplete)
    assert available_shells.get("myshell", None) == MyComplete


def test_add_completion_class_fail():
    class MyComplete:
        def source(self):
            return 'complete -W "foo bar" cli'

        def complete(self):
            return True

    with pytest.raises(TypeError, match="Completion class must extend 'ShellComplete'"):
        add_completion_class("myshell", MyComplete)


def test_shell_complete_path():
    @click.command()
    @click.option("--default", type=click.Path())
    @click.option("--dir", type=click.Path(file_okay=False))
    @click.option("--no-dir", type=click.Path(dir_okay=False))
    def cli(default, dir, no_dir):
        pass

    assert get_type(cli, ["--default"], "../") == [("file")]
    assert get_type(cli, ["--dir"], "../") == [("dir")]
    assert get_type(cli, ["--no-dir"], "../") == [("file")]


def test_single_command():
    @click.command()
    @click.option("--opt")
    def cli(opt):
        pass

    assert get_completions(cli, [], "") == []
    assert get_completions(cli, [], "-") == [
        "--opt",
        "--help",
    ]


def test_boolean_flag():
    @click.command()
    @click.option("--shout/--no-shout", default=False)
    def cli(local_opt):
        pass

    assert get_completions(cli, [], "-") == [
        "--shout",
        "--no-shout",
        "--help",
    ]


def test_multi_value_option():
    @click.group()
    @click.option("--pos", nargs=2, type=float)
    def cli(local_opt):
        pass

    @cli.command()
    @click.option("--local-opt")
    def sub(local_opt):
        pass

    assert get_completions(cli, [], "-") == ["--pos", "--help"]
    assert get_completions(cli, ["--pos"], "") == []
    assert get_completions(cli, ["--pos", "1.0"], "") == []
    assert get_completions(cli, ["--pos", "1.0", "1.0"], "") == ["sub"]


def test_multi_option():
    @click.command()
    @click.option("--message", "-m", multiple=True)
    def cli(local_opt):
        pass

    assert get_completions(cli, [], "-") == [
        "--message",
        "-m",
        "--help",
    ]
    assert get_completions(cli, ["-m"], "") == []


def test_small_chain():
    @click.group()
    @click.option("--global-opt")
    def cli(global_opt):
        pass

    @cli.command()
    @click.option("--local-opt")
    def sub(local_opt):
        pass

    assert get_completions(cli, [], "") == ["sub"]
    assert get_completions(cli, [], "-") == [
        "--global-opt",
        "--help",
    ]
    assert get_completions(cli, ["sub"], "") == []
    assert get_completions(cli, ["sub"], "-") == [
        "--local-opt",
        "--help",
    ]


def test_long_chain():
    @click.group("cli")
    @click.option("--cli-opt")
    def cli(cli_opt):
        pass

    @cli.group("asub")
    @click.option("--asub-opt")
    def asub(asub_opt):
        pass

    @asub.group("bsub")
    @click.option("--bsub-opt")
    def bsub(bsub_opt):
        pass

    COLORS = ["red", "green", "blue"]

    def get_colors(ctx, args, incomplete):
        for c in COLORS:
            if c.startswith(incomplete):
                yield c

    def search_colors(ctx, args, incomplete):
        for c in COLORS:
            if incomplete in c:
                yield c

    CSUB_OPT_CHOICES = ["foo", "bar"]
    CSUB_CHOICES = ["bar", "baz"]

    @bsub.command("csub")
    @click.option("--csub-opt", type=click.Choice(CSUB_OPT_CHOICES))
    @click.option("--csub", type=click.Choice(CSUB_CHOICES))
    @click.option("--search-color", autocompletion=search_colors)
    @click.argument("color", autocompletion=get_colors)
    def csub(csub_opt, color):
        pass

    assert get_completions(cli, [], "-") == ["--cli-opt", "--help"]
    assert get_completions(cli, [], "") == ["asub"]
    assert get_completions(cli, ["asub"], "-") == [
        "--asub-opt",
        "--help",
    ]
    assert get_completions(cli, ["asub"], "") == ["bsub"]
    assert get_completions(cli, ["asub", "bsub"], "-") == [
        "--bsub-opt",
        "--help",
    ]
    assert get_completions(cli, ["asub", "bsub"], "") == ["csub"]
    assert get_completions(cli, ["asub", "bsub", "csub"], "-") == [
        "--csub-opt",
        "--csub",
        "--search-color",
        "--help",
    ]
    assert (
        get_completions(cli, ["asub", "bsub", "csub", "--csub-opt"], "")
        == CSUB_OPT_CHOICES
    )
    assert get_completions(cli, ["asub", "bsub", "csub"], "--csub") == [
        "--csub-opt",
        "--csub",
    ]
    assert get_completions(cli, ["asub", "bsub", "csub", "--csub"], "") == CSUB_CHOICES
    assert get_completions(cli, ["asub", "bsub", "csub", "--csub-opt"], "f") == ["foo"]
    assert get_completions(cli, ["asub", "bsub", "csub"], "") == COLORS
    assert get_completions(cli, ["asub", "bsub", "csub"], "b") == ["blue"]
    assert get_completions(cli, ["asub", "bsub", "csub", "--search-color"], "een") == [
        "green"
    ]


def test_chaining():
    @click.group("cli", chain=True)
    @click.option("--cli-opt")
    @click.argument("arg", type=click.Choice(["cliarg1", "cliarg2"]))
    def cli(cli_opt, arg):
        pass

    @cli.command()
    @click.option("--asub-opt")
    def asub(asub_opt):
        pass

    @cli.command(help="bsub help")
    @click.option("--bsub-opt")
    @click.argument("arg", type=click.Choice(["arg1", "arg2"]))
    def bsub(bsub_opt, arg):
        pass

    @cli.command()
    @click.option("--csub-opt")
    @click.argument("arg", type=click.Choice(["carg1", "carg2"]), default="carg1")
    def csub(csub_opt, arg):
        pass

    assert get_completions(cli, [], "-") == ["--cli-opt", "--help"]
    assert get_completions(cli, [], "") == ["cliarg1", "cliarg2"]
    assert get_completions(cli, ["cliarg1", "asub"], "-") == [
        "--asub-opt",
        "--help",
    ]
    assert get_completions(cli, ["cliarg1", "asub"], "") == [
        "bsub",
        "csub",
    ]
    assert get_completions(cli, ["cliarg1", "bsub"], "") == [
        "arg1",
        "arg2",
    ]
    assert get_completions(cli, ["cliarg1", "asub", "--asub-opt"], "") == []
    assert get_completions(
        cli, ["cliarg1", "asub", "--asub-opt", "5", "bsub"], "-"
    ) == ["--bsub-opt", "--help"]
    assert get_completions(cli, ["cliarg1", "asub", "bsub"], "-") == [
        "--bsub-opt",
        "--help",
    ]
    assert get_completions(cli, ["cliarg1", "asub", "csub"], "") == [
        "carg1",
        "carg2",
    ]
    assert get_completions(cli, ["cliarg1", "bsub", "arg1", "csub"], "") == [
        "carg1",
        "carg2",
    ]
    assert get_completions(cli, ["cliarg1", "asub", "csub"], "-") == [
        "--csub-opt",
        "--help",
    ]
    assert do_complete(cli, cli.name, ["cliarg1", "asub"], "b") == [
        ("plain", "bsub", "bsub help")
    ]


def test_argument_choice():
    @click.command()
    @click.argument("arg1", required=True, type=click.Choice(["arg11", "arg12"]))
    @click.argument("arg2", type=click.Choice(["arg21", "arg22"]), default="arg21")
    @click.argument("arg3", type=click.Choice(["arg", "argument"]), default="arg")
    def cli():
        pass

    assert get_completions(cli, [], "") == ["arg11", "arg12"]
    assert get_completions(cli, [], "arg") == ["arg11", "arg12"]
    assert get_completions(cli, ["arg11"], "") == ["arg21", "arg22"]
    assert get_completions(cli, ["arg12", "arg21"], "") == ["arg", "argument"]
    assert get_completions(cli, ["arg12", "arg21"], "argu") == ["argument"]


def test_option_choice():
    @click.command()
    @click.option("--opt1", type=click.Choice(["opt11", "opt12"]), help="opt1 help")
    @click.option("--opt2", type=click.Choice(["opt21", "opt22"]), default="opt21")
    @click.option("--opt3", type=click.Choice(["opt", "option"]))
    def cli():
        pass

    assert do_complete(cli, cli.name, [], "-") == [
        ("plain", "--opt1", "opt1 help"),
        ("plain", "--opt2", None),
        ("plain", "--opt3", None),
        ("plain", "--help", "Show this message and exit."),
    ]
    assert get_completions(cli, [], "--opt") == ["--opt1", "--opt2", "--opt3"]
    assert get_completions(cli, [], "--opt1=") == ["opt11", "opt12"]
    assert get_completions(cli, [], "--opt2=") == ["opt21", "opt22"]
    assert get_completions(cli, ["--opt2"], "=") == ["opt21", "opt22"]
    assert get_completions(cli, ["--opt2", "="], "opt") == ["opt21", "opt22"]
    assert get_completions(cli, ["--opt1"], "") == ["opt11", "opt12"]
    assert get_completions(cli, ["--opt2"], "") == ["opt21", "opt22"]
    assert get_completions(cli, ["--opt1", "opt11", "--opt2"], "") == [
        "opt21",
        "opt22",
    ]
    assert get_completions(cli, ["--opt2", "opt21"], "-") == [
        "--opt1",
        "--opt3",
        "--help",
    ]
    assert get_completions(cli, ["--opt1", "opt11"], "-") == [
        "--opt2",
        "--opt3",
        "--help",
    ]
    assert get_completions(cli, ["--opt1"], "opt") == ["opt11", "opt12"]
    assert get_completions(cli, ["--opt3"], "opti") == ["option"]

    assert get_completions(cli, ["--opt1", "invalid_opt"], "-") == [
        "--opt2",
        "--opt3",
        "--help",
    ]


def test_option_and_arg_choice():
    @click.command()
    @click.option("--opt1", type=click.Choice(["opt11", "opt12"]))
    @click.argument("arg1", required=False, type=click.Choice(["arg11", "arg12"]))
    @click.option("--opt2", type=click.Choice(["opt21", "opt22"]))
    def cli():
        pass

    assert get_completions(cli, ["--opt1"], "") == ["opt11", "opt12"]
    assert get_completions(cli, [""], "--opt1=") == ["opt11", "opt12"]
    assert get_completions(cli, [], "") == ["arg11", "arg12"]
    assert get_completions(cli, ["--opt2"], "") == ["opt21", "opt22"]
    assert get_completions(cli, ["arg11"], "--opt") == ["--opt1", "--opt2"]
    assert get_completions(cli, [], "--opt") == ["--opt1", "--opt2"]


def test_boolean_flag_choice():
    @click.command()
    @click.option("--shout/--no-shout", default=False)
    @click.argument("arg", required=False, type=click.Choice(["arg1", "arg2"]))
    def cli(local_opt):
        pass

    assert get_completions(cli, [], "-") == [
        "--shout",
        "--no-shout",
        "--help",
    ]
    assert get_completions(cli, ["--shout"], "") == ["arg1", "arg2"]


def test_multi_value_option_choice():
    @click.command()
    @click.option("--pos", nargs=2, type=click.Choice(["pos1", "pos2"]))
    @click.argument("arg", required=False, type=click.Choice(["arg1", "arg2"]))
    def cli(local_opt):
        pass

    assert get_completions(cli, ["--pos"], "") == ["pos1", "pos2"]
    assert get_completions(cli, ["--pos", "pos1"], "") == ["pos1", "pos2"]
    assert get_completions(cli, ["--pos", "pos1", "pos2"], "") == [
        "arg1",
        "arg2",
    ]
    assert get_completions(cli, ["--pos", "pos1", "pos2", "arg1"], "") == []


def test_multi_option_choice():
    @click.command()
    @click.option("--message", "-m", multiple=True, type=click.Choice(["m1", "m2"]))
    @click.argument("arg", required=False, type=click.Choice(["arg1", "arg2"]))
    def cli(local_opt):
        pass

    assert get_completions(cli, ["-m"], "") == ["m1", "m2"]
    assert get_completions(cli, ["-m", "m1", "-m"], "") == ["m1", "m2"]
    assert get_completions(cli, ["-m", "m1"], "") == ["arg1", "arg2"]


def test_variadic_argument_choice():
    @click.command()
    @click.option("--opt", type=click.Choice(["opt1", "opt2"]))
    @click.argument("src", nargs=-1, type=click.Choice(["src1", "src2"]))
    def cli(local_opt):
        pass

    assert get_completions(cli, ["src1", "src2"], "") == ["src1", "src2"]
    assert get_completions(cli, ["src1", "src2"], "--o") == ["--opt"]
    assert get_completions(cli, ["src1", "src2", "--opt"], "") == [
        "opt1",
        "opt2",
    ]
    assert get_completions(cli, ["src1", "src2"], "") == ["src1", "src2"]


def test_variadic_argument_complete():
    def _complete(ctx, args, incomplete):
        return ["abc", "def", "ghi", "jkl", "mno", "pqr", "stu", "vwx", "yz"]

    @click.group()
    def entrypoint():
        pass

    @click.command()
    @click.option("--opt", autocompletion=_complete)
    @click.argument("arg", nargs=-1)
    def subcommand(opt, arg):
        pass

    entrypoint.add_command(subcommand)

    assert get_completions(entrypoint, ["subcommand", "--opt"], "") == _complete(
        0, 0, 0
    )
    assert get_completions(
        entrypoint, ["subcommand", "whatever", "--opt"], ""
    ) == _complete(0, 0, 0)
    assert (
        get_completions(entrypoint, ["subcommand", "whatever", "--opt", "abc"], "")
        == []
    )


def test_long_chain_choice():
    @click.group()
    def cli():
        pass

    @cli.group()
    @click.option("--sub-opt", type=click.Choice(["subopt1", "subopt2"]))
    @click.argument(
        "sub-arg", required=False, type=click.Choice(["subarg1", "subarg2"])
    )
    def sub(sub_opt, sub_arg):
        pass

    @sub.command(short_help="bsub help")
    @click.option("--bsub-opt", type=click.Choice(["bsubopt1", "bsubopt2"]))
    @click.argument(
        "bsub-arg1", required=False, type=click.Choice(["bsubarg1", "bsubarg2"])
    )
    @click.argument(
        "bbsub-arg2", required=False, type=click.Choice(["bbsubarg1", "bbsubarg2"])
    )
    def bsub(bsub_opt):
        pass

    @sub.group("csub")
    def csub():
        pass

    @csub.command()
    def dsub():
        pass

    assert do_complete(cli, cli.name, ["sub", "subarg1"], "") == [
        ("plain", "bsub", "bsub help"),
        ("plain", "csub", ""),
    ]
    assert get_completions(cli, ["sub"], "") == ["subarg1", "subarg2"]
    assert get_completions(cli, ["sub", "--sub-opt"], "") == [
        "subopt1",
        "subopt2",
    ]
    assert get_completions(cli, ["sub", "--sub-opt", "subopt1"], "") == [
        "subarg1",
        "subarg2",
    ]
    assert get_completions(
        cli, ["sub", "--sub-opt", "subopt1", "subarg1", "bsub"], "-"
    ) == ["--bsub-opt", "--help"]
    assert get_completions(
        cli, ["sub", "--sub-opt", "subopt1", "subarg1", "bsub"], ""
    ) == ["bsubarg1", "bsubarg2"]
    assert get_completions(
        cli, ["sub", "--sub-opt", "subopt1", "subarg1", "bsub", "--bsub-opt"], ""
    ) == ["bsubopt1", "bsubopt2"]
    assert get_completions(
        cli,
        [
            "sub",
            "--sub-opt",
            "subopt1",
            "subarg1",
            "bsub",
            "--bsub-opt",
            "bsubopt1",
            "bsubarg1",
        ],
        "",
    ) == ["bbsubarg1", "bbsubarg2"]
    assert get_completions(
        cli, ["sub", "--sub-opt", "subopt1", "subarg1", "csub"], ""
    ) == ["dsub"]


def test_chained_multi():
    @click.group()
    def cli():
        pass

    @cli.group()
    def sub():
        pass

    @sub.group()
    def bsub():
        pass

    @sub.group(chain=True)
    def csub():
        pass

    @csub.command()
    def dsub():
        pass

    @csub.command()
    def esub():
        pass

    assert get_completions(cli, ["sub"], "") == ["bsub", "csub"]
    assert get_completions(cli, ["sub"], "c") == ["csub"]
    assert get_completions(cli, ["sub", "csub"], "") == ["dsub", "esub"]
    assert get_completions(cli, ["sub", "csub", "dsub"], "") == ["esub"]


def test_hidden():
    @click.group()
    @click.option("--name", hidden=True)
    @click.option("--choices", type=click.Choice([1, 2]), hidden=True)
    def cli(name):
        pass

    @cli.group(hidden=True)
    def hgroup():
        pass

    @hgroup.group()
    def hgroupsub():
        pass

    @cli.command()
    def asub():
        pass

    @cli.command(hidden=True)
    @click.option("--hname")
    def hsub():
        pass

    assert get_completions(cli, [], "--n") == []
    assert get_completions(cli, [], "--c") == []
    # If the user exactly types out the hidden param, complete its options.
    assert get_completions(cli, ["--choices"], "") == [1, 2]
    assert get_completions(cli, [], "") == ["asub"]
    assert get_completions(cli, [], "") == ["asub"]
    assert get_completions(cli, [], "h") == []
    # If the user exactly types out the hidden command, complete its subcommands.
    assert get_completions(cli, ["hgroup"], "") == ["hgroupsub"]
    assert get_completions(cli, ["hsub"], "--h") == ["--hname", "--help"]


@pytest.mark.parametrize(
    ("args", "part", "expect"),
    [
        ([], "-", ["--opt", "--help"]),
        (["value"], "--", ["--opt", "--help"]),
        ([], "-o", []),
        (["--opt"], "-o", []),
        (["--"], "", ["name", "-o", "--opt", "--"]),
        (["--"], "--o", ["--opt"]),
    ],
)
def test_args_with_double_dash_complete(args, part, expect):
    def _complete(ctx, args, incomplete):
        values = ["name", "-o", "--opt", "--"]
        return [x for x in values if x.startswith(incomplete)]

    @click.command()
    @click.option("--opt")
    @click.argument("args", nargs=-1, autocompletion=_complete)
    def cli(opt, args):
        pass

    assert get_completions(cli, args, part) == expect

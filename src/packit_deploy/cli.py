"""Usage:
  packit --version
  packit start <path> [--extra=PATH] [--option=OPTION]... [--pull]
  packit status <path>
  packit stop <path> [--volumes] [--network] [--kill] [--force]
    [--extra=PATH] [--option=OPTION]...

Options:
  --extra=PATH     Path, relative to <path>, of yml file of additional
                   configuration
  --option=OPTION  Additional configuration options, in the form key=value
                   Use dots in key for hierarchical structure, e.g., a.b=value
                   This argument may be repeated to provide multiple arguments
  --pull           Pull images before starting
  --volumes        Remove volumes (WARNING: irreversible data loss)
  --network        Remove network
  --kill           Kill the containers (faster, but possible db corruption)
"""

import docopt
import yaml
import packit_deploy.__about__ as about


def main(argv=None):
    opts = docopt.docopt(__doc__, argv)
    if opts["--version"]:
        print(about.__version__)
        return about.__version__
    else:
        path, extra, options, args = parse_args(opts)
        print(args.action)
        return path, extra, options, args


def parse_args(opts):
    path = opts["<path>"]
    extra = opts["--extra"]
    options = parse_option(opts)
    return path, extra, options, PackitArgs(opts)


def parse_option(args):
    return [string_to_dict(x) for x in args["--option"]]


def string_to_dict(string):
    """Convert a configuration option a.b.c=x to a dictionary
    {"a": {"b": "c": x}}"""
    # Won't deal with dots embedded within quotes but that's ok as
    # that should not be allowed generally.
    try:
        key, value = string.split("=")
    except ValueError as err:
        msg = f"Invalid option '{string}', expected option in form key=value"
        raise Exception(msg) from err
    value = yaml_atom_parse(value)
    for k in reversed(key.split(".")):
        value = {k: value}
    return value


def yaml_atom_parse(x):
    ret = yaml.safe_load(x)
    if type(ret) not in [bool, int, float, str]:
        msg = f"Invalid value '{x}' - expected simple type"
        raise Exception(msg)
    return ret


class PackitArgs:
    def __init__(self, args):
        if args["start"]:
            self.action = "start"
        elif args["status"]:
            self.action = "status"
        elif args["stop"]:
            self.action = "stop"

        self.pull = args["--pull"]
        self.kill = args["--kill"]
        self.volumes = args["--volumes"]
        self.network = args["--network"]

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
from packit_deploy.config import PackitConfig
from packit_deploy.packit_constellation import PackitConstellation


def main(argv=None):
    path, extra, options, args = parse_args(argv)
    if args.version:
        print(about.__version__)
        return about.__version__
    else:
        cfg = PackitConfig(path, extra, options)
        obj = PackitConstellation(cfg)
        if args.action == "start":
            packit_start(obj, args)
        elif args.action == "status":
            packit_status(obj)
        elif args.action == "stop":
            packit_stop(obj, args, cfg)
        return True


def parse_args(argv=None):
    opts = docopt.docopt(__doc__, argv)
    path = opts["<path>"]
    extra = opts["--extra"]
    options = parse_option(opts)
    return path, extra, options, PackitArgs(opts)


def packit_start(obj, args):
    obj.start(pull_images=args.pull)


def packit_status(obj):
    obj.status()


def packit_stop(obj, args, cfg):
    if args.volumes:
        verify_data_loss(cfg)
    obj.stop(kill=args.kill, remove_network=args.network, remove_volumes=args.volumes)


def verify_data_loss(cfg):
    if cfg.protect_data:
        err = "Cannot remove volumes with this configuration"
        raise Exception(err)
    else:
        print(
            """WARNING! PROBABLE IRREVERSIBLE DATA LOSS!
You are about to delete the data volumes. This action cannot be undone
and will result in the irreversible loss of *all* data associated with
the application. This includes all databases, packet data etc."""
        )
    if not prompt_yes_no():
        msg = "Not continuing"
        raise Exception(msg)


def prompt_yes_no(get_input=input):
    return get_input("\nContinue? [yes/no] ") == "yes"


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
        self.version = args["--version"]

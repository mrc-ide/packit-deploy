import os
from pathlib import Path

import click

from packit_deploy.config import PackitConfig
from packit_deploy.packit_constellation import PackitConstellation

_HELP_NAME = "Override the configured instance, use with care!"


@click.group()
@click.version_option()
def cli():
    pass


@cli.command("configure")
@click.argument("name")
def cli_configure(name):
    prev = _read_identity(required=False)
    if prev:
        if prev != name:
            msg = (
                f"This packit instance is already configured as '{prev}', "
                f"but you are trying to reconfigure it as '{name}'. "
                "If you really want to do do this, then delete the file "
                f"'{IDENTITY_FILE}' from this directory and try again"
            )
            raise Exception(msg)
        else:
            print(f"Packit already configured as '{name}'")
    else:
        # Check that we can read the configuration before saving it.
        PackitConfig(name)
        with IDENTITY_FILE.open("w") as f:
            f.write(name)
        print(f"Configured packit as '{name}'")


@cli.command("unconfigure")
def cli_unconfigure():
    prev = _read_identity(required=False)
    if prev:
        print(f"Unconfigured packit (was '{prev}')")
        os.unlink(IDENTITY_FILE)
    else:
        print("Packit is not configured")


@cli.command("start")
@click.option("--pull", is_flag=True, help="Pull images before start")
@click.option("--name", type=str, help=_HELP_NAME)
def cli_start(*, pull, name, options=None):
    _constellation(name, options=options).start(pull_images=pull)


@cli.command("status")
@click.option("--name", type=str, help=_HELP_NAME)
def cli_status(name):
    name = _read_identity(name)
    print(f"Configured as '{name}'")
    _constellation(name).status()


@cli.command("stop")
@click.option("--kill", is_flag=True, help="Kill containers, don't wait for a clean exit")
@click.option("--network", is_flag=True, help="Remove the docker network")
@click.option("--volumes", is_flag=True, help="Remove the docker volumes, causing permanent data loss")
@click.option("--name", type=str, help=_HELP_NAME)
def cli_stop(*, name, kill, network, volumes):
    obj = _constellation(name)
    if volumes:
        _verify_data_loss(obj.cfg.protect_data)
    obj.stop(kill=kill, remove_network=network, remove_volumes=volumes)


def _verify_data_loss(protect_data):
    if protect_data:
        err = "Cannot remove volumes with this configuration"
        raise Exception(err)
    else:
        print(
            """WARNING! PROBABLE IRREVERSIBLE DATA LOSS!
You are about to delete the data volumes. This action cannot be undone
and will result in the irreversible loss of *all* data associated with
the application. This includes all databases, packet data etc."""
        )
    if not _prompt_yes_no():
        msg = "Not continuing"
        raise Exception(msg)


def _prompt_yes_no(get_input=input):
    return get_input("\nContinue? [yes/no] ") == "yes"


IDENTITY_FILE = Path(".packit_identity")


def _read_identity(name=None, *, required=True):
    if name:
        return name
    if IDENTITY_FILE.exists():
        with IDENTITY_FILE.open() as f:
            return f.read().strip()
    if required:
        msg = "Packit identity is not yet configured; run 'packit configure <name>' first"
        raise Exception(msg)
    return None


def _constellation(name=None, options=None) -> PackitConstellation:
    name = _read_identity(name)
    cfg = PackitConfig(name, options=options)
    return PackitConstellation(cfg)

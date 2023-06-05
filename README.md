# Packit Deploy

[![PyPI - Version](https://img.shields.io/pypi/v/packit-deploy.svg)](https://pypi.org/project/packit-deploy)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/packit-deploy.svg)](https://pypi.org/project/packit-deploy)

-----

This is the command line tool for deploying Packit.

## Install from PyPi

```console
pip install packit-deploy
```

## Usage

So far the only commands are `start`, `stop` and `status`. Admin commands for managing users 
and permissions will be added in due course.

```
$ packit --help
Usage:
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
```

Here `<path>` is the path to a directory that contains a configuration file `packit.yml`.

## Dev requirements

1. [Python3](https://www.python.org/downloads/) (>= 3.7)
2. [Hatch](https://hatch.pypa.io/latest/install/)

## Test and lint

1. `hatch run test`
2. `hatch run lint:fmt`

## Build

```console
hatch build
```

## Install from local sources

1. `hatch build`
2. `pip install dist/packit_deploy-{version}.tar.gz`

## Publish to PyPi

Ensure you have built a new version of the package:
1. `hatch clean`
2. `hatch build`

Then publish to the test server:

```console
hatch publish -r test
```

You will be prompted to enter your [test.pypi.org](https://test.pypi.org/legacy/) username and password.
To test the installation, first run Python in a container:

```
docker run --rm -it --entrypoint bash python
```

Then:

```
pip install --index-url https://test.pypi.org/simple packit-deploy --extra-index-url https://pypi.org/simple
```

Now you should be able to run `packit` from the command line and see the usage instructions.

If it is working, you can publish to the real PyPi:

```console
hatch publish
```

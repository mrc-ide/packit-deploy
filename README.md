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

## Test

1. `hatch run test`

To get coverage reported locally in the console, use `hatch run cov`. 
On CI, use `hatch run cov-ci` to generate an xml report.

## Lint and format

1. `hatch run lint:fmt`

## Build

```console
hatch build
```

## Publishing to PyPI

Automatically publish to [PyPI](https://pypi.org/project/packit-deploy).  Assuming a version number `0.1.2`:

* Create a [release on github](https://github.com/reside-ic/packit-deploy/releases/new)
* Choose a tag -> Create a new tag: `v0.1.2`
* Use this version as the description
* Optionally describe the release
* Click "Publish release"
* This triggers the release workflow and the package will be available on PyPI in a few minutes

Settings are configured [here on PyPI](https://pypi.org/manage/project/packit-deploy/settings/publishing)

## Install from local sources

You should not need to do this very often, but if you really want to:

1. `hatch build`
2. `pip install dist/packit_deploy-{version}.tar.gz`

## Example configurations

The following example configurations are included under `/config`:

- `novault`: does not use any vault values, but does include proxy (using self-signed cert) and demo data
- `complete`: example of vault secrets required for a full configuration
- `githubauth`: example with github auth enabled, includes proxy (using self-signed cert) and demo data
- `basicauth`: example with basic auth enabled, includes proxy (using self-signed cert) and demo data
- `basicauthcustombrand`: same as basicauth, but with custom front-end branding.
- `nodemo`: does not include the demo data
- `noproxy`: does not include proxy container

## Running locally

You can bring up most of the configurations above for local testing (except for `complete` which includes non-existant vault secrets and `noproxy` which will not actually expose anything to interact with).  You will need access to the vault to run the `githubauth` configuration, which requires secrets for the github oauth2 client app
details.

For example, to bring up the `basicauth` configuration, you can run:

```console
hatch env run -- packit start --pull config/basicauth
./scripts/create-super-user
```

The `--` allows `--pull` to make it through to the deploy (and not be swallowed by `hatch`).  Alternatively you can run `packit start --pull config/basicauth` after running `hatch shell`.  The `create-super-user` script sets up a user that you can log in with via basic auth and prints the login details to stdout.  After this, packit will be running at `https://localhost` though with a self-signed certificate so you will need to tell your browser that it's ok to connect.

To bring things down, run

```console
hatch env run -- packit stop --kill config/basicauth
```

If you need to see what lurks in the database, connect with

```console
docker exec -it packit-packit-db psql -U packituser -d packit
```

If you have anything else running on port 80 or 443, nothing will work as expected; either stop that service or change the proxy port in the configuration that you are using.

### Custom branding config

Custom branding is disabled unless both a logo and brand name are configured, since we don't want to display an incorrect combination of brand name and logo/favicon.

#### Logo (required)

The logo file is bind-mounted into the front-end container, in a public folder, and the packit api has an env var set for the filename of the logo, so that it can tell the front end where to look for the file. Your logo file should be in the same directory as the config file.

#### Logo alt text (optional)

This is set as an env var in the packit api, which passes it on to the front end.

#### Logo link (optional)

This is to allow a configurable link destination for when the user clicks the logo. In VIMC's case this would be a link back to Montagu. This is set as an env var in the packit api, which passes it on to the front end.

#### Brand name (required)

The 'brand name' (e.g. 'Reporting Portal') is used in two ways: firstly an env var is set in the packit api, which can be sent on the front-end. Secondly, it's used to directly overwrite part of the front end's public index.html file, replacing any pre-existing title tag.

#### Favicon (optional)

The favicon file is bind-mounted into the front-end container, in a public folder. Then we overwrite part of the front end's public index.html file, replacing any pre-existing reference to 'favicon.ico' with the filename of the configured favicon. Your favicon file should be in the same directory as the config file.

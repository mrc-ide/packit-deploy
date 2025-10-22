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

So far the commands are `configure`, `unconfigure`, `start`, `stop` and `status`.

```
$ packit --help
Usage: packit [OPTIONS] COMMAND [ARGS]...

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  configure
  start
  status
  stop
  unconfigure
```

Help for sub commands is available via, for example, `packit start --help`, but most have few options.

First, configure an instance with

```
packit configure <path>
```

where `<path>` is the path to a directory that contains a configuration file `packit.yml`.  After that, `packit start`, `packit stop` and `packit status` operate on that instance.

## Dev requirements

1. [Python3](https://www.python.org/downloads/) (>= 3.9)
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

* Create a [release on github](https://github.com/mrc-ide/packit-deploy/releases/new)
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

First, you need to [be logged into GitHub Container Registry]([url](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic)) using a GitHub personal access token (PAT) that has the `read:packages` permission.

You can bring up most of the configurations above for local testing (except for `complete` which includes non-existant vault secrets and `noproxy` which will not actually expose anything to interact with). You will need access to the vault to run the `githubauth` configuration, which requires secrets for the github oauth2 client app details.

For example, to bring up the `basicauth` configuration, you can run:

```console
hatch env run -- packit configure config/basicauth
hatch env run -- packit start --pull
./scripts/create-super-user
```

The `--` allows `--pull` to make it through to the deploy (and not be swallowed by `hatch`).  Alternatively you can run these commands without the `hatch env run --` part after running `hatch shell`.  The `create-super-user` script sets up a user that you can log in with via basic auth and prints the login details to stdout.  After this, packit will be running at `https://localhost` though with a self-signed certificate so you will need to tell your browser that it's ok to connect.

To bring things down, run

```console
hatch env run -- packit stop --kill
```

If you need to see what lurks in the database, connect with

```console
docker exec -it packit-packit-db psql -U packituser -d packit
```

If you have anything else running on port 80 or 443, nothing will work as expected; either stop that service or change the proxy port in the configuration that you are using.

Delete the file `.packit_identity` once you're done.  This is manual because it should not be easy in deployments!

## Custom branding configuration

For each custom branding setting's corresponding yml value, see the example 'brand' dictionaries in basicauthcustombrand/packit.yml or complete/packit.yml. All settings are optional.

### Logo

The logo file is bind-mounted into the front-end container, in a public folder, and the packit api has an env var set for the filename of the logo, so that it can tell the front end where to look for the file. Your logo file should be in the same directory as the config file. With regards to size/dimensions, the logo will be constrained to the height of the header, and the proportions between height and width are maintained.

### Logo alt text

This is set as an env var in the packit api, which passes it on to the front end.

### Logo link

This is to allow a configurable link destination for when the user clicks the logo. In VIMC's case this would be a link back to Montagu. This is set as an env var in the packit api, which passes it on to the front end.

### Brand name / title text

The 'brand name' (e.g. 'Reporting Portal') is used to directly overwrite part of the front end's public index.html file, replacing any pre-existing title tag. (The front-end reads this from the index.html in order to re-use the name elsewhere.)

### Favicon

The favicon file is bind-mounted into the front-end container, in a public folder. Then we overwrite part of the front end's public index.html file, replacing any pre-existing reference to 'favicon.ico' with the filename of the configured favicon. Your favicon file should be in the same directory as the config file.

### Brand colours

The brand colours are written as css variables into the public custom.css file, which override default variables in the front-end.

If the yml config provides no colours for the dark theme, dark mode will be disabled. If no colours are provided for the light theme, light mode will be disabled. If no colours are provided for either theme, then both modes will be enabled, using default colours.

When choosing colours, consider contrast carefully, as described below. Do not rely solely on hue for contrast as this will create problems for users with certain types of colour blindness.

The configurable colours are:

* Accent-colour. This may be used as the background for buttons or borders, and is expected to contrast in lightness with white (the background colour of the app in light mode), and with the accent-foreground colour (next bullet point). As such it should be middlingly dark or darker.
* Accent-foreground. This will be used as the text colour for anything whose background is the accent-colour, and as such is expected to contrast in lightness with the accent-colour (so it should be rather light, or simply white).
* Dark accent-colour. If configured, this plays the role of the accent-colour as above when the app is used in dark mode. As such it is expected to contrast in lightness with black (the background colour of the app in dark mode) and with the dark accent-foreground colour. It should thus be somewhat lighter than black.
* Dark accent-foreground. If configured, this plays the role of the accent-foreground as above when the app is used in dark mode. As such it should contrast in lightness with the dark accent-colour.

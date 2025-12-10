import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional, Union

import constellation
from constellation import BuildSpec, config
from constellation.acme import AcmeBuddyConfig
from constellation.vault import VaultConfig


def config_path(dat, key: list[str], *, root: str, is_optional: bool = False) -> Optional[Path]:
    """
    Parse the path to an external asset.

    The path in the configuration is interpreted to be relative to the given
    root. The returned path is always absolute.
    """
    value = config.config_string(dat, key, is_optional=is_optional)
    if value is not None:
        return Path(root, value).resolve()
    else:
        return None


def config_ref(dat, key: list[str], *, repo: str) -> constellation.ImageReference:
    """
    Parse an image reference.

    The reference should be a dictionary with at least two entries, `name` and
    `tag`.
    """
    name = config.config_string(dat, [*key, "name"])
    tag = config.config_string(dat, [*key, "tag"])
    return constellation.ImageReference(repo, name, tag)


def config_buildable(dat, key: list[str], *, repo: str, root: str) -> Union["BuildSpec", constellation.ImageReference]:
    build = config_path(dat, [*key, "build"], is_optional=True, root=root)
    if build is not None:
        return BuildSpec(path=str(build))
    else:
        name = config.config_string(dat, [*key, "name"])
        tag = config.config_string(dat, [*key, "tag"])
        return constellation.ImageReference(repo, name, tag)


APP_HTML_ROOT = "/usr/share/nginx/html"  # from Packit app Dockerfile


@dataclass
class Context:
    root: str
    repo: str
    instance: Optional[str]

    def container_name(self, name: str) -> str:
        if self.instance is None:
            return name
        else:
            return f"{self.instance}-{name}"

    def volume_id(self, name: str) -> str:
        if self.instance is None:
            return name
        else:
            return f"{self.instance}/{name}"


@dataclass
class Theme:
    accent: str
    foreground: str

    @classmethod
    def from_data(cls, dat, key: list[str]) -> Optional["Theme"]:
        theme = config.config_dict(dat, key, is_optional=True)
        if theme is not None:
            return Theme(theme["accent"], theme["accent_foreground"])
        else:
            return None


@dataclass
class Branding:
    name: Optional[str]
    logo: Optional[Path]
    logo_link: Optional[str]
    logo_alt_text: Optional[str]
    favicon: Optional[Path]
    theme_light: Optional[Theme]
    theme_dark: Optional[Theme]

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "Branding":
        name = config.config_string(dat, [*key, "name"], is_optional=True)
        logo = config_path(dat, [*key, "logo_path"], root=ctx.root, is_optional=True)
        logo_link = config.config_string(dat, [*key, "logo_link"], is_optional=True)
        logo_alt_text = config.config_string(dat, [*key, "logo_alt_text"], is_optional=True)
        if logo_alt_text is None and name is not None:
            logo_alt_text = f"{name} logo"
        favicon = config_path(dat, [*key, "favicon_path"], root=ctx.root, is_optional=True)

        theme_light = Theme.from_data(dat, [*key, "css", "light"])
        theme_dark = Theme.from_data(dat, [*key, "css", "dark"])

        return Branding(
            name=name,
            logo=logo,
            logo_link=logo_link,
            logo_alt_text=logo_alt_text,
            favicon=favicon,
            theme_light=theme_light,
            theme_dark=theme_dark,
        )

    @property
    def light_mode_enabled(self) -> bool:
        if self.theme_light is None and self.theme_dark is None:
            return True
        else:
            return self.theme_light is not None

    @property
    def dark_mode_enabled(self) -> bool:
        if self.theme_light is None and self.theme_dark is None:
            return True
        else:
            return self.theme_dark is not None


@dataclass
class PackitAuthGithub:
    org: str
    team: str
    client_id: str
    client_secret: str
    oauth2_redirect_packit_api_root: str
    oauth2_redirect_url: str

    @classmethod
    def from_data(cls, dat, key: list[str]) -> "PackitAuthGithub":
        org = config.config_string(dat, [*key, "github_api_org"])
        team = config.config_string(dat, [*key, "github_api_team"])
        client_id = config.config_string(dat, [*key, "github_client", "id"])
        client_secret = config.config_string(dat, [*key, "github_client", "secret"])
        oauth2_redirect_packit_api_root = config.config_string(dat, [*key, "oauth2", "redirect", "packit_api_root"])
        oauth2_redirect_url = config.config_string(dat, [*key, "oauth2", "redirect", "url"])
        return PackitAuthGithub(
            org=org,
            team=team,
            client_id=client_id,
            client_secret=client_secret,
            oauth2_redirect_packit_api_root=oauth2_redirect_packit_api_root,
            oauth2_redirect_url=oauth2_redirect_url,
        )


@dataclass
class PackitAuth:
    VALID_AUTH_METHODS = frozenset(("github", "basic", "preauth"))

    method: str
    github: Optional[PackitAuthGithub]
    expiry_days: int
    jwt_secret: str

    @classmethod
    def from_data(cls, dat, key: list[str]) -> "PackitAuth":
        method = config.config_enum(dat, [*key, "auth_method"], PackitAuth.VALID_AUTH_METHODS)
        if method == "github":
            github = PackitAuthGithub.from_data(dat, key)
        else:
            github = None
        expiry_days = config.config_integer(dat, [*key, "expiry_days"])
        jwt_secret = config.config_string(dat, [*key, "jwt", "secret"])
        return PackitAuth(method=method, github=github, expiry_days=expiry_days, jwt_secret=jwt_secret)


@dataclass
class ContainerConfig:
    """
    A generic config class for containers that don't need allow any
    configuration options other than an image reference.
    """

    container_name: str
    image: constellation.ImageReference

    @classmethod
    def from_data(cls, dat, key: list[str], *, container_name: str, ctx: Context) -> "ContainerConfig":
        return ContainerConfig(
            container_name=ctx.container_name(container_name),
            image=config_ref(dat, key, repo=ctx.repo),
        )


@dataclass
class PackitAPI:
    container_name: str
    image: constellation.ImageReference
    # port at which api provides health metrics, separately proxied by montagu API - different from Proxy port_metrics!
    management_port: int
    base_url: str
    cors_allowed_origins: str
    auth: Optional[PackitAuth]
    runner_git_url: Optional[str]
    runner_git_ssh_key: Optional[str]
    default_roles: str

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "PackitAPI":
        image = config_ref(dat, [*key, "api"], repo=ctx.repo)
        management_port = config.config_integer(dat, [*key, "api", "management_port"], is_optional=True, default=8081)
        base_url = config.config_string(dat, [*key, "base_url"])
        default_roles = config.config_string(dat, [*key, "default_roles"], is_optional=True, default="")

        cors_allowed_origins = config.config_string(
            dat,
            [*key, "cors_allowed_origins"],
            is_optional=True,
            default="http://localhost*,https://localhost*",
        )

        if config.config_boolean(dat, [*key, "auth", "enabled"], is_optional=True, default=False):
            auth = PackitAuth.from_data(dat, [*key, "auth"])
        else:
            auth = None

        runner_git_url = config.config_string(dat, [*key, "runner", "git", "url"], is_optional=True)
        runner_git_ssh_key = config.config_string(dat, [*key, "runner", "git", "ssh-key"], is_optional=True)
        return PackitAPI(
            container_name=ctx.container_name("packit-api"),
            image=image,
            management_port=management_port,
            base_url=base_url,
            cors_allowed_origins=cors_allowed_origins,
            auth=auth,
            runner_git_url=runner_git_url,
            runner_git_ssh_key=runner_git_ssh_key,
            default_roles=default_roles,
        )


@dataclass
class PackitDB:
    container_name: str
    image: constellation.ImageReference
    user: str
    password: str

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "PackitDB":
        image = config_ref(dat, key, repo=ctx.repo)
        user = config.config_string(dat, [*key, "user"])
        password = config.config_string(dat, [*key, "password"])
        return PackitDB(
            container_name=ctx.container_name("packit-db"),
            image=image,
            user=user,
            password=password,
        )

    @property
    def jdbc_url(self):
        return f"jdbc:postgresql://{self.container_name}:5432/packit?stringtype=unspecified"


@dataclass
class OrderlyRunner:
    redis: ContainerConfig
    api: ContainerConfig
    worker: ContainerConfig

    worker_count: int
    env: dict[str, str]

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "OrderlyRunner":
        image = config_ref(dat, [*key, "image"], repo=ctx.repo)
        worker_count = config.config_integer(dat, ["orderly-runner", "workers"])
        env = config.config_dict(dat, ["orderly-runner", "env"], is_optional=True, default={})

        redis_image = constellation.ImageReference("library", "redis", "8.0")
        return OrderlyRunner(
            redis=ContainerConfig(ctx.container_name("redis"), redis_image),
            api=ContainerConfig(ctx.container_name("orderly-runner-api"), image),
            worker=ContainerConfig(ctx.container_name("orderly-runner-worker"), image),
            worker_count=worker_count,
            env=env,
        )

    @property
    def api_url(self) -> str:
        return f"http://{self.api.container_name}:8001"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis.container_name}:6379"


@dataclass
class SSL:
    certificate: str
    key: str


@dataclass
class Proxy:
    container_name: ClassVar[str] = "proxy"

    image: Union[BuildSpec, constellation.ImageReference]
    hostname: str
    port_http: int
    port_https: int
    # port at which proxy will provide api and outpack server metrics. Different from PackitAPI management_port!
    port_metrics: Optional[int]

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "Proxy":
        image = config_buildable(dat, [*key, "image"], repo=ctx.repo, root=ctx.root)
        hostname = config.config_string(dat, [*key, "hostname"])
        port_http = config.config_integer(dat, [*key, "port_http"])
        port_https = config.config_integer(dat, [*key, "port_https"])
        port_metrics = config.config_integer(dat, [*key, "port_metrics"], is_optional=True)

        return Proxy(
            image=image,
            hostname=hostname,
            port_http=port_http,
            port_https=port_https,
            port_metrics=port_metrics,
        )


@dataclass
class PackitInstance:
    outpack_server: ContainerConfig
    packit_app: ContainerConfig
    packit_api: PackitAPI
    packit_db: PackitDB
    brand: Branding

    # The handling of volumes in Constellation is a bit rigid and weird.
    # - Every volume has an ID that is (generally) a constant.
    # - We need to give Constellation a map from volume ID to volume name,
    #   based on the user provided configuration.
    # - When configuring containers we need to pass in the volume ID, not the
    #   volume name.
    #
    # This is a bit inconvenient for running multiple instances of Packit,
    # where we can't have a finite set of constant volume IDs. These need
    # to be generated from the instance name and recorded in the fields below.
    volume_id_outpack: str
    volume_id_packit_db: str

    # packit_db_backup is not really needed for much. It was mostly used as
    # scratch space for maintenance operations.
    volume_id_packit_db_backup: Optional[str]

    # This is the map from volume ID to volume name, for instance-specific
    # volumes. It gets merged with other instances later.
    volumes: dict[str, str]

    @classmethod
    def from_data(cls, dat, key: list[str], *, ctx: Context) -> "PackitInstance":
        outpack_server = ContainerConfig.from_data(
            dat,
            [*key, "outpack", "server"],
            container_name="outpack-server",
            ctx=ctx,
        )
        packit_app = ContainerConfig.from_data(dat, [*key, "packit", "app"], container_name="packit", ctx=ctx)
        packit_api = PackitAPI.from_data(dat, [*key, "packit"], ctx=ctx)
        packit_db = PackitDB.from_data(dat, [*key, "packit", "db"], ctx=ctx)
        brand = Branding.from_data(dat, [*key, "brand"], ctx=ctx)

        volume_id_outpack = ctx.volume_id("outpack")
        volume_id_packit_db = ctx.volume_id("packit_db")

        volumes = {
            volume_id_outpack: config.config_string(dat, [*key, "volumes", "outpack"]),
            volume_id_packit_db: config.config_string(dat, [*key, "volumes", "packit_db"]),
        }

        volume = config.config_string(dat, [*key, "volumes", "packit_db_backup"], is_optional=True)
        if volume is not None:
            volume_id_packit_db_backup = ctx.volume_id("packit_db_backup")
            volumes[volume_id_packit_db_backup] = volume
        else:
            volume_id_packit_db_backup = None

        return PackitInstance(
            outpack_server=outpack_server,
            packit_app=packit_app,
            packit_api=packit_api,
            packit_db=packit_db,
            brand=brand,
            volume_id_outpack=volume_id_outpack,
            volume_id_packit_db=volume_id_packit_db,
            volume_id_packit_db_backup=volume_id_packit_db_backup,
            volumes=volumes,
        )

    @property
    def outpack_server_url(self) -> str:
        return f"http://{self.outpack_server.container_name}:8000"

    @property
    def packit_app_url(self) -> str:
        return f"http://{self.packit_app.container_name}:80"

    @property
    def packit_api_url(self) -> str:
        return f"http://{self.packit_api.container_name}:8080"

    @property
    def packit_api_management_url(self) -> str:
        return f"http://{self.packit_api.container_name}:{self.packit_api.management_port}"


class PackitConfig:
    # Maps internal volume names to user configured names
    # In cases where multiple instances are used, the internal names look like
    # `name/outpack` (See Context.volume_id).
    volumes: dict[str, str]

    container_prefix: str
    network: str
    protect_data: bool
    vault: VaultConfig

    orderly_runner: Optional[OrderlyRunner]
    proxy: Optional[Proxy]
    acme_config: Optional[AcmeBuddyConfig]

    # The map of instances we host, with the same as the key.
    # In cases where a single unnamed instance is hosted, the key is None.
    instances: dict[Optional[str], PackitInstance]

    def __init__(self, path, extra=None, options=None) -> None:
        dat = config.read_yaml(f"{path}/packit.yml")
        dat = config.config_build(path, dat, extra, options)
        self.vault = config.config_vault(dat, ["vault"])
        self.network = config.config_string(dat, ["network"])
        self.protect_data = config.config_boolean(dat, ["protect_data"])

        self.container_prefix = config.config_string(dat, ["container_prefix"])

        self.volumes = {}

        repo = config.config_string(dat, ["repo"])
        ctx = Context(repo=repo, root=path, instance=None)

        if "orderly-runner" in dat:
            self.orderly_runner = OrderlyRunner.from_data(dat, ["orderly-runner"], ctx=ctx)
            self.volumes["orderly_library"] = config.config_string(dat, ["volumes", "orderly_library"])
            self.volumes["orderly_logs"] = config.config_string(dat, ["volumes", "orderly_logs"])
        else:
            self.orderly_runner = None

        if "proxy" in dat and config.config_boolean(dat, ["proxy", "enabled"]):
            self.proxy = Proxy.from_data(dat, ["proxy"], ctx=ctx)
            self.volumes["proxy_logs"] = config.config_string(dat, ["volumes", "proxy_logs"])
        else:
            self.proxy = None

        if "acme_buddy" in dat:
            self.acme_config = config.config_acme(dat, "acme_buddy")
            self.volumes["packit-tls"] = "packit-tls"
        else:
            self.acme_config = None

        instances = config.config_dict(dat, ["instances"], is_optional=True)
        if instances is not None:
            self.instances = {
                name: PackitInstance.from_data(
                    dat,
                    ["instances", name],
                    ctx=dataclasses.replace(ctx, instance=name),
                )
                for name in instances.keys()
            }
        else:
            self.instances = {
                None: PackitInstance.from_data(dat, [], ctx=ctx),
            }

        for instance in self.instances.values():
            self.volumes.update(instance.volumes)

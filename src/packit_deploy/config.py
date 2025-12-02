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
    def from_data(cls, dat, *, root: str) -> "Branding":
        name = config.config_string(dat, ["brand", "name"], is_optional=True)
        logo = config_path(dat, ["brand", "logo_path"], root=root, is_optional=True)
        logo_link = config.config_string(dat, ["brand", "logo_link"], is_optional=True)
        logo_alt_text = config.config_string(dat, ["brand", "logo_alt_text"], is_optional=True)
        if logo_alt_text is None and name is not None:
            logo_alt_text = f"{name} logo"
        favicon = config_path(dat, ["brand", "favicon_path"], root=root, is_optional=True)

        theme_light = Theme.from_data(dat, ["brand", "css", "light"])
        theme_dark = Theme.from_data(dat, ["brand", "css", "dark"])

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
    A generic config class for containers that don't support any customization.
    """

    container_name: str
    image: constellation.ImageReference

    @classmethod
    def from_data(cls, dat, key: list[str], *, repo: str, name: str) -> "ContainerConfig":
        return ContainerConfig(
            container_name=name,
            image=config_ref(dat, key, repo=repo),
        )


@dataclass
class PackitAPI:
    container_name: ClassVar[str] = "packit-api"

    image: constellation.ImageReference
    management_port: int
    base_url: str
    cors_allowed_origins: str
    auth: Optional[PackitAuth]
    runner_git_url: Optional[str]
    runner_git_ssh_key: Optional[str]

    @classmethod
    def from_data(cls, dat, key: list[str], *, repo: str) -> "PackitAPI":
        image = config_ref(dat, [*key, "api"], repo=repo)
        management_port = config.config_integer(dat, [*key, "api", "management_port"], is_optional=True, default=8081)
        base_url = config.config_string(dat, [*key, "base_url"])

        cors_allowed_origins = config.config_string(
            dat,
            [*key, "cors_allowed_origins"],
            is_optional=True,
            default="http://localhost*,https://localhost*",
        )

        if "auth" in dat["packit"] and config.config_boolean(dat, ["packit", "auth", "enabled"]):
            auth = PackitAuth.from_data(dat, ["packit", "auth"])
        else:
            auth = None

        runner_git_url = config.config_string(dat, [*key, "runner", "git", "url"], is_optional=True)
        runner_git_ssh_key = config.config_string(dat, [*key, "runner", "git", "ssh-key"], is_optional=True)
        return PackitAPI(
            image=image,
            management_port=management_port,
            base_url=base_url,
            cors_allowed_origins=cors_allowed_origins,
            auth=auth,
            runner_git_url=runner_git_url,
            runner_git_ssh_key=runner_git_ssh_key,
        )


@dataclass
class PackitDB:
    container_name: ClassVar[str] = "packit-db"
    image: constellation.ImageReference
    user: str
    password: str

    @classmethod
    def from_data(cls, dat, key: list[str], *, repo: str) -> "PackitDB":
        image = config_ref(dat, key, repo=repo)
        user = config.config_string(dat, [*key, "user"])
        password = config.config_string(dat, [*key, "password"])
        return PackitDB(image=image, user=user, password=password)

    @property
    def jdbc_url(self):
        return f"jdbc:postgresql://{self.container_name}:5432/packit?stringtype=unspecified"


@dataclass
class OrderlyRunner:
    container_name_api: ClassVar[str] = "orderly-runner-api"
    container_name_worker: ClassVar[str] = "orderly-runner-worker"

    image: constellation.ImageReference
    workers: int
    env: dict[str, str]

    @classmethod
    def from_data(cls, dat, key: list[str], *, repo: str) -> "OrderlyRunner":
        image = config_ref(dat, [*key, "image"], repo=repo)
        workers = config.config_integer(dat, ["orderly-runner", "workers"])
        env = config.config_dict(dat, ["orderly-runner", "env"], is_optional=True, default={})
        return OrderlyRunner(image=image, workers=workers, env=env)

    @property
    def api_url(self) -> str:
        return f"http://{self.container_name_api}:8001"


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

    @classmethod
    def from_data(cls, dat, key: list[str], *, repo: str, root: str) -> "Proxy":
        image = config_buildable(dat, [*key, "image"], repo=repo, root=root)
        hostname = config.config_string(dat, [*key, "hostname"])
        port_http = config.config_integer(dat, [*key, "port_http"])
        port_https = config.config_integer(dat, [*key, "port_https"])

        return Proxy(image=image, hostname=hostname, port_http=port_http, port_https=port_https)


class PackitConfig:
    app_html_root = "/usr/share/nginx/html"  # from Packit app Dockerfile

    volumes: dict[str, str]

    container_prefix: str
    network: str
    protect_data: bool
    repo: str
    vault: VaultConfig

    outpack: ContainerConfig
    packit_app: ContainerConfig
    packit_api: PackitAPI
    packit_db: PackitDB
    orderly_runner: Optional[OrderlyRunner]
    proxy: Optional[Proxy]
    acme_config: Optional[AcmeBuddyConfig]

    brand: Branding

    def __init__(self, path, extra=None, options=None) -> None:
        dat = config.read_yaml(f"{path}/packit.yml")
        dat = config.config_build(path, dat, extra, options)
        self.vault = config.config_vault(dat, ["vault"])
        self.network = config.config_string(dat, ["network"])
        self.protect_data = config.config_boolean(dat, ["protect_data"])
        self.volumes = {
            "outpack": config.config_string(dat, ["volumes", "outpack"]),
            "packit_db": config.config_string(dat, ["volumes", "packit_db"]),
            "packit_db_backup": config.config_string(dat, ["volumes", "packit_db_backup"]),
        }

        self.container_prefix = config.config_string(dat, ["container_prefix"])
        self.repo = config.config_string(dat, ["repo"])

        self.outpack_server = ContainerConfig.from_data(
            dat, ["outpack", "server"], repo=self.repo, name="outpack-server"
        )
        self.packit_app = ContainerConfig.from_data(dat, ["packit", "app"], repo=self.repo, name="packit")
        self.packit_api = PackitAPI.from_data(dat, ["packit"], repo=self.repo)
        self.packit_db = PackitDB.from_data(dat, ["packit", "db"], repo=self.repo)

        if "orderly-runner" in dat:
            self.orderly_runner = OrderlyRunner.from_data(dat, ["orderly-runner"], repo=self.repo)
            self.volumes["orderly_library"] = config.config_string(dat, ["volumes", "orderly_library"])
            self.volumes["orderly_logs"] = config.config_string(dat, ["volumes", "orderly_logs"])
        else:
            self.orderly_runner = None

        self.brand = Branding.from_data(dat, root=path)

        if "proxy" in dat and config.config_boolean(dat, ["proxy", "enabled"]):
            self.proxy = Proxy.from_data(dat, ["proxy"], repo=self.repo, root=path)
            self.volumes["proxy_logs"] = config.config_string(dat, ["volumes", "proxy_logs"])
        else:
            self.proxy = None

        if "acme_buddy" in dat:
            self.acme_config = config.config_acme(dat, "acme_buddy")
            self.volumes["packit-tls"] = "packit-tls"
        else:
            self.acme_config = None

    @property
    def outpack_server_url(self) -> str:
        return f"http://{self.outpack_server.container_name}:8000"

    @property
    def redis_url(self) -> str:
        return "redis://redis:6379"

    @property
    def redis(self) -> ContainerConfig:
        return ContainerConfig(
            container_name="redis",
            image=constellation.ImageReference("library", "redis", "8.0"),
        )

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import constellation
from constellation import config

from packit_deploy.docker_helpers import DockerClient


def config_path(dat, key: list[str], *, root: str, is_optional: bool = False) -> Optional[Path]:
    """
    Parse the path to an external asset.

    The path is the configuration is interpreted to be relative to the given
    root. The returned path is always absolute.
    """
    value = config.config_string(dat, key, is_optional=is_optional)
    if value is not None:
        return Path(root, value).absolute()
    else:
        return None


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


class PackitConfig:
    app_html_root = "/usr/share/nginx/html"  # from Packit app Dockerfile

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

        self.outpack_ref = self.build_ref(dat, "outpack", "server", self.repo)
        self.packit_api_ref = self.build_ref(dat, "packit", "api")
        self.packit_api_management_port = config.config_integer(
            dat, ["packit", "api", "management_port"], is_optional=True, default=8081
        )
        self.packit_ref = self.build_ref(dat, "packit", "app")
        self.packit_db_ref = self.build_ref(dat, "packit", "db")
        self.packit_db_user = config.config_string(dat, ["packit", "db", "user"])
        self.packit_db_password = config.config_string(dat, ["packit", "db", "password"])
        self.packit_base_url = config.config_string(dat, ["packit", "base_url"])

        default_cors_allowed = "http://localhost*,https://localhost*"
        self.packit_cors_allowed_origins = config.config_string(
            dat, ["packit", "cors_allowed_origins"], is_optional=True, default=default_cors_allowed
        )

        if "auth" in dat["packit"]:
            valid_auth_methods = {"github", "basic", "preauth"}
            self.packit_auth_enabled = config.config_boolean(dat, ["packit", "auth", "enabled"])
            self.packit_auth_method = config.config_enum(dat, ["packit", "auth", "auth_method"], valid_auth_methods)
            self.packit_auth_expiry_days = config.config_integer(dat, ["packit", "auth", "expiry_days"])
            self.packit_auth_jwt_secret = config.config_string(dat, ["packit", "auth", "jwt", "secret"])
            if self.packit_auth_method == "github":
                self.packit_auth_github_api_org = config.config_string(dat, ["packit", "auth", "github_api_org"])
                self.packit_auth_github_api_team = config.config_string(dat, ["packit", "auth", "github_api_team"])
                self.packit_auth_github_client_id = config.config_string(dat, ["packit", "auth", "github_client", "id"])
                self.packit_auth_github_client_secret = config.config_string(
                    dat, ["packit", "auth", "github_client", "secret"]
                )
                self.packit_auth_oauth2_redirect_packit_api_root = config.config_string(
                    dat, ["packit", "auth", "oauth2", "redirect", "packit_api_root"]
                )
                self.packit_auth_oauth2_redirect_url = config.config_string(
                    dat, ["packit", "auth", "oauth2", "redirect", "url"]
                )
        else:
            self.packit_auth_enabled = False

        self.packit_runner_git_url = config.config_string(dat, ["packit", "runner", "git", "url"], is_optional=True)
        self.packit_runner_git_ssh_key = config.config_string(
            dat, ["packit", "runner", "git", "ssh-key"], is_optional=True
        )

        self.containers = {
            "outpack-server": "outpack-server",
            "packit-db": "packit-db",
            "packit-api": "packit-api",
            "packit": "packit",
        }

        self.images = {
            "outpack-server": self.outpack_ref,
            "packit-db": self.packit_db_ref,
            "packit-api": self.packit_api_ref,
            "packit": self.packit_ref,
        }

        self.orderly_runner_enabled = "orderly-runner" in dat
        if self.orderly_runner_enabled:
            self.orderly_runner_ref = self.build_ref(dat, "orderly-runner", "image", self.repo)
            self.orderly_runner_workers = config.config_integer(dat, ["orderly-runner", "workers"])
            self.orderly_runner_api_url = f"http://{self.container_prefix}-orderly-runner-api:8001"
            self.orderly_runner_env = config.config_dict(dat, ["orderly-runner", "env"], is_optional=True, default={})

            self.orderly_runner_workers = config.config_integer(dat, ["orderly-runner", "workers"])

            self.containers["redis"] = "redis"
            self.containers["orderly-runner-api"] = "orderly-runner-api"
            self.containers["orderly-runner-worker"] = "orderly-runner-worker"

            self.volumes["orderly_library"] = config.config_string(dat, ["volumes", "orderly_library"])
            self.volumes["orderly_logs"] = config.config_string(dat, ["volumes", "orderly_logs"])

            self.images["orderly-runner"] = self.orderly_runner_ref
            self.images["redis"] = constellation.ImageReference("library", "redis", "8.0")

            self.redis_url = "redis://redis:6379"

        self.outpack_server_url = f"http://{self.container_prefix}-{self.containers['outpack-server']}:8000"

        if dat.get("proxy"):
            self.proxy_enabled = config.config_boolean(dat, ["proxy", "enabled"], True)
        else:
            self.proxy_enabled = False

        self.brand = Branding.from_data(dat, root=path)

        if self.proxy_enabled:
            self.proxy_hostname = config.config_string(dat, ["proxy", "hostname"])
            self.proxy_port_http = config.config_integer(dat, ["proxy", "port_http"])
            self.proxy_port_https = config.config_integer(dat, ["proxy", "port_https"])
            ssl = config.config_dict(dat, ["proxy", "ssl"], True)
            self.proxy_ssl_self_signed = ssl is None
            if not self.proxy_ssl_self_signed:
                self.proxy_ssl_certificate = config.config_string(dat, ["proxy", "ssl", "certificate"], True)
                self.proxy_ssl_key = config.config_string(dat, ["proxy", "ssl", "key"], True)

            self.proxy_name = config.config_string(dat, ["proxy", "image", "name"])
            self.proxy_tag = config.config_string(dat, ["proxy", "image", "tag"])
            self.proxy_ref = constellation.ImageReference(self.repo, self.proxy_name, self.proxy_tag)
            self.containers["proxy"] = "proxy"
            self.images["proxy"] = self.proxy_ref
            self.volumes["proxy_logs"] = config.config_string(dat, ["volumes", "proxy_logs"])

    def build_ref(self, dat, section, subsection, repo=None):
        repo = self.repo if repo is None else repo
        name = config.config_string(dat, [section, subsection, "name"])
        tag = config.config_string(dat, [section, subsection, "tag"])
        return constellation.ImageReference(repo, name, tag)

    def get_container(self, name):
        with DockerClient() as cl:
            return cl.containers.get(f"{self.container_prefix}-{self.containers[name]}")

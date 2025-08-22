import os

import constellation
from constellation import config

from packit_deploy.docker_helpers import DockerClient


class PackitConfig:
    def __init__(self, path, extra=None, options=None):
        dat = config.read_yaml(f"{path}/packit.yml")
        dat = config.config_build(path, dat, extra, options)
        self.vault = config.config_vault(dat, ["vault"])
        self.network = config.config_string(dat, ["network"])
        self.protect_data = config.config_boolean(dat, ["protect_data"])
        self.volumes = {
            "outpack": config.config_string(dat, ["volumes", "outpack"]),
            "packit_db": config.config_string(dat, ["volumes", "packit_db"]),
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
            self.orderly_runner_git_url = config.config_string(dat, ["orderly-runner", "git", "url"])
            self.orderly_runner_env = config.config_dict(dat, ["orderly-runner", "env"], is_optional=True, default={})
            if self.orderly_runner_git_url.startswith("git@"):
                self.orderly_runner_git_ssh_key = config.config_string(dat, ["orderly-runner", "git", "ssh"])
            else:
                self.orderly_runner_git_ssh_key = None
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

        brand_config = dat.get("brand", {})
        if brand_config.get("name"):
            self.brand_name = config.config_string(dat, ["brand", "name"])
        if brand_config.get("logo_path"):
            logo_path = config.config_string(dat, ["brand", "logo_path"])
            self.brand_logo_path = os.path.abspath(os.path.join(path, logo_path))
            self.brand_logo_name = os.path.basename(self.brand_logo_path)
        if brand_config.get("logo_link"):
            self.brand_logo_link = config.config_string(dat, ["brand", "logo_link"])
        if brand_config.get("logo_alt_text"):
            self.brand_logo_alt_text = config.config_string(dat, ["brand", "logo_alt_text"])
        elif brand_config.get("name"):
            self.brand_logo_alt_text = f"{self.brand_name} logo"
        if brand_config.get("favicon_path"):
            favicon_path = config.config_string(dat, ["brand", "favicon_path"])
            self.brand_favicon_path = os.path.abspath(os.path.join(path, favicon_path))
            self.brand_favicon_name = os.path.basename(self.brand_favicon_path)
        if brand_config.get("css"):
            if brand_config.get("css").get("light"):
                self.brand_accent_light = config.config_string(dat, ["brand", "css", "light", "accent"])
                self.brand_accent_foreground_light = config.config_string(
                    dat, ["brand", "css", "light", "accent_foreground"]
                )
                self.brand_light_mode_enabled = True
            else:
                self.brand_light_mode_enabled = False
            if brand_config.get("css").get("dark"):
                self.brand_accent_dark = config.config_string(dat, ["brand", "css", "dark", "accent"])
                self.brand_accent_foreground_dark = config.config_string(
                    dat, ["brand", "css", "dark", "accent_foreground"]
                )
                self.brand_dark_mode_enabled = True
            else:
                self.brand_dark_mode_enabled = False
        if (not brand_config.get("css")) or (not self.brand_dark_mode_enabled and not self.brand_light_mode_enabled):
            self.brand_light_mode_enabled = True
            self.brand_dark_mode_enabled = True

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

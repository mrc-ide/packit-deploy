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
        self.volumes = {"outpack": config.config_string(dat, ["volumes", "outpack"])}

        self.container_prefix = config.config_string(dat, ["container_prefix"])
        self.repo = config.config_string(dat, ["repo"])

        if "ssh" in dat:
            self.ssh_public = config.config_string(dat, ["ssh", "public"])
            self.ssh_private = config.config_string(dat, ["ssh", "private"])
            self.ssh = True
        else:
            self.ssh = False

        if "initial" in dat["outpack"]:
            self.outpack_source_url = config.config_string(dat, ["outpack", "initial", "url"])
        else:
            self.outpack_source_url = None

        self.outpack_ref = self.build_ref(dat, "outpack", "server")
        self.packit_api_ref = self.build_ref(dat, "packit", "api")
        self.packit_ref = self.build_ref(dat, "packit", "app")
        self.packit_db_ref = self.build_ref(dat, "packit", "db")
        self.packit_db_user = config.config_string(dat, ["packit", "db", "user"])
        self.packit_db_password = config.config_string(dat, ["packit", "db", "password"])

        if "auth" in dat["packit"]:
            self.packit_auth_enabled = config.config_boolean(dat, ["packit", "auth", "enabled"])
            self.packit_auth_method = config.config_string(dat, ["packit", "auth", "auth_method"])
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

        if dat.get("proxy"):
            self.proxy_enabled = config.config_boolean(dat, ["proxy", "enabled"], True)
        else:
            self.proxy_enabled = False

        self.branding_enabled = bool(dat.get("brand", {}).get("name") and dat.get("brand", {}).get("logo_path"))

        if self.branding_enabled:
            self.brand_name = config.config_string(dat, ["brand", "name"])
            logo_path = config.config_string(dat, ["brand", "logo_path"])
            self.brand_logo_path = os.path.abspath(os.path.join(path, logo_path))
            self.brand_logo_name = os.path.basename(self.brand_logo_path)

            # Optional branding configuration
            if dat.get("brand").get("logo_link"):
                self.brand_logo_link = config.config_string(dat, ["brand", "logo_link"])
            if dat.get("brand").get("logo_alt_text"):
                self.brand_logo_alt_text = config.config_string(dat, ["brand", "logo_alt_text"])
            if dat.get("brand").get("favicon_path"):
                favicon_path = config.config_string(dat, ["brand", "favicon_path"])
                self.brand_favicon_path = os.path.abspath(os.path.join(path, favicon_path))
                self.brand_favicon_name = os.path.basename(self.brand_favicon_path)
            if dat.get("brand").get("css"):
                self.brand_accent_light = config.config_string(dat, ["brand", "css", "light", "accent"])
                self.brand_accent_foreground_light = config.config_string(
                    dat, ["brand", "css", "light", "accent_foreground"]
                )
                if dat.get("brand").get("css").get("dark"):
                    self.brand_accent_dark = config.config_string(dat, ["brand", "css", "dark", "accent"])
                    self.brand_accent_foreground_dark = config.config_string(
                        dat, ["brand", "css", "dark", "accent_foreground"]
                    )
                else:
                    self.brand_accent_dark = self.brand_accent_light
                    self.brand_accent_foreground_dark = self.brand_accent_foreground_light

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

    def build_ref(self, dat, section, subsection):
        name = config.config_string(dat, [section, subsection, "name"])
        tag = config.config_string(dat, [section, subsection, "tag"])
        return constellation.ImageReference(self.repo, name, tag)

    def get_container(self, name):
        with DockerClient() as cl:
            return cl.containers.get(f"{self.container_prefix}-{self.containers[name]}")

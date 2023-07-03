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

        if "proxy" in dat and dat["proxy"]:
            self.proxy_enabled = config.config_boolean(dat, ["proxy", "enabled"], True)
        else:
            self.proxy_enabled = False

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

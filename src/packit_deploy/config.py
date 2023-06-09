import constellation
from constellation import config

from packit_deploy.docker_helpers import DockerClient


class PackitConfig:
    def __init__(self, path, extra=None, options=None):
        dat = config.read_yaml(f"{path}/packit.yml")
        dat = config.config_build(path, dat, extra, options)
        self.network = config.config_string(dat, ["network"])
        self.protect_data = config.config_boolean(dat, ["protect_data"])
        self.volumes = {"outpack": config.config_string(dat, ["volumes", "outpack"])}

        self.container_prefix = config.config_string(dat, ["container_prefix"])
        self.repo = config.config_string(dat, ["repo"])

        if "initial" in dat["outpack"]:
            source = config.config_string(dat, ["outpack", "initial", "source"])
            if source == "demo":
                self.outpack_demo = True
                self.outpack_source_url = None
            elif source == "clone":
                self.outpack_demo = False
                self.outpack_source_url = config.config_string(dat, ["outpack", "initial", "url"])
            else:
                err = "Unknown outpack initial source. Valid values are 'demo' and 'clone'"
                raise Exception(err)
        else:
            self.outpack_demo = False
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

    def build_ref(self, dat, section, subsection):
        name = config.config_string(dat, [section, subsection, "name"])
        tag = config.config_string(dat, [section, subsection, "tag"])
        return constellation.ImageReference(self.repo, name, tag)

    def get_container(self, name):
        with DockerClient() as cl:
            return cl.containers.get(f"{self.container_prefix}-{self.containers[name]}")

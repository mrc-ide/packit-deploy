from enum import StrEnum
from typing import Any, Literal, Optional
import json
import hvac
import os.path

import constellation
from constellation import config
from pydantic import BaseModel, Field


class VaultAuth(BaseModel):
    method: str
    args: dict[str, Any] = Field(default_factory=dict)

class Vault(BaseModel):
    addr: Optional[str]
    auth: VaultAuth

    def client(self) -> hvac.Client:
        return constellation.VaultConfig(self.addr, self.auth.method, self.auth.args).client()


class ImageReference(BaseModel):
    name: str
    tag: str


class Outpack(BaseModel):
    server: ImageReference
    migrate: ImageReference


class DBConfig(ImageReference):
    user: str
    password: str


class AuthMethod(StrEnum):
    PREAUTH = "preauth"
    BASIC = "basic"
    GITHUB = "github"


class JWTConfig(BaseModel):
    secret: str


class GithubClient(BaseModel):
    id: str
    secret: str


class OAuth2Redirect(BaseModel):
    packit_api_root: str
    url: str


class OAuth2(BaseModel):
    redirect: OAuth2Redirect


class Auth(BaseModel):
    enabled: Literal[True] = True
    auth_method: AuthMethod
    expiry_days: int
    jwt: JWTConfig

    github_api_org: Optional[str] = None
    github_api_team: Optional[str] = None
    github_client: Optional[GithubClient] = None
    oauth2: Optional[OAuth2] = None


class PackitAPI(ImageReference):
    management_port: int = 8081


class Packit(BaseModel):
    base_url: str
    api: PackitAPI
    app: ImageReference
    auth: Optional[Auth] = None
    db: DBConfig
    cors_allowed_origins: str = "http://localhost*,https://localhost*"


class TLS(BaseModel):
    certificate: str
    key: str


class Proxy(BaseModel):
    image: ImageReference
    enabled: Literal[True] = True
    hostname: str
    port_http: int = 80
    port_https: int = 443
    ssl: Optional[TLS] = None


class RunnerGit(BaseModel):
    url: str
    ssh: Optional[str] = None


class Runner(BaseModel):
    image: ImageReference
    workers: int
    git: RunnerGit
    env: dict[str, str] = Field(default_factory=dict)


class Theme(BaseModel):
    accent: str
    accent_foreground: str

class ThemeCollection(BaseModel):
    light: Optional[Theme] = None
    dark: Optional[Theme] = None

class Brand(BaseModel):
    name: Optional[str] = None
    favicon_path: Optional[str] = None
    logo_alt_text: Optional[str] = None
    logo_link: Optional[str] = None
    logo_path: Optional[str] = None
    css: ThemeCollection = Field(default_factory=ThemeCollection)

    @property
    def logo_name(self) -> Optional[str]:
        if self.logo_path is not None:
            return os.path.basename(self.logo_path)
        else:
            return None
    @property
    def favicon_name(self) -> Optional[str]:
        if self.favicon_path is not None:
            return os.path.basename(self.favicon_path)
        else:
            return None
    @property
    def dark_mode_enabled(self) -> bool:
        return (self.css.dark is not None) or (self.css.light is None)

    @property
    def light_mode_enabled(self) -> bool:
        return (self.css.light is not None) or (self.css.dark is None)

class Volumes(BaseModel):
    outpack: str
    packit_db: str
    packit_db_backup: str

    orderly_library: Optional[str] = None
    orderly_logs: Optional[str] = None
    proxy_logs: Optional[str] = None

class Config(BaseModel):
    container_prefix: str
    protect_data: bool
    repo: str
    network: str

    outpack: Outpack
    packit: Packit
    volumes: Volumes
    proxy: Optional[Proxy] = None
    vault: Optional[Vault] = None
    orderly_runner: Optional[Runner] = Field(alias="orderly-runner", default=None)
    brand: Brand = Field(default_factory=Brand)

    def _image_ref(self, ref: ImageReference) -> constellation.ImageReference:
        return constellation.ImageReference(self.repo, ref.name, ref.tag)

    @property
    def outpack_ref(self) -> constellation.ImageReference:
        return self._image_ref(self.outpack.server)

    @property
    def packit_db_ref(self) -> constellation.ImageReference:
        return self._image_ref(self.packit.db)

    @property
    def packit_api_ref(self) -> constellation.ImageReference:
        return self._image_ref(self.packit.api)

    @property
    def packit_ref(self) -> constellation.ImageReference:
        return self._image_ref(self.packit.app)

    @property
    def proxy_ref(self) -> Optional[constellation.ImageReference]:
        if self.proxy is None:
            return None
        else:
            return self._image_ref(self.proxy.image)

    @property
    def outpack_server_url(self) -> str:
        return f"http://{self.container_prefix}-outpack-server:8000"

    @classmethod
    def load(cls, name) -> "Config":
        dat = config.read_yaml(f"{name}/packit.yml")

        # `model_validate` is too strict because it expects values to be Python
        # objects already (eg. enums need to be the actual enum class, not
        # strings). Dumping out as json and validating back with
        # `model_validate_json` applies a different mode in Pydantic and does
        # what we want.
        #
        # See https://github.com/pydantic/pydantic/issues/11154
        return cls.model_validate_json(
            json.dumps(dat),
            strict=True,
            extra="forbid",
        )

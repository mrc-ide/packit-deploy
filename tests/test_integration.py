import json
import ssl
import subprocess
import time
import urllib
from unittest import mock

import docker
import tenacity
import vault_dev
from constellation import docker_util

from src.packit_deploy import cli
from src.packit_deploy.config import PackitConfig


def test_start_and_stop_noproxy():
    path = "config/noproxy"
    try:
        # Start
        res = cli.main(["start", path, "--pull"])
        assert res

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 4
        cfg = PackitConfig(path)
        assert docker_util.network_exists(cfg.network)
        assert docker_util.volume_exists(cfg.volumes["outpack"])
        assert docker_util.container_exists("packit-outpack-server")
        assert docker_util.container_exists("packit-packit-api")
        assert docker_util.container_exists("packit-packit-db")
        assert docker_util.container_exists("packit-packit")

        # Stop
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])
            containers = cl.containers.list()
            assert len(containers) == 0
            assert not docker_util.network_exists(cfg.network)
            assert not docker_util.volume_exists(cfg.volumes["outpack"])
            assert not docker_util.container_exists("packit-packit-api")
            assert not docker_util.container_exists("packit-packit-db")
            assert not docker_util.container_exists("packit-packit")
            assert not docker_util.container_exists("packit-outpack-server")
    finally:
        stop_packit(path)


def test_status():
    res = cli.main(["status", "config/noproxy"])
    assert res


def test_start_and_stop_proxy():
    path = "config/novault"
    try:
        res = cli.main(["start", "--pull", path])
        assert res

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 5
        assert docker_util.container_exists("packit-proxy")

        # Trivial check that the proxy container works:
        cfg = PackitConfig(path)
        proxy = cfg.get_container("proxy")
        ports = proxy.attrs["HostConfig"]["PortBindings"]
        assert set(ports.keys()) == {"443/tcp", "80/tcp"}
        http_get("http://localhost")
        res = http_get("http://localhost/api/packets", poll=3)
        # might take some seconds for packets to appear
        retries = 1
        while len(json.loads(res)) < 1 and retries < 5:
            res = http_get("http://localhost/api/packets")
            time.sleep(5)
            retries = retries + 1
        assert len(json.loads(res)) > 1
    finally:
        stop_packit(path)


def test_proxy_ssl_configured():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            write_secrets_to_vault(cfg)

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            proxy = cfg.get_container("proxy")
            cert = docker_util.string_from_container(proxy, "run/proxy/certificate.pem")
            key = docker_util.string_from_container(proxy, "run/proxy/key.pem")
            assert "c3rt" in cert
            assert "s3cret" in key

    finally:
        stop_packit(path)


def test_api_configured():
    path = "config/noproxy"
    try:
        cli.main(["start", path, "--pull"])
        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 4
        cfg = PackitConfig(path)

        api = cfg.get_container("packit-api")

        assert (
            get_env_var(api, "PACKIT_DB_URL")
            == b"jdbc:postgresql://packit-packit-db:5432/packit?stringtype=unspecified\n"
        )
        assert get_env_var(api, "PACKIT_DB_USER") == b"packituser\n"
        assert get_env_var(api, "PACKIT_DB_PASSWORD") == b"changeme\n"
        assert get_env_var(api, "PACKIT_OUTPACK_SERVER_URL") == b"http://packit-outpack-server:8000\n"
        assert get_env_var(api, "PACKIT_AUTH_ENABLED") == b"false\n"
    finally:
        stop_packit(path)


def test_api_configured_for_github_auth():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            write_secrets_to_vault(cfg)

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit-api")

            # assert env variables
            assert get_env_var(api, "PACKIT_AUTH_METHOD") == b"github\n"
            assert get_env_var(api, "PACKIT_AUTH_ENABLED") == b"true\n"
            assert get_env_var(api, "PACKIT_JWT_EXPIRY_DAYS") == b"1\n"
            assert get_env_var(api, "PACKIT_AUTH_GITHUB_ORG") == b"mrc-ide\n"
            assert get_env_var(api, "PACKIT_AUTH_GITHUB_TEAM") == b"packit\n"
            assert get_env_var(api, "PACKIT_JWT_SECRET") == b"jwts3cret\n"
            assert get_env_var(api, "PACKIT_AUTH_REDIRECT_URL") == b"https://packit/redirect\n"
    finally:
        stop_packit(path)


def test_api_configured_with_custom_branding():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            write_secrets_to_vault(cfg)

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit-api")

            # assert env variables
            assert get_env_var(api, "PACKIT_BRAND_LOGO_ALT_TEXT") == b"My logo\n"
            assert get_env_var(api, "PACKIT_BRAND_LOGO_NAME") == b"examplelogo.webp\n"
            assert get_env_var(api, "PACKIT_BRAND_LOGO_LINK") == b"https://www.google.com/\n"
    finally:
        stop_packit(path)


def test_custom_branding_end_to_end():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            write_secrets_to_vault(cfg)

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit")

            index_html = docker_util.string_from_container(api, "/usr/share/nginx/html/index.html")
            assert "<title>My Packit Instance</title>" in index_html
            assert "examplefavicon.ico" in index_html

            custom_css = docker_util.string_from_container(api, "/usr/share/nginx/html/css/custom.css")
            assert "--custom-accent: hsl(0 100% 50%);" in custom_css
            assert "--custom-accent-foreground: hsl(123 100% 50%);" in custom_css

            logo = docker_util.bytes_from_container(api, "/usr/share/nginx/html/img/examplelogo.webp")
            assert logo is not None and len(logo) > 0

            favicon = docker_util.bytes_from_container(api, "/usr/share/nginx/html/examplefavicon.ico")
            assert favicon is not None and len(favicon) > 0

            # Test that the index.html file is served without error, implying it has correct file permissions
            http_get(f"http://localhost:{s.port}/")
    finally:
        stop_packit(path)


# Very basic test for now, just checking that everything appears:
def test_deploy_with_runner_support():
    path = "config/runner"
    try:
        cli.main(["start", path])
        cl = docker.client.from_env()
        containers = cl.containers.list()

        prefix = "packit-orderly-runner-worker"
        assert sum(x.name.startswith(prefix) for x in containers) == 2

        cfg = PackitConfig(path)
        api = cfg.get_container("packit-api")

        assert get_env_var(api, "PACKIT_ORDERLY_RUNNER_URL") == b"http://packit-orderly-runner-api:8001\n"
        assert (
            get_env_var(api, "PACKIT_ORDERLY_RUNNER_REPOSITORY_URL")
            == b"https://github.com/reside-ic/orderly2-example.git\n"
        )
        assert get_env_var(api, "PACKIT_ORDERLY_RUNNER_LOCATION_URL") == get_env_var(api, "PACKIT_OUTPACK_SERVER_URL")

        runner = cfg.get_container("orderly-runner-api")
        assert get_env_var(runner, "PACKIT_RUNNER_EXAMPLE_ENVVAR") == b"hello\n"
    finally:
        stop_packit(path)


def test_vault():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            write_secrets_to_vault(cfg)

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit-api")

            assert get_env_var(api, "PACKIT_DB_USER") == b"us3r\n"
            assert get_env_var(api, "PACKIT_DB_PASSWORD") == b"p@ssword\n"
    finally:
        stop_packit(path)


def stop_packit(path):
    with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
        prompt.return_value = True
        cli.main(["stop", path, "--kill", "--volumes", "--network"])


def write_secrets_to_vault(cfg):
    cl = cfg.vault.client()
    cl.write("secret/cert", value="c3rt")
    cl.write("secret/key", value="s3cret")
    cl.write("secret/db/user", value="us3r")
    cl.write("secret/db/password", value="p@ssword")
    cl.write("secret/ssh", public="publ1c", private="private")
    cl.write("secret/auth/githubclient/id", value="ghclientid")
    cl.write("secret/auth/githubclient/secret", value="ghs3cret")
    cl.write("secret/auth/jwt/secret", value="jwts3cret")


# Because we wait for a go signal to come up, we might not be able to
# make the request right away:
def http_get(url, retries=5, poll=1):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for _i in range(retries):
        try:
            r = urllib.request.urlopen(url, context=ctx)  # noqa: S310
            return r.read().decode("UTF-8")
        except (urllib.error.URLError, ConnectionResetError) as e:
            print("sleeping...")
            time.sleep(poll)
            error = e
    raise error


def get_env_var(container, env):
    return docker_util.exec_safely(container, ["sh", "-c", f"echo ${env}"]).output


def test_db_volume_is_persisted():
    path = "config/noproxy"
    try:
        res = cli.main(["start", path])
        assert res

        # Create a real user
        create_super_user()

        cfg = PackitConfig(path)
        sql = "SELECT username from public.user"
        cmd = ["psql", "-t", "-A", "-U", "packituser", "-d", "packit", "-c", sql]

        # Check that we have actually created our user:
        db = cfg.get_container("packit-db")
        users = docker_util.exec_safely(db, cmd).output.decode("UTF-8").splitlines()
        assert set(users) == {"SERVICE", "resideUser@resideAdmin.ic.ac.uk"}

        # Tear things down, but leave the volumes in place:
        cli.main(["stop", path, "--kill", "--network"])

        # Bring back up
        res = cli.main(["start", path])
        assert res

        # Check that the users have survived
        db = cfg.get_container("packit-db")
        users = docker_util.exec_safely(db, cmd).output.decode("UTF-8").splitlines()
        assert set(users) == {"SERVICE", "resideUser@resideAdmin.ic.ac.uk"}
    finally:
        stop_packit(path)


@tenacity.retry(wait=tenacity.wait_fixed(1), stop=tenacity.stop_after_attempt(20))
def create_super_user():
    print("Trying to create superuser")
    subprocess.run(["./scripts/create-super-user"], check=True)  # noqa: S603
    print("...success")

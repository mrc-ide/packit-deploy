import json
import ssl
import subprocess
import time
import urllib
from unittest import mock

import docker
import tenacity
import vault_dev
from click.testing import CliRunner
from constellation import docker_util
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from packit_deploy import cli
from packit_deploy.config import PackitConfig
from packit_deploy.docker_helpers import DockerClient


def _stop_args(path):
    return ["stop", "--name", path, "--kill", "--volumes", "--network"]


def test_start_and_stop_noproxy():
    path = "config/noproxy"
    try:
        # Start
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

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
        with mock.patch("packit_deploy.cli._prompt_yes_no") as prompt:
            prompt.return_value = True
            res = runner.invoke(cli.cli, _stop_args(path))
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


def test_status(name="config/noproxy"):
    res = CliRunner().invoke(cli.cli, ["status", "--name", name])
    assert res.exit_code == 0
    assert "Configured as 'config/noproxy'" in res.output


def test_start_and_stop_proxy():
    path = "config/novault"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 5
        assert docker_util.container_exists("packit-proxy")

        # Trivial check that the proxy container works:
        proxy = get_container("packit-proxy")
        ports = proxy.attrs["HostConfig"]["PortBindings"]
        assert set(ports.keys()) == {"443/tcp", "80/tcp"}
        http_get("http://localhost")
        res = http_get("http://localhost/api/packets", poll=3)
        # might take some seconds for packets to appear
        retries = 1
        while len(json.loads(res)) < 1 and retries < 5:
            res = http_get("http://localhost/api/packets")
            time.sleep(5)
            retries += 1
        assert len(json.loads(res)) > 1
    finally:
        stop_packit(path)


# For all tests involving vault, there's some grossness to deal with.
# It's not easy to inject the vault configuration (url and token) into
# the packit yml configuration, so we bypass it this way for tests.
# Previously one could pass arbitrary additional options to override
# bits of the constellation config by writing
# '--option=vault.addr=URL' but that's removed generally because it
# was never used outside of tests either.  We could also inject these
# into the yml and rewrite it, which would make the implementation
# less coupled from the tests.
def test_proxy_ssl_configured():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())
            cli.cli_start.callback(pull=False, name=path, options=options)
            client = docker.from_env()
            container = client.containers.get("packit-acme-buddy")
            env = container.attrs["Config"]["Env"]
            env_dict = dict(e.split("=", 1) for e in env)
            assert "hdb-us3r" in env_dict["HDB_ACME_USERNAME"]
            assert "hdb-p@assword" in env_dict["HDB_ACME_PASSWORD"]

    finally:
        stop_packit(path)


def test_acme_buddy_writes_cert():
    path = "config/self-signed"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())
            cli.cli_start.callback(pull=False, name=path, options=options)
            client = docker.from_env()
            proxy = client.containers.get("packit-proxy")
            cert_str = docker_util.string_from_container(proxy, "/run/proxy/certificate.pem")
            cert = x509.load_pem_x509_certificate(cert_str.encode(), default_backend())
            assert cert.subject == cert.issuer

    finally:
        stop_packit(path)


def test_api_configured():
    path = "config/noproxy"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 4

        api = get_container("packit-packit-api")

        assert get_env_var(api, "PACKIT_DB_URL") == b"jdbc:postgresql://packit-db:5432/packit?stringtype=unspecified\n"
        assert get_env_var(api, "PACKIT_DB_USER") == b"packituser\n"
        assert get_env_var(api, "PACKIT_DB_PASSWORD") == b"changeme\n"
        assert get_env_var(api, "PACKIT_OUTPACK_SERVER_URL") == b"http://outpack-server:8000\n"
        assert get_env_var(api, "PACKIT_AUTH_ENABLED") == b"false\n"
        # has configured default management port
        assert get_env_var(api, "PACKIT_MANAGEMENT_PORT") == b"8081\n"
    finally:
        stop_packit(path)


def test_api_configured_for_github_auth():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())

            cli.cli_start.callback(pull=False, name=path, options=options)

            api = get_container("packit-packit-api")

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
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())

            cli.cli_start.callback(pull=False, name=path, options=options)

            api = get_container("packit-packit-api")

            assert get_env_var(api, "PACKIT_BRAND_LOGO_ALT_TEXT") == b"My logo\n"
            assert get_env_var(api, "PACKIT_BRAND_LOGO_NAME") == b"examplelogo.webp\n"
            assert get_env_var(api, "PACKIT_BRAND_LOGO_LINK") == b"https://www.google.com/\n"
            assert get_env_var(api, "PACKIT_BRAND_DARK_MODE_ENABLED") == b"true\n"
            assert get_env_var(api, "PACKIT_BRAND_LIGHT_MODE_ENABLED") == b"true\n"
    finally:
        stop_packit(path)


def test_custom_branding_end_to_end():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())

            cli.cli_start.callback(pull=False, name=path, options=options)

            api = get_container("packit-packit")

            index_html = docker_util.string_from_container(api, "/usr/share/nginx/html/index.html")
            assert "<title>My Packit Instance</title>" in index_html
            assert "examplefavicon.ico" in index_html

            custom_css = docker_util.string_from_container(api, "/usr/share/nginx/html/css/custom.css")
            assert "--custom-accent: hsl(0 100% 50%);" in custom_css  # light theme
            assert "--custom-accent-foreground: hsl(123 100% 50%);" in custom_css
            assert "--custom-accent: hsl(30 100% 50%);" in custom_css  # dark theme
            assert "--custom-accent-foreground: hsl(322 50% 87%);" in custom_css

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
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--name", path])
        assert res.exit_code == 0

        cl = docker.client.from_env()
        containers = cl.containers.list()

        prefix = "packit-orderly-runner-worker"
        assert sum(x.name.startswith(prefix) for x in containers) == 2

        api = get_container("packit-packit-api")

        assert get_env_var(api, "PACKIT_ORDERLY_RUNNER_URL") == b"http://orderly-runner-api:8001\n"
        assert (
            get_env_var(api, "PACKIT_ORDERLY_RUNNER_REPOSITORY_URL")
            == b"https://github.com/reside-ic/orderly2-example.git\n"
        )
        assert get_env_var(api, "PACKIT_ORDERLY_RUNNER_LOCATION_URL") == get_env_var(api, "PACKIT_OUTPACK_SERVER_URL")

        runner = get_container("packit-orderly-runner-api")
        assert get_env_var(runner, "PACKIT_RUNNER_EXAMPLE_ENVVAR") == b"hello\n"
    finally:
        stop_packit(path)


def test_vault():
    path = "config/complete"
    try:
        with vault_dev.Server() as s:
            url = f"http://localhost:{s.port}"
            options = {"vault": {"addr": url, "auth": {"args": {"token": s.token}}}}
            write_secrets_to_vault(s.client())

            cli.cli_start.callback(pull=False, name=path, options=options)

            api = get_container("packit-packit-api")

            assert get_env_var(api, "PACKIT_DB_USER") == b"us3r\n"
            assert get_env_var(api, "PACKIT_DB_PASSWORD") == b"p@ssword\n"
    finally:
        stop_packit(path)


# Test that the custom management port defined in the novault config
# has been correctly configured in the api so we can get health metrics from
# within the network - we currently do not expose packit metrics through
# the proxy as this will be done through montagu proxy, and handled
# separately in the nix deployment
def test_can_read_packit_health_metrics_on_custom_port():
    path = "config/novault"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        # has configured non-default management port
        api = get_container("packit-packit-api")
        assert get_env_var(api, "PACKIT_MANAGEMENT_PORT") == b"8082\n"

        proxy = get_container("packit-proxy")
        curl_output = curl_get_from_container(proxy, "http://packit-api:8082/health")
        assert '{"status":"UP"}' in curl_output
    finally:
        stop_packit(path)


def test_can_read_metrics_from_proxy_single_instance():
    path = "config/runner"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        retries = 50
        api_res = http_get("http://localhost:8080/metrics/packit-api", retries=retries)
        assert "application_ready_time_seconds" in api_res

        outpack_res = http_get("http://localhost:8080/metrics/outpack_server", retries=retries)
        assert "outpack_server_build_info" in outpack_res
    finally:
        stop_packit(path)


def test_can_read_metrics_from_proxy_multi_instance():
    path = "config/multipackit"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        retries = 50
        expected_api_metrics_content = "application_ready_time_seconds"
        assert expected_api_metrics_content in http_get("http://foo.localhost:8080/metrics/packit-api", retries=retries)
        assert expected_api_metrics_content in http_get("http://bar.localhost:8080/metrics/packit-api", retries=retries)

        expected_outpack_metrics_content = "outpack_server_build_info"
        assert expected_outpack_metrics_content in http_get(
            "http://foo.localhost:8080/metrics/outpack_server", retries=retries
        )
        assert expected_outpack_metrics_content in http_get(
            "http://bar.localhost:8080/metrics/outpack_server", retries=retries
        )
    finally:
        stop_packit(path)


def stop_packit(path):
    with mock.patch("packit_deploy.cli._prompt_yes_no") as prompt:
        prompt.return_value = True
        CliRunner().invoke(cli.cli, _stop_args(path))


def write_secrets_to_vault(cl):
    cl.write("secret/certbot-hdb/credentials", username="hdb-us3r", password="hdb-p@assword")
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


def get_container(name):
    with DockerClient() as cl:
        return cl.containers.get(name)


def test_db_volume_is_persisted():
    path = "config/noproxy"
    try:
        runner = CliRunner()
        res = runner.invoke(cli.cli, ["start", "--pull", "--name", path])
        assert res.exit_code == 0

        # Create a real user
        create_super_user()

        sql = "SELECT username from public.user"
        cmd = ["psql", "-t", "-A", "-U", "packituser", "-d", "packit", "-c", sql]

        # Check that we have actually created our user:
        db = get_container("packit-packit-db")
        users = docker_util.exec_safely(db, cmd).output.decode("UTF-8").splitlines()
        assert set(users) == {"SERVICE", "resideUser@resideAdmin.ic.ac.uk"}

        # Tear things down, but leave the volumes in place:
        res = runner.invoke(cli.cli, ["stop", "--name", path, "--kill", "--network"])
        assert res.exit_code == 0

        # Bring back up
        res = runner.invoke(cli.cli, ["start", "--name", path])
        assert res.exit_code == 0

        # Check that the users have survived
        db = get_container("packit-packit-db")
        users = docker_util.exec_safely(db, cmd).output.decode("UTF-8").splitlines()
        assert set(users) == {"SERVICE", "resideUser@resideAdmin.ic.ac.uk"}
    finally:
        stop_packit(path)


@tenacity.retry(wait=tenacity.wait_fixed(1), stop=tenacity.stop_after_attempt(20))
def curl_get_from_container(container, url):
    # wait for curl results from a container that may take a few attempts while it spins up
    return docker_util.exec_safely(container, ["curl", url]).output.decode("UTF-8")


@tenacity.retry(wait=tenacity.wait_fixed(1), stop=tenacity.stop_after_attempt(20))
def create_super_user():
    print("Trying to create superuser")
    subprocess.run(["./scripts/create-super-user"], check=True)
    print("...success")

import io
import shutil
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from packit_deploy import cli
from packit_deploy.cli import _prompt_yes_no, _verify_data_loss


def test_can_run_start(mocker):
    mocker.patch("packit_deploy.cli._constellation")
    runner = CliRunner()
    res = runner.invoke(cli.cli, ["start"])
    assert res.exit_code == 0
    assert cli._constellation.call_count == 1
    assert cli._constellation.mock_calls[0] == mock.call(None, options=None)


def test_can_run_status(mocker):
    mocker.patch("packit_deploy.cli._read_identity")
    mocker.patch("packit_deploy.cli._constellation")
    cli._read_identity.return_value = "config/noproxy"
    runner = CliRunner()
    res = runner.invoke(cli.cli, ["status"])
    assert res.exit_code == 0
    assert cli._read_identity.call_count == 1
    assert cli._read_identity.mock_calls[0] == mock.call(None)
    assert cli._constellation.call_count == 1
    assert cli._constellation.mock_calls[0] == mock.call("config/noproxy")


def test_that_can_configure_system():
    runner = CliRunner()
    path_config = Path("config").absolute()
    with runner.isolated_filesystem():
        shutil.copytree(path_config, "config")

        res = runner.invoke(cli.cli, ["configure", "config/noproxy"])
        assert res.exit_code == 0
        assert "Configured packit as 'config/noproxy'" in res.stdout

        assert cli._read_identity() == "config/noproxy"

        res = runner.invoke(cli.cli, ["configure", "config/noproxy"])
        assert res.exit_code == 0
        assert "Packit already configured as 'config/noproxy'" in res.stdout
        assert cli._read_identity() == "config/noproxy"

        res = runner.invoke(cli.cli, ["configure", "config/proxy"])
        assert res.exit_code == 1
        assert "already configured as 'config/noproxy'" in str(res.exception)
        assert cli._read_identity() == "config/noproxy"

        res = runner.invoke(cli.cli, ["unconfigure"])
        assert res.exit_code == 0
        assert "Unconfigured packit (was 'config/noproxy')" in res.stdout
        assert cli._read_identity(required=False) is None

        res = runner.invoke(cli.cli, ["unconfigure"])
        assert res.exit_code == 0
        assert "Packit is not configured" in res.stdout


def test_can_error_if_not_configured():
    runner = CliRunner()
    with runner.isolated_filesystem():
        assert cli._read_identity(required=False) is None
        msg = "Packit identity is not yet configured"
        with pytest.raises(Exception, match=msg):
            cli._read_identity()


def test_verify_data_loss_called():
    f = io.StringIO()
    with redirect_stdout(f):
        with mock.patch("packit_deploy.cli._verify_data_loss") as verify:
            verify.return_value = True
            runner = CliRunner()
            res = runner.invoke(cli.cli, ["stop", "--volumes", "--name", "config/noproxy"])
            assert res.exit_code == 0

    assert verify.called


def test_verify_data_loss_not_called():
    f = io.StringIO()
    with redirect_stdout(f):
        with mock.patch("packit_deploy.cli._verify_data_loss") as verify:
            verify.return_value = True
            runner = CliRunner()
            res = runner.invoke(cli.cli, ["stop", "--name", "config/noproxy"])
            assert res.exit_code == 0

    assert not verify.called


def test_verify_data_loss_warns_if_loss():
    f = io.StringIO()
    with redirect_stdout(f):
        with mock.patch("packit_deploy.cli._prompt_yes_no") as prompt:
            prompt.return_value = True
            _verify_data_loss(False)

    assert prompt.called
    assert "WARNING! PROBABLE IRREVERSIBLE DATA LOSS!" in f.getvalue()


def test_verify_data_loss_throws_if_loss():
    with mock.patch("packit_deploy.cli._prompt_yes_no") as prompt:
        prompt.return_value = False
        with pytest.raises(Exception, match="Not continuing"):
            _verify_data_loss(False)


def test_verify_data_prevents_unwanted_loss():
    msg = "Cannot remove volumes with this configuration"
    with mock.patch("packit_deploy.cli._prompt_yes_no"):
        with pytest.raises(Exception, match=msg):
            _verify_data_loss(True)


def test_prompt_is_quite_strict():
    assert _prompt_yes_no(lambda _: "yes")
    assert not _prompt_yes_no(lambda _: "no")
    assert not _prompt_yes_no(lambda _: "Yes")
    assert not _prompt_yes_no(lambda _: "Great idea!")
    assert not _prompt_yes_no(lambda _: "")

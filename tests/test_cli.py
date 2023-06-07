from src.packit_deploy import cli


def test_parse_args():
    res = cli.main(["start", "config/basic", "--pull"])
    assert res[0] == "config/basic"
    assert res[1] is None
    assert res[2] == []
    args = res[3]
    assert args.action == "start"
    assert args.pull is True
    assert args.kill is False
    assert args.volumes is False
    assert args.network is False

    res = cli.main(["start", "config/basic", "--extra=extra.yml"])
    assert res[1] == "extra.yml"

    res = cli.main(["start", "config/basic", "--option=a=x", "--option=b.c=y"])
    assert res[2] == [{"a": "x"}, {"b": {"c": "y"}}]

    res = cli.main(["stop", "config/basic", "--kill", "--network", "--volumes"])
    args = res[3]
    assert args.action == "stop"
    assert args.pull is False
    assert args.kill is True
    assert args.volumes is True
    assert args.network is True

    res = cli.main(["status", "config/basic"])
    args = res[3]
    assert args.action == "status"

    res = cli.main(["--version"])
    assert res == "0.0.0"

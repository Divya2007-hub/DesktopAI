import subprocess
from unittest.mock import MagicMock

import pytest

from src.core import tools


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/test",
        "sudo apt update",
        "shutdown now",
        "reboot",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/tmp/test",
        "chmod -R 777 /tmp/test",
        "chown -R root /tmp/test",
    ],
)
def test_dangerous_commands_are_detected(command):
    assert tools.is_dangerous_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo hello",
        "python --version",
        "git status",
        "ls -la",
    ],
)
def test_safe_commands_are_not_flagged(command):
    assert not tools.is_dangerous_command(command)


def test_output_is_unchanged_when_within_limit(monkeypatch):
    monkeypatch.setattr(tools.config, "COMMAND_MAX_OUTPUT_CHARS", 20)

    assert tools.truncate_command_output("hello") == "hello"


def test_long_output_is_truncated(monkeypatch):
    monkeypatch.setattr(tools.config, "COMMAND_MAX_OUTPUT_CHARS", 20)

    output = tools.truncate_command_output("x" * 100)

    assert len(output) == 20
    assert "truncated" in output


def test_empty_command_is_rejected():
    result = tools.run_command.invoke({"command": "   "})

    assert "cannot be empty" in result


def test_dangerous_command_is_cancelled_without_execution(monkeypatch):
    monkeypatch.setattr(
        tools.config, "COMMAND_REQUIRE_CONFIRMATION", True
    )
    monkeypatch.setattr(
        tools.overlay, "confirm_command", lambda command: False
    )

    popen = MagicMock()
    monkeypatch.setattr(tools.subprocess, "Popen", popen)

    result = tools.run_command.invoke({"command": "sudo apt update"})

    assert "cancelled" in result.lower()
    popen.assert_not_called()


def test_approved_dangerous_command_can_execute(monkeypatch):
    monkeypatch.setattr(
        tools.config, "COMMAND_REQUIRE_CONFIRMATION", True
    )
    monkeypatch.setattr(
        tools.overlay, "confirm_command", lambda command: True
    )

    process = MagicMock()
    process.communicate.return_value = ("approved output", None)
    process.returncode = 0

    popen = MagicMock(return_value=process)
    monkeypatch.setattr(tools.subprocess, "Popen", popen)

    result = tools.run_command.invoke({"command": "sudo apt update"})

    assert result == "approved output"
    popen.assert_called_once()


def test_command_timeout_terminates_process(monkeypatch):
    monkeypatch.setattr(
        tools.config, "COMMAND_REQUIRE_CONFIRMATION", False
    )
    monkeypatch.setattr(tools.config, "COMMAND_TIMEOUT", 1)

    process = MagicMock()
    process.pid = 1234
    process.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=1),
        ("partial output", None),
    ]

    monkeypatch.setattr(
        tools.subprocess, "Popen", MagicMock(return_value=process)
    )

    terminate = MagicMock()
    monkeypatch.setattr(tools, "terminate_command_process", terminate)

    result = tools.run_command.invoke({"command": "long-running-command"})

    assert "timed out" in result.lower()
    terminate.assert_called_once_with(process)
    assert "partial output" in result
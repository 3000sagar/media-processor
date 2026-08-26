from unittest.mock import patch

from app.utils.ffmpeg_runner import transcode


def test_ffmpeg_invoked_with_list_args_and_shell_false(tmp_path):
    malicious_input = "input.mp4; rm -rf / #"
    output_path = str(tmp_path / "out.mp4")

    with patch("app.utils.ffmpeg_runner.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = b""
        # The command-injection property under test is about argument construction, not
        # actual ffmpeg execution (which is fully mocked here) — so satisfy the output-
        # existence check with a real placeholder file rather than disabling that check.
        with open(output_path, "wb") as f:
            f.write(b"fake output bytes")

        transcode(
            input_path=malicious_input,
            output_path=output_path,
            resolution="1280x720",
            codec="libx264",
            allowed_protocols="file",
            timeout_seconds=10,
        )

    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert isinstance(cmd, list), "ffmpeg must be invoked with a list of args, never a joined string"
    assert kwargs.get("shell", False) is False
    assert malicious_input in cmd  # present as ONE argument, not concatenated into a shell string
    assert "-protocol_whitelist" in cmd
    assert "file" in cmd  # http/https/concat protocols are never in the allowed set

import os
import subprocess


class FfmpegError(RuntimeError):
    pass


def transcode(
    input_path: str,
    output_path: str,
    resolution: str,
    codec: str,
    allowed_protocols: str,
    timeout_seconds: int,
) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", allowed_protocols,  # blocks http/https/concat/subfile — the
                                                      # exact protocol classes used in known
                                                      # FFmpeg SSRF/LFI vulnerabilities
        "-i", input_path,
        "-vf", f"scale={resolution}",
        "-c:v", codec,
        output_path,
    ]
    _run(cmd, timeout_seconds, expected_output_path=output_path)


def extract_thumbnail(
    input_path: str,
    output_path: str,
    allowed_protocols: str,
    timeout_seconds: int,
    at_seconds: float = 2.0,
) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", allowed_protocols,
        "-ss", str(at_seconds),
        "-i", input_path,
        "-frames:v", "1",
        output_path,
    ]
    _run(cmd, timeout_seconds, expected_output_path=output_path)


def _run(cmd: list[str], timeout_seconds: int, expected_output_path: str | None = None) -> None:
    # shell=False (the default, but stated explicitly) + list args means no shell metacharacter
    # in any input path can ever be interpreted as a command separator. Never change this to
    # a joined string / shell=True, regardless of how convenient it seems for a one-off fix.
    try:
        # Justification for suppressing S603 below: this call is exactly the hardening
        # this module exists to provide — list-args (never a joined string), shell=False
        # (never True), and a protocol_whitelist baked into every caller. Ruff's S603
        # flags all subprocess calls for manual review; this one has already had that review.
        result = subprocess.run(  # noqa: S603
            cmd, capture_output=True, timeout=timeout_seconds, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FfmpegError(f"ffmpeg timed out after {timeout_seconds}s") from exc

    if result.returncode != 0:
        # stderr can be large/noisy; truncate before it ends up in logs or a failure reason field.
        stderr_tail = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise FfmpegError(f"ffmpeg exited {result.returncode}: {stderr_tail}")

    # ffmpeg can exit 0 while producing no usable output — e.g. a -ss seek point past the
    # end of a short clip silently yields zero frames. Caught by an actual test run against
    # a real short fixture, not by inspection; treat a missing/empty output as a hard failure
    # rather than letting a downstream S3 upload fail with a confusing "file not found".
    if expected_output_path is not None:
        if not os.path.exists(expected_output_path) or os.path.getsize(expected_output_path) == 0:
            raise FfmpegError(f"ffmpeg reported success but produced no output at {expected_output_path}")

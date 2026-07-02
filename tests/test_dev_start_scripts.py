import socket
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dev_start_batch_uses_windows_crlf_line_endings():
    """cmd.exe can misparse UTF-8 batch comments when the file uses bare LF."""
    content = (ROOT / "dev-start.bat").read_bytes()

    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")


def test_dev_start_pip_probe_does_not_promote_pip_notice_to_error():
    """pip writes version notices to stderr; the probe must not merge stderr into errors."""
    script = (ROOT / "dev-start.ps1").read_text(encoding="utf-8")

    assert "& $PipExe list --format=freeze > $null 2>&1" not in script
    assert "--disable-pip-version-check" in script
    assert "2>$null" in script


def test_dev_start_dependency_probes_do_not_merge_native_stderr():
    """With $ErrorActionPreference=Stop, native stderr merged via 2>&1 becomes fatal."""
    script = (ROOT / "dev-start.ps1").read_text(encoding="utf-8")

    assert "2>&1" not in script


def test_dev_start_stops_process_trees_for_reloading_servers():
    """uvicorn --reload and npm/vite spawn children that outlive direct Stop-Process."""
    script = (ROOT / "dev-start.ps1").read_text(encoding="utf-8")

    assert "function Stop-ProcessTree" in script
    assert "Stop-ProcessTree -ProcessId $script:FrontendProcess.Id" in script
    assert "Stop-ProcessTree -ProcessId $script:BackendProcess.Id" in script


def test_dev_start_waits_for_frontend_on_localhost():
    """Vite may listen on ::1 for localhost instead of IPv4 127.0.0.1."""
    script = (ROOT / "dev-start.ps1").read_text(encoding="utf-8")

    assert 'Wait-TcpPort -HostName "localhost" -Port $FrontendPort' in script


def test_tcp_port_probe_detects_ipv6_localhost_listener():
    """Windows PowerShell must detect Vite when localhost resolves to ::1."""
    script = (ROOT / "dev-start.ps1").read_text(encoding="utf-8")
    start = script.index("function Test-TcpPort")
    end = script.index("# ===== 等待端口就绪", start)
    function_source = script[start:end]

    try:
        listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        listener.bind(("::1", 0))
        listener.listen(1)
    except OSError:
        return

    with listener:
        port = listener.getsockname()[1]
        command = textwrap.dedent(
            f"""
            $ErrorActionPreference = "Stop"
            {function_source}
            if (Test-TcpPort -HostName "localhost" -Port {port}) {{
                "OK"
            }} else {{
                "FAIL"
                exit 1
            }}
            """
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout

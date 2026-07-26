import subprocess

import psutil


def system_stats() -> dict:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_count": psutil.cpu_count(),
        "load_avg": [round(x, 2) for x in psutil.getloadavg()],
        "mem_used_mb": round(vm.used / 1024 / 1024),
        "mem_total_mb": round(vm.total / 1024 / 1024),
        "mem_percent": vm.percent,
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
        "disk_percent": disk.percent,
        "boot_time": psutil.boot_time(),
    }


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr or "").strip()
    except Exception as e:
        return f"error: {e}"


def service_status(service: str) -> dict:
    active = _run(["systemctl", "is-active", service])
    enabled = _run(["systemctl", "is-enabled", service])
    since = _run(["systemctl", "show", service, "--property=ActiveEnterTimestamp", "--value"])
    return {"active": active, "enabled": enabled, "since": since}


def recent_logs(service: str, lines: int = 60) -> str:
    return _run(["journalctl", "-u", service, "--no-pager", "-n", str(lines)])

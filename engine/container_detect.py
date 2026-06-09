"""Container detection and escape vector enumeration for authorized security testing.

Reports findings only -- NEVER exploits anything.
"""

from __future__ import annotations

import logging
import os
import platform
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CAPABILITY_NAMES: dict[int, str] = {
    0: "CAP_CHOWN",
    1: "CAP_DAC_OVERRIDE",
    2: "CAP_DAC_READ_SEARCH",
    3: "CAP_FOWNER",
    4: "CAP_FSETID",
    5: "CAP_KILL",
    6: "CAP_SETGID",
    7: "CAP_SETUID",
    8: "CAP_SETPCAP",
    9: "CAP_LINUX_IMMUTABLE",
    10: "CAP_NET_BIND_SERVICE",
    11: "CAP_NET_BROADCAST",
    12: "CAP_NET_ADMIN",
    13: "CAP_NET_RAW",
    14: "CAP_IPC_LOCK",
    15: "CAP_IPC_OWNER",
    16: "CAP_SYS_MODULE",
    17: "CAP_SYS_RAWIO",
    18: "CAP_SYS_CHROOT",
    19: "CAP_SYS_PTRACE",
    20: "CAP_SYS_PACCT",
    21: "CAP_SYS_ADMIN",
    22: "CAP_SYS_BOOT",
    23: "CAP_NICE",
    24: "CAP_SYS_RESOURCE",
    25: "CAP_SYS_TIME",
    26: "CAP_SYS_TTY_CONFIG",
    27: "CAP_MKNOD",
    28: "CAP_LEASE",
    29: "CAP_AUDIT_WRITE",
    30: "CAP_AUDIT_CONTROL",
    31: "CAP_SETFCAP",
    32: "CAP_MAC_OVERRIDE",
    33: "CAP_MAC_ADMIN",
    34: "CAP_SYSLOG",
    35: "CAP_WAKE_ALARM",
    36: "CAP_BLOCK_SUSPEND",
    37: "CAP_AUDIT_READ",
}

# Known container CVEs: (substring of kernel version, cve id, description)
KNOWN_CONTAINER_CVES: list[tuple[str, str, str]] = [
    ("4.4.", "CVE-2016-5195", "Dirty COW - race condition allows privilege escalation"),
    ("4.8.", "CVE-2016-5195", "Dirty COW - race condition allows privilege escalation"),
    ("4.4.0", "CVE-2017-5123", "BPF sign extension漏洞 allow privilege escalation"),
    ("3.", "CVE-2016-0728", "Keyrings reference count overflow allows privilege escalation"),
    ("4.6.", "CVE-2016-8655", "AF_PACKET race condition allows privilege escalation"),
    ("4.14.", "CVE-2022-0185", "cgroup v1 escape via integer overflow"),
    ("5.", "CVE-2022-0492", "cgroup v1 release_agent escape"),
    ("5.8.", "CVE-2021-4034", "pkexec local privilege escalation (not kernel, but common)"),
]


@dataclass
class ContainerInfo:
    is_container: bool = False
    container_type: str = "none"
    container_id: str = ""
    hostname: str = ""


@dataclass
class EscapeFinding:
    vector: str = ""
    severity: str = "info"
    description: str = ""
    detail: str = ""


def _is_linux() -> bool:
    return platform.system() == "Linux"


def _read_file(path: str) -> str | None:
    try:
        with open(path, "r") as f:
            return f.read()
    except (OSError, IOError, PermissionError):
        return None


def detect_container() -> ContainerInfo:
    """Detect if Mythos is running inside a container.

    Checks multiple indicators: /.dockerenv, /proc/1/cgroup, environment
    variables, and mount info for overlayfs.
    """
    info = ContainerInfo(hostname=_get_hostname())

    if not _is_linux():
        info.container_type = "unknown"
        return info

    # Check /.dockerenv (Docker-specific)
    if os.path.exists("/.dockerenv"):
        info.is_container = True
        info.container_type = "docker"
        info.container_id = _extract_container_id()
        return info

    # Check /.dockerinit (older Docker)
    if os.path.exists("/.dockerinit"):
        info.is_container = True
        info.container_type = "docker"
        info.container_id = _extract_container_id()
        return info

    # Check /proc/1/cgroup for container signatures
    cgroup_content = _read_file("/proc/1/cgroup")
    if cgroup_content:
        for line in cgroup_content.strip().splitlines():
            line_lower = line.lower()
            if "docker" in line_lower:
                info.is_container = True
                info.container_type = "docker"
                info.container_id = _extract_container_id()
                return info
            if "lxc" in line_lower:
                info.is_container = True
                info.container_type = "lxc"
                return info
            if "podman" in line_lower or "libpod" in line_lower:
                info.is_container = True
                info.container_type = "podman"
                info.container_id = _extract_container_id()
                return info
            # Kubernetes often uses docker or containerd under the hood
            if "kubepods" in line_lower:
                info.is_container = True
                if info.container_type == "none":
                    info.container_type = "docker"
                info.container_id = _extract_container_id()
                return info

    # Check environment variables
    container_env = os.environ.get("container", "")
    if container_env:
        info.is_container = True
        if container_env.lower() == "docker":
            info.container_type = "docker"
        elif container_env.lower() == "lxc":
            info.container_type = "lxc"
        elif container_env.lower() == "podman":
            info.container_type = "podman"
        else:
            info.container_type = container_env if container_env else "unknown"
        info.container_id = _extract_container_id()
        return info

    docker_container_env = os.environ.get("DOCKER_CONTAINER", "")
    if docker_container_env:
        info.is_container = True
        info.container_type = "docker"
        info.container_id = _extract_container_id()
        return info

    # Check /proc/self/mountinfo for overlayfs (common in containers)
    mountinfo = _read_file("/proc/self/mountinfo")
    if mountinfo:
        for line in mountinfo.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                # Field index 2 (0-based after optional fields) contains filesystem type
                # The mountinfo format has: mount_id, parent_id, major:minor, root, mount_point, ...
                # Check for overlay in the line
                if "overlay" in line and "/ " in line:
                    info.is_container = True
                    info.container_type = info.container_type if info.container_type != "none" else "unknown"
                    info.container_id = _extract_container_id()
                    return info

    # Check /proc/1/sched for container init process name
    sched = _read_file("/proc/1/sched")
    if sched:
        first_line = sched.splitlines()[0] if sched.strip() else ""
        # On host, pid 1 is usually systemd, init, or upstart
        # In containers, it is often bash, sh, node, python, tini, etc.
        host_inits = {"systemd", "init", "upstart", "sysvinit", "openrc"}
        proc_name = first_line.split()[0] if first_line else ""
        if proc_name and proc_name not in host_inits:
            # Not definitive, but suggestive
            info.is_container = True
            if info.container_type == "none":
                info.container_type = "unknown"

    return info


def _get_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return os.environ.get("HOSTNAME", "unknown")


def _extract_container_id() -> str:
    """Try to extract the container ID from cgroup or hostname."""
    cgroup = _read_file("/proc/1/cgroup")
    if cgroup:
        for line in cgroup.strip().splitlines():
            parts = line.split("/")
            if parts:
                last = parts[-1].strip()
                # Docker container IDs are 64-char hex strings
                if len(last) >= 12 and all(c in "0123456789abcdef" for c in last):
                    return last[:12]
    # Fall back to hostname (Docker often uses container ID as hostname)
    hostname = _get_hostname()
    if len(hostname) == 12 and all(c in "0123456789abcdef" for c in hostname):
        return hostname
    if len(hostname) == 64 and all(c in "0123456789abcdef" for c in hostname):
        return hostname[:12]
    return ""


def enumerate_capabilities() -> list[str]:
    """Read /proc/self/status CapEff line and decode to capability names."""
    if not _is_linux():
        return []

    status = _read_file("/proc/self/status")
    if not status:
        return []

    cap_eff_hex = ""
    for line in status.strip().splitlines():
        if line.startswith("CapEff:"):
            parts = line.split()
            if len(parts) >= 2:
                cap_eff_hex = parts[1]
                break

    if not cap_eff_hex:
        return []

    try:
        cap_bits = int(cap_eff_hex, 16)
    except ValueError:
        logger.warning("Failed to parse CapEff hex value: %s", cap_eff_hex)
        return []

    caps: list[str] = []
    for bit, name in CAPABILITY_NAMES.items():
        if cap_bits & (1 << bit):
            caps.append(name)

    return sorted(caps)


def _decode_cap_eff_hex(hex_str: str) -> int:
    """Decode CapEff hex string to integer."""
    try:
        return int(hex_str, 16)
    except ValueError:
        return 0


def check_escape_vectors() -> list[EscapeFinding]:
    """Detect container misconfigurations that could allow escape.

    This function only reports findings. It NEVER attempts exploitation.
    """
    findings: list[EscapeFinding] = []

    if not _is_linux():
        return findings

    container_info = detect_container()
    if not container_info.is_container:
        # Not in a container, so escape vectors are not relevant
        # but still report a few host-level checks
        return findings

    _check_privileged_mode(findings)
    _check_docker_socket(findings)
    _check_host_pid_namespace(findings)
    _check_host_network_namespace(findings)
    _check_mounted_host_filesystems(findings)
    _check_suid_binaries(findings)
    _check_world_writable_paths(findings)
    _check_kernel_cves(findings)

    return findings


def _check_privileged_mode(findings: list[EscapeFinding]) -> None:
    """Check if the container is running in privileged mode (all capabilities)."""
    caps = enumerate_capabilities()
    if not caps:
        return

    # If the container has almost all capabilities, it is likely privileged
    total_known = len(CAPABILITY_NAMES)
    if len(caps) >= total_known - 2:
        # Allow for 1-2 missing caps due to kernel version differences
        findings.append(EscapeFinding(
            vector="privileged_mode",
            severity="critical",
            description="Container appears to be running in privileged mode",
            detail=f"Has {len(caps)}/{total_known} capabilities including CAP_SYS_ADMIN"
        ))
    elif "CAP_SYS_ADMIN" in caps:
        findings.append(EscapeFinding(
            vector="cap_sys_admin",
            severity="high",
            description="Container has CAP_SYS_ADMIN capability",
            detail="CAP_SYS_ADMIN grants broad system access and is a common escape vector"
        ))

    if "CAP_SYS_PTRACE" in caps:
        findings.append(EscapeFinding(
            vector="cap_sys_ptrace",
            severity="high",
            description="Container has CAP_SYS_PTRACE capability",
            detail="CAP_SYS_PTRACE can be used to inject code into host processes from shared PID namespace"
        ))

    if "CAP_NET_RAW" in caps:
        findings.append(EscapeFinding(
            vector="cap_net_raw",
            severity="medium",
            description="Container has CAP_NET_RAW capability",
            detail="CAP_NET_RAW allows raw socket access, useful for network sniffing and spoofing"
        ))

    if "CAP_SYS_MODULE" in caps:
        findings.append(EscapeFinding(
            vector="cap_sys_module",
            severity="critical",
            description="Container has CAP_SYS_MODULE capability",
            detail="CAP_SYS_MODULE allows loading kernel modules, trivial host escape"
        ))

    if "CAP_DAC_READ_SEARCH" in caps:
        findings.append(EscapeFinding(
            vector="cap_dac_read_search",
            severity="medium",
            description="Container has CAP_DAC_READ_SEARCH capability",
            detail="CAP_DAC_READ_SEARCH bypasses file read permission checks"
        ))


def _check_docker_socket(findings: list[EscapeFinding]) -> None:
    """Check if the Docker socket is mounted into the container."""
    docker_sock = "/var/run/docker.sock"
    if os.path.exists(docker_sock):
        try:
            mode = os.stat(docker_sock).st_mode
            if stat.S_ISSOCK(mode):
                findings.append(EscapeFinding(
                    vector="docker_socket",
                    severity="critical",
                    description="Docker socket is mounted in the container",
                    detail=f"{docker_sock} is accessible as a socket, allowing unrestricted Docker API access"
                ))
        except OSError:
            pass

    # Also check for podman socket
    podman_sock = "/var/run/podman/podman.sock"
    if os.path.exists(podman_sock):
        try:
            mode = os.stat(podman_sock).st_mode
            if stat.S_ISSOCK(mode):
                findings.append(EscapeFinding(
                    vector="podman_socket",
                    severity="critical",
                    description="Podman socket is mounted in the container",
                    detail=f"{podman_sock} is accessible as a socket, allowing unrestricted container management"
                ))
        except OSError:
            pass


def _check_host_pid_namespace(findings: list[EscapeFinding]) -> None:
    """Check if the container shares the host PID namespace."""
    sched = _read_file("/proc/1/sched")
    if sched is None:
        return

    first_line = sched.splitlines()[0] if sched.strip() else ""
    if not first_line:
        return

    # If pid 1 is a standard host init, we share the PID namespace
    host_inits = {"systemd", "init", "upstart", "sysvinit", "openrc"}
    proc_name = first_line.split()[0] if first_line else ""

    if proc_name in host_inits:
        findings.append(EscapeFinding(
            vector="host_pid_namespace",
            severity="high",
            description="Container shares the host PID namespace",
            detail=f"PID 1 is {proc_name}, indicating host PID namespace is shared"
        ))

    # Also check /proc/1/cgroup vs /proc/self/cgroup
    cgroup_1 = _read_file("/proc/1/cgroup")
    cgroup_self = _read_file("/proc/self/cgroup")
    if cgroup_1 and cgroup_self and cgroup_1 == cgroup_self:
        # Same cgroup mapping does not necessarily mean shared PID ns
        # but combined with the sched check it is informative
        pass


def _check_host_network_namespace(findings: list[EscapeFinding]) -> None:
    """Check if the container shares the host network namespace."""
    # Compare /proc/self/net and /proc/1/net
    # If they point to the same inode, we share the network namespace
    try:
        self_net = os.stat("/proc/self/net/dev")
        pid1_net = os.stat("/proc/1/net/dev")
        if self_net.st_ino == pid1_net.st_ino:
            findings.append(EscapeFinding(
                vector="host_network_namespace",
                severity="high",
                description="Container shares the host network namespace",
                detail="Network namespace of container matches host (PID 1), enabling network-level attacks"
            ))
    except (OSError, IOError):
        pass

    # Alternative check: if the container has full network access with host IP
    try:
        self_ns = os.stat("/proc/self/ns/net")
        pid1_ns = os.stat("/proc/1/ns/net")
        if self_ns.st_ino == pid1_ns.st_ino:
            findings.append(EscapeFinding(
                vector="host_network_namespace",
                severity="high",
                description="Container shares the host network namespace",
                detail="Network namespace inode matches PID 1, confirming shared network namespace"
            ))
    except (OSError, IOError):
        pass


def _check_mounted_host_filesystems(findings: list[EscapeFinding]) -> None:
    """Check for host filesystems mounted into the container."""
    mountinfo = _read_file("/proc/self/mountinfo")
    if not mountinfo:
        return

    suspicious_mount_points = ("/host", "/mnt/host", "/hostfs", "/host_root")
    critical_mount_sources = ("ext4", "xfs", "btrfs")

    for line in mountinfo.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue

        # mountinfo format: mount_id parent_id major:minor root mount_point options ...
        # Find the mount point (field index 4 after the optional fields marker)
        # The separator is a space-hyphen-space for optional fields
        try:
            sep_idx = parts.index("-")
            mount_point = parts[sep_idx + 2] if len(parts) > sep_idx + 2 else ""
            fs_type = parts[sep_idx + 1] if len(parts) > sep_idx + 1 else ""
            mount_source = parts[sep_idx - 1] if sep_idx > 0 else ""
        except (ValueError, IndexError):
            # Fallback: try to parse with a simpler approach
            # Field 4 is usually the mount point in standard format
            mount_point = parts[4] if len(parts) > 4 else ""
            fs_type = ""
            mount_source = ""

        # Check for suspicious mount points
        if mount_point in suspicious_mount_points:
            findings.append(EscapeFinding(
                vector="host_filesystem_mount",
                severity="critical",
                description="Host filesystem is mounted inside the container",
                detail=f"Mount point: {mount_point} - this provides full access to host files"
            ))

        # Check if root filesystem is a host device (not overlay)
        if mount_point == "/" and fs_type in critical_mount_sources:
            findings.append(EscapeFinding(
                vector="host_root_mount",
                severity="critical",
                description="Host root filesystem is mounted as container root",
                detail=f"Root mount uses {fs_type}, likely a direct host filesystem mount rather than overlay"
            ))

        # Check for /etc/hostname being a bind mount from host
        if mount_point == "/etc/hostname":
            # This is normal in Docker, but worth noting
            pass

        # Check for / mounted from a real block device
        if mount_point == "/" and mount_source.startswith("/dev/"):
            # This might be a host disk directly mounted
            pass


def _check_suid_binaries(findings: list[EscapeFinding]) -> None:
    """Find SUID binaries that could be used for privilege escalation."""
    try:
        result = subprocess.run(
            ["find", "/", "-perm", "-4000", "-type", "f"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            suid_binaries = result.stdout.strip().splitlines()
            # Limit to 50
            suid_binaries = suid_binaries[:50]
            count = len(suid_binaries)

            # Known dangerous SUID binaries
            dangerous_suids = {
                "/usr/bin/sudo", "/usr/bin/su", "/bin/su",
                "/usr/bin/newgrp", "/usr/bin/chsh", "/usr/bin/chfn",
                "/usr/bin/gpasswd", "/usr/bin/passwd",
                "/usr/bin/mount", "/usr/bin/umount",
                "/usr/bin/pkexec", "/usr/libexec/polkit-agent-helper-1",
                "/usr/bin/nmap", "/usr/bin/vim", "/usr/bin/find",
                "/usr/bin/bash", "/usr/bin/sh", "/bin/bash", "/bin/sh",
                "/usr/bin/python", "/usr/bin/python3",
                "/usr/bin/perl", "/usr/bin/ruby",
                "/usr/bin/cp", "/usr/bin/mv",
            }

            dangerous_found = [b for b in suid_binaries if b in dangerous_suids]
            if dangerous_found:
                findings.append(EscapeFinding(
                    vector="dangerous_suid_binaries",
                    severity="high",
                    description=f"Found {len(dangerous_found)} known-dangerous SUID binaries",
                    detail=f"Dangerous SUID: {', '.join(dangerous_found[:10])}"
                ))

            if count > 20:
                findings.append(EscapeFinding(
                    vector="excessive_suid_binaries",
                    severity="medium",
                    description=f"Excessive number of SUID binaries found ({count})",
                    detail="Many SUID binaries increase the attack surface for privilege escalation"
                ))
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass


def _check_world_writable_paths(findings: list[EscapeFinding]) -> None:
    """Check for world-writable directories that should not be."""
    sensitive_dirs = ["/etc", "/var", "/tmp", "/root", "/opt", "/usr/local/bin"]
    world_writable: list[str] = []

    for dir_path in sensitive_dirs:
        if not os.path.isdir(dir_path):
            continue
        try:
            st = os.stat(dir_path)
            if st.st_mode & stat.S_IWOTH:
                world_writable.append(dir_path)
        except (OSError, IOError):
            continue

    if world_writable:
        severity = "high" if "/root" in world_writable or "/etc" in world_writable else "medium"
        findings.append(EscapeFinding(
            vector="world_writable_paths",
            severity=severity,
            description=f"Found {len(world_writable)} world-writable sensitive directories",
            detail=f"World-writable: {', '.join(world_writable)}"
        ))


def _check_kernel_cves(findings: list[EscapeFinding]) -> None:
    """Check kernel version against known container CVEs."""
    version_content = _read_file("/proc/version")
    if not version_content:
        return

    # Extract kernel version number
    # Typical format: Linux version 5.15.0-91-generic ...
    version_str = version_content.strip()
    parts = version_str.split()
    kernel_version = ""
    for part in parts:
        if part[0].isdigit() and "." in part:
            kernel_version = part.split("-")[0]  # Strip -generic etc.
            break

    if not kernel_version:
        return

    for vuln_prefix, cve_id, description in KNOWN_CONTAINER_CVES:
        if kernel_version.startswith(vuln_prefix):
            findings.append(EscapeFinding(
                vector="kernel_cve",
                severity="high",
                description=f"Kernel version {kernel_version} may be affected by {cve_id}",
                detail=description
            ))

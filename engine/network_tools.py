"""Network scanning tools for Mythos operative mode.

For authorized security testing only. All functions require explicit
authorization via the ``authorized`` parameter.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Hostname validation: allow domain names, IPv4 -- block shell metacharacters
_HOSTNAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*$"
)
_DNS_RECORD_TYPES = frozenset({"A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "PTR"})

# Common port-to-service mapping
_PORT_MAP: dict[int, str] = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    143: "imap",
    443: "https",
    445: "smb",
    993: "imaps",
    995: "pop3s",
    1433: "mssql",
    1521: "oracle",
    3306: "mysql",
    3389: "rdp",
    5432: "postgres",
    5672: "amqp",
    6379: "redis",
    8080: "http-proxy",
    8443: "https-alt",
    9200: "elasticsearch",
    27017: "mongodb",
    27018: "mongodb",
}


@dataclass
class PortInfo:
    port: int
    state: str  # open / closed / filtered
    service: str
    banner: str


@dataclass
class ServiceInfo:
    port: int
    service: str
    version: str
    banner: str


@dataclass
class DNSInfo:
    hostname: str
    addresses: list[str] = field(default_factory=list)
    cname: str = ""
    mx_records: list[str] = field(default_factory=list)


def _require_authorization(authorized: bool) -> None:
    if not authorized:
        raise RuntimeError("Network scanning requires authorization")


def _validate_hostname(name: str) -> str:
    """Reject hostnames with shell metacharacters or invalid DNS names.

    Prevents argument injection in subprocess calls to dig/nslookup/whois.
    Uses ipaddress for strict IP validation and RFC 1035 hostname rules.
    """
    if not name or not isinstance(name, str):
        raise ValueError("Hostname must be a non-empty string")
    if len(name) > 253:
        raise ValueError(f"Hostname too long ({len(name)} chars, max 253): {name!r}")
    # Strip bracketed IPv6 notation like [::1]
    check = name
    if check.startswith("[") and check.endswith("]"):
        check = check[1:-1]
    # Try strict IP validation first (handles IPv4, IPv6, IPv4-mapped)
    try:
        ipaddress.ip_address(check)
        return name
    except ValueError:
        pass
    # Not an IP -- validate as DNS hostname per RFC 1035
    if not _HOSTNAME_RE.match(check):
        raise ValueError(f"Invalid hostname (possible injection): {name!r}")
    return name


def port_scan(
    host: str,
    ports: list[int],
    timeout: float = 2.0,
    authorized: bool = True,
) -> list[PortInfo]:
    """TCP connect scan against *host* for each port in *ports*.

    Returns a list of :class:`PortInfo` results. Open ports include a
    best-effort banner grab (up to 256 bytes).
    """
    _require_authorization(authorized)
    _validate_hostname(host)

    results: list[PortInfo] = []
    for port in ports:
        info = PortInfo(
            port=port,
            state="closed",
            service=_PORT_MAP.get(port, "unknown"),
            banner="",
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            code = sock.connect_ex((host, port))
            if code == 0:
                info.state = "open"
                # Banner grab
                try:
                    sock.settimeout(timeout / 2)
                    data = sock.recv(256)
                    if data:
                        info.banner = data.decode("utf-8", errors="replace").strip()
                except (socket.timeout, OSError):
                    pass
            else:
                info.state = "closed"
        except socket.timeout:
            info.state = "filtered"
        except OSError as exc:
            logger.debug("port_scan %s:%d error: %s", host, port, exc)
            info.state = "filtered"
        finally:
            try:
                sock.close()
            except OSError:
                pass
        results.append(info)

    return results


def service_detect(
    host: str,
    port: int,
    timeout: float = 3.0,
    authorized: bool = True,
) -> ServiceInfo:
    """Probe a single port for service and version information."""
    _require_authorization(authorized)

    service = _PORT_MAP.get(port, "unknown")
    version = ""
    banner = ""

    # Choose probe based on well-known service
    if port in (80, 8080, 8443, 443):
        probe = b"GET / HTTP/1.0\r\n\r\n"
    elif port == 25:
        probe = b"EHLO mythos\r\n"
    else:
        probe = b"\r\n"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        sock.sendall(probe)
        sock.settimeout(timeout)
        data = sock.recv(1024)
        if data:
            banner = data.decode("utf-8", errors="replace").strip()
    except OSError as exc:
        logger.debug("service_detect %s:%d error: %s", host, port, exc)
    finally:
        try:
            sock.close()
        except OSError:
            pass

    # Parse banner for service/version hints
    if banner:
        lower = banner.lower()
        if "ssh" in lower:
            service = "ssh"
            # Typical: "SSH-2.0-OpenSSH_8.9p1"
            parts = banner.split("-")
            for part in parts:
                if "openssh" in part.lower() or "dropbear" in part.lower():
                    version = part.strip()
                    break
        elif "http" in lower:
            service = "http" if port != 443 else "https"
            # First line often: HTTP/1.1 200 OK
            first_line = banner.split("\n")[0].strip()
            if "server:" in lower:
                for line in banner.split("\n"):
                    if line.lower().startswith("server:"):
                        version = line.split(":", 1)[1].strip()
                        break
            if not version and first_line:
                version = first_line
        elif "smtp" in lower or "220" in lower and port == 25:
            service = "smtp"
            version = banner.split("\n")[0].strip()
        elif "ftp" in lower or port == 21:
            service = "ftp"
            version = banner.split("\n")[0].strip()
        elif "redis" in lower or port == 6379:
            service = "redis"
            version = banner.strip()

    return ServiceInfo(port=port, service=service, version=version, banner=banner)


def dns_lookup(hostname: str, record_type: str = "A") -> DNSInfo:
    """Resolve DNS information for *hostname*.

    Uses :func:`socket.getaddrinfo` for A/AAAA records. Falls back to
    ``nslookup`` or ``dig`` for CNAME and MX records when available.
    """
    _validate_hostname(hostname)
    if record_type.upper() not in _DNS_RECORD_TYPES:
        raise ValueError(f"Invalid DNS record type: {record_type!r}")
    info = DNSInfo(hostname=hostname)

    # Basic A/AAAA resolution via stdlib
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for family, _type, _proto, _canonname, sockaddr in addr_infos:
            addr = sockaddr[0]
            if addr not in info.addresses:
                info.addresses.append(addr)
    except socket.gaierror as exc:
        logger.debug("dns_lookup getaddrinfo error for %s: %s", hostname, exc)

    # CNAME / MX via external tools
    if record_type.upper() in ("CNAME", "MX"):
        _dns_external(hostname, record_type, info)

    return info


def _dns_external(hostname: str, record_type: str, info: DNSInfo) -> None:
    """Attempt CNAME/MX lookup via ``dig`` or ``nslookup``."""
    record_upper = record_type.upper()

    # Try dig first (more widely available on Linux)
    try:
        result = subprocess.run(
            ["dig", "+short", record_upper, hostname],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if record_upper == "CNAME" and lines:
                info.cname = lines[0].rstrip(".")
            elif record_upper == "MX":
                for line in lines:
                    # dig MX +short returns "priority mail.server."
                    parts = line.split()
                    if len(parts) >= 2:
                        info.mx_records.append(parts[1].rstrip("."))
                    else:
                        info.mx_records.append(line.rstrip("."))
            return
    except FileNotFoundError:
        logger.debug("dig not found, trying nslookup")
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("dig failed: %s", exc)

    # Fallback to nslookup
    try:
        result = subprocess.run(
            ["nslookup", "-type=" + record_upper.lower(), hostname],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.splitlines():
                line_lower = line.lower().strip()
                if record_upper == "CNAME" and "canonical name" in line_lower:
                    parts = line.split("=")
                    if len(parts) >= 2:
                        info.cname = parts[-1].strip().rstrip(".")
                elif record_upper == "MX" and "mail exchanger" in line_lower:
                    parts = line.split("=")
                    if len(parts) >= 2:
                        info.mx_records.append(parts[-1].strip().rstrip("."))
    except FileNotFoundError:
        logger.debug("nslookup not found, CNAME/MX unavailable")
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("nslookup failed: %s", exc)


def lan_discover(
    timeout: float = 2.0,
    authorized: bool = True,
) -> dict:
    """Discover LAN hosts and network interfaces.

    Delegates to :mod:`mythos_cli.network_scanner` when available.
    """
    _require_authorization(authorized)

    result: dict = {"interfaces": [], "hosts": []}

    try:
        from mythos_cli.network_scanner import get_interfaces, scan_network

        try:
            result["interfaces"] = get_interfaces() or []
        except Exception as exc:
            logger.debug("lan_discover get_interfaces error: %s", exc)

        try:
            result["hosts"] = scan_network(timeout=timeout) or []
        except Exception as exc:
            logger.debug("lan_discover scan_network error: %s", exc)
    except ImportError:
        logger.debug("mythos_cli.network_scanner not available for LAN discovery")

    return result


def whois_lookup(
    target: str,
    authorized: bool = True,
) -> str:
    """Run ``whois`` against *target* and return the raw output."""
    _require_authorization(authorized)
    _validate_hostname(target)

    try:
        result = subprocess.run(
            ["whois", target],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout or ""
    except FileNotFoundError:
        logger.debug("whois command not found")
        return "whois not available"
    except subprocess.TimeoutExpired:
        logger.debug("whois lookup timed out for %s", target)
        return "whois not available"
    except OSError as exc:
        logger.debug("whois error: %s", exc)
        return "whois not available"

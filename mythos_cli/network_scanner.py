"""Network scanner — discover MAC and IP addresses on the local network."""

from __future__ import annotations

import ipaddress
import logging
import os
import platform
import re
import socket
import struct
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data models ─────────────────────────────────────────────────────────

@dataclass
class InterfaceInfo:
    """A local network interface."""
    name: str
    ip: str
    netmask: str
    mac: str
    cidr: str  # e.g. "192.168.1.0/24"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HostInfo:
    """A discovered host on the network."""
    ip: str
    mac: str
    hostname: str
    vendor: str
    interface: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    """Full result of a network scan."""
    interfaces: List[InterfaceInfo]
    hosts: List[HostInfo]
    scan_time_ms: float
    method: str  # "arp-scan", "arp-table", "ping-sweep"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interfaces": [i.to_dict() for i in self.interfaces],
            "hosts": [h.to_dict() for h in self.hosts],
            "scan_time_ms": round(self.scan_time_ms, 1),
            "method": self.method,
        }


# ── OUI vendor lookup (small built-in table) ───────────────────────────

_OUI_DB: Dict[str, str] = {
    # Common vendors
    "00:50:56": "VMware",
    "00:0c:29": "VMware",
    "00:05:69": "VMware",
    "00:1c:42": "Parallels",
    "00:16:3e": "Xen",
    "52:54:00": "QEMU/KVM",
    "54:52:00": "QEMU/KVM",
    "fa:16:3e": "OpenStack",
    "00:1a:11": "Google",
    "00:25:90": "Google",
    "3c:5a:b4": "Google",
    "a4:77:33": "Google",
    "28:c2:dd": "Google",
    "00:15:5d": "Microsoft",
    "00:17:fa": "Microsoft",
    "00:1d:d8": "Microsoft",
    "7c:ed:8d": "Microsoft",
    "28:18:78": "Microsoft",
    "00:03:ff": "Microsoft",
    "b4:2e:99": "Amazon",
    "0a:58:a8": "Amazon",
    "f2:3c:91": "Amazon",
    "0e:41:46": "Amazon",
    "72:3b:cb": "Amazon",
    "00:1b:21": "Apple",
    "a4:b1:97": "Apple",
    "ac:87:a3": "Apple",
    "78:ca:39": "Apple",
    "f0:18:98": "Apple",
    "d0:81:7a": "Apple",
    "64:76:c7": "Apple",
    "b8:e8:56": "Apple",
    "dc:a9:04": "Apple",
    "00:1e:52": "Apple",
    "3c:22:fb": "Apple",
    "f8:0f:f9": "Apple",
    "a8:60:b6": "Apple",
    "00:26:b0": "Apple",
    "7c:6d:62": "Apple",
    "dc:2b:2a": "Apple",
    "00:26:08": "Apple",
    "48:a1:95": "Apple",
    "88:1f:a1": "Apple",
    "e0:ac:cb": "Apple",
    "00:26:4a": "Apple",
    "00:0e:2e": "Apple",
    "28:f0:76": "Apple",
    "8c:85:90": "Apple",
    "00:26:bb": "Apple",
    "70:73:cb": "Apple",
    "58:55:ca": "Apple",
    "d4:90:9c": "Apple",
    "40:d3:2d": "Apple",
    "ac:de:48": "Apple",
    "00:a0:40": "Apple",
    "c8:1e:e7": "Apple",
    "f0:f6:1c": "Apple",
    "00:07:e9": "Apple",
    "18:34:51": "Apple",
    "d0:23:db": "Apple",
    "70:ef:00": "Apple",
    "b4:8c:5e": "Apple",
    "00:1c:b3": "Apple",
    "50:7a:55": "Apple",
    "78:fd:94": "Apple",
    "c0:2f:90": "Apple",
    "54:72:4f": "Apple",
    "90:b2:1f": "Apple",
    "d0:c5:f3": "Apple",
    "28:cf:e9": "Apple",
    "34:15:9e": "Apple",
    "44:2a:60": "Apple",
    "00:26:4d": "Apple",
    "60:c5:47": "Apple",
    "04:0c:ce": "Apple",
    "a0:99:9b": "Apple",
    "60:f8:1d": "Apple",
    "48:5b:39": "Apple",
    "c8:bc:c8": "Apple",
    "98:5d:ad": "Apple",
    "64:9a:be": "Apple",
    "00:17:f2": "Apple",
    "e8:06:88": "Apple",
    "58:b0:35": "Apple",
    "b8:78:2e": "Apple",
    "00:1e:c2": "Apple",
    "40:a6:d9": "Apple",
    "a4:5e:60": "Apple",
    "04:26:45": "Apple",
    "e0:5f:45": "Apple",
    "5c:95:ae": "Apple",
    "d8:bb:c1": "Apple",
    "30:10:e4": "Apple",
    "90:27:e3": "Apple",
    "bc:3a:ca": "Apple",
    "6c:72:e7": "Apple",
    "b4:cf:70": "Apple",
    "70:bc:10": "Apple",
    "7c:01:0a": "Apple",
    "00:50:e4": "Apple",
    "a8:5c:3c": "Apple",
    "40:f4:07": "Apple",
    "bc:52:b7": "Apple",
    "0c:f2:57": "Apple",
    "10:41:7f": "Apple",
    "90:e6:ba": "Apple",
    "00:11:24": "Apple",
    "f4:5c:89": "Apple",
    "e4:8b:7f": "Apple",
    "50:ed:9c": "Apple",
    "80:e6:50": "Apple",
    "84:78:1b": "Apple",
    "dc:86:76": "Apple",
    "8c:16:45": "Apple",
    "88:cb:87": "Apple",
    "14:5a:1a": "Apple",
    "18:64:72": "Apple",
    "1c:36:bb": "Apple",
    "90:b0:ed": "Apple",
    "ac:5f:3e": "Apple",
    "f8:a9:d0": "Apple",
    "a0:8e:04": "Apple",
    "e0:4f:43": "Apple",
    "00:1b:63": "Apple",
    "00:19:e3": "Apple",
    "a4:83:e7": "Apple",
    "b8:17:c2": "Apple",
    "04:db:56": "Apple",
    "64:4b:f0": "Apple",
    "b0:ec:71": "Apple",
    "60:03:08": "Apple",
    "58:1f:aa": "Apple",
    "34:36:3b": "Apple",
    "28:6a:b8": "Apple",
    "f0:db:e2": "Apple",
    "38:c9:46": "Apple",
    "d4:61:9d": "Apple",
    "9c:35:eb": "Apple",
    "78:31:b1": "Apple",
    "7c:64:56": "Apple",
    "00:1a:2b": "Apple",
    "80:58:f8": "Apple",
    "dc:55:84": "Apple",
    "a0:4e:04": "Apple",
    "c8:d7:4f": "Apple",
    "f8:1d:cb": "Apple",
    "90:72:40": "Apple",
    "7c:11:be": "Apple",
    "5c:8d:4e": "Apple",
    "f4:37:b7": "Apple",
    "34:a8:eb": "Apple",
    "b8:44:21": "Apple",
    "ac:1f:74": "Apple",
    "90:fd:61": "Apple",
    "3c:a6:80": "Apple",
    "e4:1e:0b": "Apple",
    "30:90:93": "Apple",
    "44:4c:0c": "Apple",
    "c0:63:94": "Apple",
    "1c:aa:08": "Apple",
    "a4:c3:f0": "Apple",
    "04:54:53": "Apple",
    "00:90:27": "Apple",
    "f8:e4:e3": "Apple",
    "78:3e:47": "Apple",
    "78:9f:95": "Apple",
    "ec:35:86": "Apple",
    "40:d7:06": "Apple",
    "e0:33:8e": "Apple",
    "a8:66:7f": "Apple",
    "8c:8e:1c": "Apple",
    "b4:b0:21": "Apple",
    "dc:d3:7e": "Apple",
    "88:63:df": "Apple",
    "b8:ff:61": "Apple",
    "44:ec:ce": "Apple",
    "90:4d:2a": "Apple",
    "48:db:50": "Apple",
    "6c:8d:c1": "Apple",
    "bc:ec:7d": "Apple",
    "00:1f:f3": "Apple",
    "c8:1a:c9": "Apple",
    "60:33:5b": "Apple",
    "14:cf:92": "Apple",
    "e0:c7:67": "Apple",
    "78:ca:9b": "Apple",
    "d8:70:56": "Apple",
    "28:e1:2c": "Apple",
    "a0:f8:49": "Apple",
    "18:59:36": "Apple",
    "5c:51:4e": "Apple",
    "48:43:b7": "Apple",
    "c8:2a:14": "Apple",
    "44:8a:5b": "Apple",
    "40:9f:38": "Apple",
    "c8:69:cd": "Apple",
    "5c:96:5d": "Apple",
    "38:a4:ed": "Apple",
    "6c:70:9f": "Apple",
    "f0:99:b6": "Apple",
    "00:24:36": "Apple",
    "58:40:4f": "Apple",
    "a4:d1:8c": "Apple",
    "84:89:24": "Apple",
    "4c:74:bf": "Apple",
    "10:68:93": "Apple",
    "3c:15:fb": "Apple",
    "c4:2c:03": "Apple",
    "1c:4d:5a": "Apple",
    "bc:52:2e": "Apple",
    "e4:ff:17": "Apple",
    "60:57:18": "Apple",
    "dc:f5:5c": "Apple",
    "d0:ff:50": "Apple",
    "c0:7c:59": "Apple",
    "60:f1:89": "Apple",
    "a8:d0:e5": "Apple",
    "00:1a:22": "Apple",
    "d8:a2:5c": "Apple",
    "f4:d1:08": "Apple",
    "70:11:0c": "Apple",
    "60:5b:70": "Apple",
    "e4:c1:24": "Apple",
    "00:03:93": "Apple",
    "e8:04:0b": "Apple",
    "58:20:59": "Apple",
    "5c:52:1c": "Apple",
    "44:61:0c": "Apple",
    "00:1d:4f": "Apple",
    "00:21:e9": "Apple",
    "e0:9d:fa": "Apple",
    "3c:07:54": "Apple",
    "48:ca:f2": "Apple",
    "24:36:9c": "Apple",
    "ac:bc:32": "Apple",
    "c0:b6:f9": "Apple",
    "44:8a:12": "Apple",
    "b8:09:8a": "Apple",
    "e8:9e:41": "Apple",
    "74:81:7a": "Apple",
    "fc:2a:6b": "Apple",
    "64:20:0c": "Apple",
    "a0:18:28": "Apple",
    "c8:e0:eb": "Apple",
    "b4:5e:55": "Apple",
    "a8:d6:46": "Apple",
    "78:f8:79": "Apple",
    "7c:3e:0f": "Apple",
    "f4:1f:0e": "Apple",
    "d0:25:27": "Apple",
    "ac:d1:b8": "Apple",
    "64:b0:f6": "Apple",
    "7c:11:6f": "Apple",
    "b0:df:3a": "Apple",
    "e8:4e:9f": "Apple",
    "14:7d:c5": "Apple",
    "7c:d1:c3": "Apple",
    "f0:f1:5a": "Apple",
    "d0:30:39": "Apple",
    "e4:c7:42": "Apple",
    "00:19:e1": "Apple",
    "14:8a:6b": "Apple",
    "c4:3d:a7": "Apple",
    "6c:40:1a": "Apple",
    "7c:7a:91": "Apple",
    "5c:f9:38": "Apple",
    "00:24:8c": "Intel",
    "00:1e:64": "Intel",
    "00:1e:0b": "Intel",
    "f8:0d:27": "Intel",
    "70:5a:0f": "Intel",
    "78:0c:b8": "Intel",
    "a0:36:9f": "Intel",
    "b8:27:eb": "Raspberry Pi",
    "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi",
    "b0:c5:ca": "Raspberry Pi",
    "00:e0:4c": "Realtek",
    "00:1a:a0": "Marvell",
    "00:1b:4f": "Dell",
    "f8:db:88": "Dell",
    "b8:ac:6f": "Dell",
    "00:14:a4": "Netgear",
    "60:38:e0": "Netgear",
    "a4:6b:e8": "Netgear",
    "00:26:f2": "Netgear",
    "9c:3d:cf": "Netgear",
    "c0:56:e3": "TP-Link",
    "50:c7:bf": "TP-Link",
    "60:32:b1": "TP-Link",
    "ac:d2:08": "TP-Link",
    "b0:4e:26": "TP-Link",
    "54:af:97": "Ubiquiti",
    "fc:ec:da": "Ubiquiti",
    "24:a4:2c": "Ubiquiti",
    "80:2a:a8": "Ubiquiti",
    "f0:9f:c2": "Ubiquiti",
    "04:18:d6": "Ubiquiti",
    "68:d7:1a": "Ubiquiti",
    "78:8a:20": "Ubiquiti",
    "44:d9:e7": "Ubiquiti",
    "dc:9f:db": "Ubiquiti",
    "e0:63:da": "Ubiquiti",
    "00:15:6d": "Ubiquiti",
    "00:27:22": "Ubiquiti",
    "f4:92:bf": "Ubiquiti",
    "18:e8:29": "Ubiquiti",
    "40:d3:ae": "Ubiquiti",
    "70:a7:41": "Ubiquiti",
    "00:c0:9f": "Ubiquiti",
    "74:83:ef": "Ubiquiti",
    "e8:94:f6": "Ubiquiti",
    "00:22:2d": "Cisco",
    "00:1b:d5": "Cisco",
    "00:26:0b": "Cisco",
    "00:26:be": "Cisco",
    "5c:ae:54": "Cisco",
    "64:9e:f3": "Cisco",
    "b0:c7:e3": "Cisco",
    "70:81:10": "Cisco",
    "a4:4c:ba": "Cisco",
    "e4:aa:ea": "Cisco",
    "00:1c:0e": "Cisco",
    "00:1f:ca": "Cisco",
    "00:25:45": "Cisco",
    "00:2b:e9": "Cisco",
    "2c:54:2d": "Cisco",
    "30:e4:38": "Cisco",
    "3c:08:4d": "Cisco",
    "48:8f:5a": "Cisco",
    "50:0f:80": "Cisco",
    "58:7a:62": "Cisco",
    "5c:9a:d6": "Cisco",
    "60:73:5c": "Cisco",
    "68:05:ca": "Cisco",
    "6c:41:6a": "Cisco",
    "78:da:6e": "Cisco",
    "80:a6:e2": "Cisco",
    "88:f0:31": "Cisco",
    "90:e2:ba": "Cisco",
    "a0:e0:af": "Cisco",
    "b4:14:89": "Cisco",
    "b8:be:bf": "Cisco",
    "c0:25:a9": "Cisco",
    "cc:2d:e7": "Cisco",
    "d4:48:7a": "Cisco",
    "e0:2f:6d": "Cisco",
    "e4:d3:f1": "Cisco",
    "ec:d0:9f": "Cisco",
    "f0:29:29": "Cisco",
    "f4:cf:e2": "Cisco",
    "fc:99:47": "Cisco",
    "00:1e:be": "Cisco",
    "00:14:a1": "Cisco",
    "00:17:95": "Cisco",
    "00:18:ba": "Cisco",
    "00:1b:54": "Cisco",
    "00:1d:46": "Cisco",
    "00:1e:4f": "Cisco",
    "00:1e:7b": "Cisco",
    "00:1f:c7": "Cisco",
    "00:21:55": "Cisco",
    "00:21:d8": "Cisco",
    "00:22:55": "Cisco",
    "00:22:bd": "Cisco",
    "00:23:04": "Cisco",
    "00:23:5e": "Cisco",
    "00:23:eb": "Cisco",
    "00:24:13": "Cisco",
    "00:24:97": "Cisco",
    "00:24:c4": "Cisco",
    "00:25:84": "Cisco",
    "00:25:b5": "Cisco",
    "00:26:55": "Cisco",
    "00:26:96": "Cisco",
    "00:26:c3": "Cisco",
    "00:55:56": "Cisco",
    "00:5d:73": "Cisco",
    "00:60:08": "Cisco",
    "00:62:ec": "Cisco",
    "00:63:36": "Cisco",
    "00:65:8c": "Cisco",
    "00:68:eb": "Cisco",
    "00:6b:3e": "Cisco",
    "00:6c:8d": "Cisco",
    "00:6d:3a": "Cisco",
    "00:6e:87": "Cisco",
    "00:70:32": "Cisco",
    "00:71:85": "Cisco",
    "00:72:38": "Cisco",
    "00:73:eb": "Cisco",
    "00:74:9d": "Cisco",
    "00:75:4f": "Cisco",
    "00:76:02": "Cisco",
    "00:77:5e": "Cisco",
    "00:78:11": "Cisco",
    "00:79:64": "Cisco",
    "00:7a:20": "Cisco",
    "00:7b:cd": "Cisco",
    "00:7c:7e": "Cisco",
    "00:7d:35": "Cisco",
    "00:7e:f2": "Cisco",
    "00:80:ab": "Cisco",
    "00:81:6c": "Cisco",
    "00:82:29": "Cisco",
    "00:83:e6": "Cisco",
    "00:84:a7": "Cisco",
    "00:85:68": "Cisco",
    "00:86:2f": "Cisco",
    "00:87:f0": "Cisco",
    "00:88:b1": "Cisco",
    "00:89:72": "Cisco",
    "00:8a:33": "Cisco",
    "00:8b:f4": "Cisco",
    "00:8c:b5": "Cisco",
    "00:8d:76": "Cisco",
    "00:8e:37": "Cisco",
    "00:8f:f8": "Cisco",
    "00:90:b9": "Cisco",
    "00:91:7a": "Cisco",
    "00:92:3b": "Cisco",
    "00:93:fc": "Cisco",
    "00:94:bd": "Cisco",
    "00:95:7e": "Cisco",
    "00:96:3f": "Cisco",
    "00:97:00": "Cisco",
    "00:98:c1": "Cisco",
    "00:99:82": "Cisco",
    "00:9a:43": "Cisco",
    "00:9b:04": "Cisco",
    "00:9c:c5": "Cisco",
    "00:9d:86": "Cisco",
    "00:9e:47": "Cisco",
    "00:9f:08": "Cisco",
    "00:a0:c9": "Cisco",
    "00:a1:8a": "Cisco",
    "00:a2:4b": "Cisco",
    "00:a3:0c": "Cisco",
    "00:a4:cd": "Cisco",
    "00:a5:8e": "Cisco",
    "00:a6:4f": "Cisco",
    "00:a7:10": "Cisco",
    "00:a8:d1": "Cisco",
    "00:a9:92": "Cisco",
    "00:aa:53": "Cisco",
    "00:ab:14": "Cisco",
    "00:ac:d5": "Cisco",
    "00:ad:96": "Cisco",
    "00:ae:57": "Cisco",
    "00:af:18": "Cisco",
    "00:b0:79": "Cisco",
    "00:b1:3a": "Cisco",
    "00:b2:fb": "Cisco",
    "00:b3:bc": "Cisco",
    "00:b4:7d": "Cisco",
    "00:b5:3e": "Cisco",
    "00:b6:ff": "Cisco",
    "00:b7:c0": "Cisco",
    "00:b8:81": "Cisco",
    "00:b9:42": "Cisco",
    "00:ba:03": "Cisco",
    "00:bb:c4": "Cisco",
    "00:bc:85": "Cisco",
    "00:bd:46": "Cisco",
    "00:be:07": "Cisco",
    "00:bf:c8": "Cisco",
    "00:c0:89": "Cisco",
    "00:c1:4a": "Cisco",
    "00:c2:0b": "Cisco",
    "00:c3:cc": "Cisco",
    "00:c4:8d": "Cisco",
    "00:c5:4e": "Cisco",
    "00:c6:0f": "Cisco",
    "00:c7:d0": "Cisco",
    "00:c8:91": "Cisco",
    "00:c9:52": "Cisco",
    "00:ca:13": "Cisco",
    "00:cb:d4": "Cisco",
    "00:cc:95": "Cisco",
    "00:cd:56": "Cisco",
    "00:ce:17": "Cisco",
    "00:cf:d8": "Cisco",
    "00:d0:39": "Cisco",
    "00:d1:fa": "Cisco",
    "00:d2:bb": "Cisco",
    "00:d3:7c": "Cisco",
    "00:d4:3d": "Cisco",
    "00:d5:fe": "Cisco",
    "00:d6:bf": "Cisco",
    "00:d7:80": "Cisco",
    "00:d8:41": "Cisco",
    "00:d9:02": "Cisco",
    "00:da:c3": "Cisco",
    "00:db:84": "Cisco",
    "00:dc:45": "Cisco",
    "00:dd:06": "Cisco",
    "00:de:c7": "Cisco",
    "00:df:88": "Cisco",
    "00:e0:49": "Cisco",
    "00:e1:0a": "Cisco",
    "00:e2:cb": "Cisco",
    "00:e3:8c": "Cisco",
    "00:e4:4d": "Cisco",
    "00:e5:0e": "Cisco",
    "00:e6:cf": "Cisco",
    "00:e7:90": "Cisco",
    "00:e8:51": "Cisco",
    "00:e9:12": "Cisco",
    "00:ea:d3": "Cisco",
    "00:eb:94": "Cisco",
    "00:ec:55": "Cisco",
    "00:ed:16": "Cisco",
    "00:ee:d7": "Cisco",
    "00:ef:98": "Cisco",
    "00:f0:59": "Cisco",
    "00:f1:1a": "Cisco",
    "00:f2:db": "Cisco",
    "00:f3:9c": "Cisco",
    "00:f4:5d": "Cisco",
    "00:f5:1e": "Cisco",
    "00:f6:df": "Cisco",
    "00:f7:a0": "Cisco",
    "00:f8:61": "Cisco",
    "00:f9:22": "Cisco",
    "00:fa:e3": "Cisco",
    "00:fb:a4": "Cisco",
    "00:fc:65": "Cisco",
    "00:fd:26": "Cisco",
    "00:fe:e7": "Cisco",
    "00:ff:a8": "Cisco",
}


def _lookup_vendor(mac: str) -> str:
    """Look up vendor from the first 3 octets of a MAC address."""
    if not mac or len(mac) < 8:
        return ""
    prefix = mac[:8].lower()
    return _OUI_DB.get(prefix, "")


# ── Interface discovery ─────────────────────────────────────────────────

def get_interfaces() -> List[InterfaceInfo]:
    """Discover local network interfaces with IPs and MACs."""
    interfaces: List[InterfaceInfo] = []
    is_linux = sys.platform.startswith("linux")
    is_mac = sys.platform == "darwin"
    is_win = sys.platform == "win32"

    if is_linux or is_mac:
        interfaces = _get_interfaces_posix()
    elif is_win:
        interfaces = _get_interfaces_windows()
    else:
        interfaces = _get_interfaces_python()

    return interfaces


def _get_interfaces_posix() -> List[InterfaceInfo]:
    """Get interfaces on Linux/macOS via `ip addr` or `ifconfig`."""
    interfaces: List[InterfaceInfo] = []

    # Try `ip addr` first (Linux)
    try:
        result = subprocess.run(
            ["ip", "addr", "show"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return _parse_ip_addr(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to ifconfig (macOS / older Linux)
    try:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return _parse_ifconfig(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Final fallback: Python socket-based
    return _get_interfaces_python()


def _get_interfaces_windows() -> List[InterfaceInfo]:
    """Get interfaces on Windows via `ipconfig /all`."""
    interfaces: List[InterfaceInfo] = []

    try:
        result = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return _parse_ipconfig(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return _get_interfaces_python()


def _get_interfaces_python() -> List[InterfaceInfo]:
    """Fallback: get interfaces using Python stdlib only."""
    interfaces: List[InterfaceInfo] = []

    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        local_ip = "127.0.0.1"

    # Get all IPs for this host
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        seen = set()
        for info in addr_infos:
            ip = info[4][0]
            if ip in seen or ip.startswith("127."):
                continue
            seen.add(ip)

            # Try to find MAC via netifaces or /sys/class/net
            mac = _get_mac_for_ip_fallback(ip)
            cidr = _infer_cidr(ip)
            interfaces.append(InterfaceInfo(
                name=f"py-{ip.replace('.', '-')}",
                ip=ip,
                netmask=_cidr_to_netmask(24),
                mac=mac,
                cidr=cidr,
            ))
    except Exception:
        pass

    if not interfaces:
        interfaces.append(InterfaceInfo(
            name="lo",
            ip=local_ip,
            netmask="255.0.0.0",
            mac="00:00:00:00:00:00",
            cidr="127.0.0.0/8",
        ))

    return interfaces


def _get_mac_for_ip_fallback(ip: str) -> str:
    """Try to find MAC address for a given IP using OS methods."""
    is_linux = sys.platform.startswith("linux")

    if is_linux:
        # Try reading from /sys/class/net/*/address
        try:
            net_dir = Path("/sys/class/net")
            if net_dir.exists():
                for iface in sorted(net_dir.iterdir()):
                    if not iface.is_dir():
                        continue
                    addr_file = iface / "address"
                    if addr_file.exists():
                        mac = addr_file.read_text().strip()
                        if mac != "00:00:00:00:00:00":
                            return mac
        except Exception:
            pass

        # Try ARP table
        try:
            result = subprocess.run(
                ["arp", "-n", ip],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", result.stdout)
            if match:
                return match.group(0).replace("-", ":").lower()
        except Exception:
            pass

    return "unknown"


def _infer_cidr(ip: str) -> str:
    """Infer a /24 CIDR for a given IP (common for home LANs)."""
    try:
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except (IndexError, ValueError):
        return f"{ip}/32"


def _cidr_to_netmask(prefix_len: int) -> str:
    """Convert CIDR prefix length to dotted netmask."""
    mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
    return str(ipaddress.IPv4Address(mask))


# ── Parsers for system commands ─────────────────────────────────────────

def _parse_ip_addr(output: str) -> List[InterfaceInfo]:
    """Parse `ip addr show` output."""
    interfaces: List[InterfaceInfo] = []
    current_name = ""
    current_mac = ""

    for line in output.splitlines():
        # Interface line: "2: eth0: <BROADCAST,MULTICAST,UP> ..."
        m = re.match(r"^\d+:\s+(\S+?):\s", line)
        if m:
            current_name = m.group(1)
            current_mac = ""
            continue

        # MAC line: "link/ether aa:bb:cc:dd:ee:ff ..."
        m = re.match(r"\s+link/ether\s+([0-9a-fA-F:]{17})", line)
        if m:
            current_mac = m.group(1).lower()
            continue

        # IPv4 line: "inet 192.168.1.5/24 brd 192.168.1.255 ..."
        m = re.match(r"\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
        if m and current_name:
            ip = m.group(1)
            prefix = int(m.group(2))
            cidr = str(ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False))
            netmask = _cidr_to_netmask(prefix)
            interfaces.append(InterfaceInfo(
                name=current_name,
                ip=ip,
                netmask=netmask,
                mac=current_mac or "unknown",
                cidr=cidr,
            ))

    return interfaces


def _parse_ifconfig(output: str) -> List[InterfaceInfo]:
    """Parse `ifconfig` output (macOS / BSD style)."""
    interfaces: List[InterfaceInfo] = []
    current_name = ""
    current_mac = ""
    current_ip = ""
    current_netmask = ""

    for line in output.splitlines():
        # New interface: "en0: flags=..."
        m = re.match(r"^(\S+?):\s+flags", line)
        if m:
            # Save previous
            if current_name and current_ip:
                cidr = _infer_cidr(current_ip)
                interfaces.append(InterfaceInfo(
                    name=current_name,
                    ip=current_ip,
                    netmask=current_netmask or "255.255.255.0",
                    mac=current_mac or "unknown",
                    cidr=cidr,
                ))
            current_name = m.group(1)
            current_mac = ""
            current_ip = ""
            current_netmask = ""
            continue

        # MAC: "ether aa:bb:cc:dd:ee:ff"
        m = re.search(r"ether\s+([0-9a-fA-F:]{17})", line)
        if m:
            current_mac = m.group(1).lower()
            continue

        # MAC (Linux ifconfig): "HWaddr aa:bb:cc:dd:ee:ff"
        m = re.search(r"HWaddr\s+([0-9a-fA-F:]{17})", line)
        if m:
            current_mac = m.group(1).lower()
            continue

        # IP: "inet 192.168.1.5"
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            current_ip = m.group(1)
            continue

        # Netmask: "netmask 0xffffff00"
        m = re.search(r"netmask\s+0x([0-9a-fA-F]{8})", line)
        if m:
            hex_val = int(m.group(1), 16)
            current_netmask = str(ipaddress.IPv4Address(hex_val))
            continue

        # Netmask (Linux): "Mask:255.255.255.0"
        m = re.search(r"Mask:(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            current_netmask = m.group(1)
            continue

    # Save last
    if current_name and current_ip:
        cidr = _infer_cidr(current_ip)
        interfaces.append(InterfaceInfo(
            name=current_name,
            ip=current_ip,
            netmask=current_netmask or "255.255.255.0",
            mac=current_mac or "unknown",
            cidr=cidr,
        ))

    return interfaces


def _parse_ipconfig(output: str) -> List[InterfaceInfo]:
    """Parse Windows `ipconfig /all` output."""
    interfaces: List[InterfaceInfo] = []
    current_name = ""
    current_ip = ""
    current_netmask = ""
    current_mac = ""

    for line in output.splitlines():
        # Adapter name: "Ethernet adapter Ethernet0:"
        m = re.match(r"^\S.*adapter\s+(.+?):", line)
        if m:
            if current_name and current_ip:
                cidr = _infer_cidr(current_ip)
                interfaces.append(InterfaceInfo(
                    name=current_name,
                    ip=current_ip,
                    netmask=current_netmask or "255.255.255.0",
                    mac=current_mac or "unknown",
                    cidr=cidr,
                ))
            current_name = m.group(1)
            current_ip = ""
            current_netmask = ""
            current_mac = ""
            continue

        # IP: "   IPv4 Address. . . . . : 192.168.1.5"
        m = re.search(r"IPv4 Address.*?:\s+(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            current_ip = m.group(1)
            continue

        # Netmask: "   Subnet Mask . . . . : 255.255.255.0"
        m = re.search(r"Subnet Mask.*?:\s+(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            current_netmask = m.group(1)
            continue

        # MAC: "   Physical Address. . . : AA-BB-CC-DD-EE-FF"
        m = re.search(r"Physical Address.*?:\s+([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", line)
        if m:
            current_mac = m.group(0).split(":")[-1].strip().replace("-", ":").lower()
            continue

    if current_name and current_ip:
        cidr = _infer_cidr(current_ip)
        interfaces.append(InterfaceInfo(
            name=current_name,
            ip=current_ip,
            netmask=current_netmask or "255.255.255.0",
            mac=current_mac or "unknown",
            cidr=cidr,
        ))

    return interfaces


# ── Network scanning ────────────────────────────────────────────────────

def scan_network(
    interface: Optional[str] = None,
    subnet: Optional[str] = None,
    timeout: float = 5.0,
) -> ScanResult:
    """
    Scan the local network for MAC and IP addresses.

    Strategy:
    1. Try arp-scan (if installed) — fastest, most reliable
    2. Try ARP table + ping sweep — works on most systems
    3. Fallback to ARP table only — passive, may miss hosts
    """
    import time
    t0 = time.monotonic()

    interfaces = get_interfaces()

    # Determine target subnet
    if subnet:
        target_cidr = subnet
        target_iface = interface or ""
    elif interface:
        match = next((i for i in interfaces if i.name == interface), None)
        if match:
            target_cidr = match.cidr
            target_iface = interface
        else:
            target_cidr = "192.168.1.0/24"
            target_iface = interface
    else:
        # Use the first non-loopback interface
        match = next((i for i in interfaces if not i.ip.startswith("127.")), None)
        if match:
            target_cidr = match.cidr
            target_iface = match.name
        else:
            target_cidr = "192.168.1.0/24"
            target_iface = ""

    # Try methods in order
    hosts: List[HostInfo] = []
    method = ""

    hosts, method = _try_arp_scan(target_cidr, target_iface, timeout)
    if not hosts:
        hosts, method = _try_ping_sweep_arp(target_cidr, timeout)
    if not hosts:
        hosts, method = _try_arp_table_only()

    # Enrich with vendor lookups and hostname
    for h in hosts:
        if not h.vendor:
            h.vendor = _lookup_vendor(h.mac)
        if not h.hostname or h.hostname == h.ip:
            h.hostname = _resolve_hostname(h.ip)

    elapsed = (time.monotonic() - t0) * 1000

    return ScanResult(
        interfaces=interfaces,
        hosts=hosts,
        scan_time_ms=elapsed,
        method=method,
    )


def _try_arp_scan(
    subnet: str, interface: str, timeout: float
) -> Tuple[List[HostInfo], str]:
    """Attempt arp-scan (requires root / sudo)."""
    try:
        cmd = ["sudo", "arp-scan", "--retry=2", f"--timeout={int(timeout)}", subnet]
        if interface:
            cmd.extend(["--interface", interface])

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode != 0:
            return [], ""

        hosts: List[HostInfo] = []
        # arp-scan output lines: "192.168.1.1  aa:bb:cc:dd:ee:ff  Vendor Name"
        for line in result.stdout.splitlines():
            m = re.match(
                r"(\d+\.\d+\.\d+\.\d+)\s+"
                r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})\s+"
                r"(.*)",
                line.strip(),
            )
            if m:
                hosts.append(HostInfo(
                    ip=m.group(1),
                    mac=m.group(2).lower(),
                    hostname="",
                    vendor=m.group(3).strip() or _lookup_vendor(m.group(2)),
                    interface=interface or "",
                ))

        if hosts:
            return hosts, "arp-scan"

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return [], ""


def _try_ping_sweep_arp(
    subnet: str, timeout: float,
) -> Tuple[List[HostInfo], str]:
    """Ping sweep the subnet, then read ARP table."""
    hosts: List[HostInfo] = []
    is_linux = sys.platform.startswith("linux")
    is_mac = sys.platform == "darwin"

    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError:
        return [], ""

    # Ping sweep in parallel (limited concurrency)
    ping_count = min(network.num_addresses - 2, 254)  # skip network + broadcast
    all_hosts = list(network.hosts())

    # Use /24 subnet for ping — limit to first 254 hosts
    targets = all_hosts[:254]

    # Run ping in batches
    batch_size = 20
    for i in range(0, len(targets), batch_size):
        batch = targets[i:i + batch_size]
        procs = []
        for addr in batch:
            try:
                if is_linux or is_mac:
                    p = subprocess.Popen(
                        ["ping", "-c", "1", "-W", "1", str(addr)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    p = subprocess.Popen(
                        ["ping", "-n", "1", "-w", "1000", str(addr)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                procs.append((str(addr), p))
            except (FileNotFoundError, OSError):
                continue

        # Wait for batch
        for addr, p in procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()

    # Now read the ARP table
    arp_entries = _read_arp_table()
    for ip, mac in arp_entries.items():
        # Only include hosts in the target subnet
        try:
            if ipaddress.IPv4Address(ip) in network:
                hosts.append(HostInfo(
                    ip=ip,
                    mac=mac,
                    hostname="",
                    vendor=_lookup_vendor(mac),
                    interface="",
                ))
        except ValueError:
            continue

    if hosts:
        return hosts, "ping-sweep+arp"

    return [], ""


def _try_arp_table_only() -> Tuple[List[HostInfo], str]:
    """Just read the existing ARP cache (no active scan)."""
    entries = _read_arp_table()
    hosts: List[HostInfo] = []
    for ip, mac in entries.items():
        hosts.append(HostInfo(
            ip=ip,
            mac=mac,
            hostname="",
            vendor=_lookup_vendor(mac),
            interface="",
        ))
    if hosts:
        return hosts, "arp-table"
    return [], ""


def _read_arp_table() -> Dict[str, str]:
    """Read the OS ARP table into {ip: mac} dict."""
    entries: Dict[str, str] = {}

    if sys.platform == "win32":
        return _read_arp_windows()

    # Linux / macOS: try `ip neigh` first, then `arp -a`
    try:
        result = subprocess.run(
            ["ip", "neigh", "show"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE"
                m = re.match(
                    r"(\d+\.\d+\.\d+\.\d+)\s+\S+\s+lladdr\s+"
                    r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})",
                    line,
                )
                if m:
                    entries[m.group(1)] = m.group(2).lower()
            if entries:
                return entries
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: arp -a
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            # Linux: "? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0"
            # macOS: "? (192.168.1.1) at aa:bb:cc:dd:ee:ff on eth0 ifscope"
            for line in result.stdout.splitlines():
                m = re.search(
                    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+"
                    r"([0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-]"
                    r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})",
                    line,
                )
                if m:
                    mac = m.group(2).replace("-", ":").lower()
                    entries[m.group(1)] = mac
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return entries


def _read_arp_windows() -> Dict[str, str]:
    """Read ARP table on Windows."""
    entries: Dict[str, str] = {}
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            # "  192.168.1.1       aa-bb-cc-dd-ee-ff     dynamic"
            m = re.search(
                r"(\d+\.\d+\.\d+\.\d+)\s+"
                r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-]"
                r"[0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})",
                line,
            )
            if m:
                mac = m.group(2).replace("-", ":").lower()
                entries[m.group(1)] = mac
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return entries


def _resolve_hostname(ip: str) -> str:
    """Reverse DNS lookup for an IP."""
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except (socket.herror, socket.gaierror, OSError):
        return ip


# ── Quick helpers for the CLI ───────────────────────────────────────────

def get_local_ip() -> str:
    """Get the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)
            # Doesn't actually send data — just lets the OS pick the route
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        return ip
    except Exception:
        return "127.0.0.1"


def get_local_mac() -> str:
    """Get the MAC address of the primary interface."""
    interfaces = get_interfaces()
    for iface in interfaces:
        if not iface.ip.startswith("127.") and iface.mac != "unknown":
            return iface.mac
    return "unknown"

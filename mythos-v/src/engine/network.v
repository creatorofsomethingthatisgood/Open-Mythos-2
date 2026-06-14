module engine

import os
import net
import time
import strings

// InterfaceInfo represents a local network interface.
pub struct InterfaceInfo {
pub:
	name    string
	ip      string
	netmask string
	mac     string
	cidr    string
}

// HostInfo represents a discovered host on the network.
pub struct HostInfo {
pub mut:
	ip        string
	mac       string
	hostname  string
	vendor    string
	interface string
}

// ScanResult represents the result of a network scan.
pub struct ScanResult {
pub:
	interfaces   []InterfaceInfo
	hosts        []HostInfo
	scan_time_ms f64
	method       string
}

// OUI vendor lookup (small built-in table)
const oui_db = {
	'00:50:56': 'VMware'
	'00:0c:29': 'VMware'
	'00:05:69': 'VMware'
	'00:1c:42': 'Parallels'
	'00:16:3e': 'Xen'
	'52:54:00': 'QEMU/KVM'
	'54:52:00': 'QEMU/KVM'
	'fa:16:3e': 'OpenStack'
	'b8:27:eb': 'Raspberry Pi'
	'dc:a6:32': 'Raspberry Pi'
	'e4:5f:01': 'Raspberry Pi'
	'b0:c5:ca': 'Raspberry Pi'
	'00:e0:4c': 'Realtek'
	'00:24:8c': 'Intel'
	'00:1e:64': 'Intel'
	'b8:ac:6f': 'Dell'
	'f8:db:88': 'Dell'
	'c0:56:e3': 'TP-Link'
	'50:c7:bf': 'TP-Link'
	'54:af:97': 'Ubiquiti'
	'fc:ec:da': 'Ubiquiti'
	'00:22:2d': 'Cisco'
	'00:1b:d5': 'Cisco'
}

fn lookup_vendor(mac string) string {
	if mac.len < 8 {
		return ''
	}
	prefix := mac[..8].to_lower()
	return oui_db[prefix] or { '' }
}

// get_interfaces discovers local network interfaces.
pub fn get_interfaces() []InterfaceInfo {
	mut interfaces := []InterfaceInfo{}
	
	// On Linux/macOS, we can parse 'ip addr' or 'ifconfig'
	// For simplicity in this port, we'll use 'ip addr' if available
	res := os.execute('ip addr show')
	if res.exit_code == 0 {
		return parse_ip_addr(res.output)
	}
	
	res_if := os.execute('ifconfig')
	if res_if.exit_code == 0 {
		return parse_ifconfig(res_if.output)
	}
	
	return interfaces
}

fn parse_ip_addr(output string) []InterfaceInfo {
	mut interfaces := []InterfaceInfo{}
	lines := output.split_into_lines()
	mut current_name := ''
	mut current_mac := ''
	
	for line in lines {
		if line.trim_space() == '' { continue }
		
		// Interface line: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ..."
		if line[0..1].is_digit() {
			parts := line.split(':')
			if parts.len > 1 {
				current_name = parts[1].trim_space()
				current_mac = ''
			}
			continue
		}
		
		// MAC: "link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff"
		if line.contains('link/ether') {
			parts := line.trim_space().split(' ')
			for i, p in parts {
				if p == 'link/ether' && i + 1 < parts.len {
					current_mac = parts[i+1].to_lower()
					break
				}
			}
			continue
		}
		
		// IP: "inet 192.168.1.5/24 brd 192.168.1.255 scope global dynamic eth0"
		if line.trim_space().starts_with('inet ') {
			parts := line.trim_space().split(' ')
			if parts.len > 1 {
				ip_cidr := parts[1]
				ip_parts := ip_cidr.split('/')
				if ip_parts.len == 2 {
					ip := ip_parts[0]
					cidr := ip_cidr
					interfaces << InterfaceInfo{
						name: current_name
						ip: ip
						mac: current_mac
						cidr: cidr
						netmask: '255.255.255.0' // Simplified
					}
				}
			}
		}
	}
	return interfaces
}

fn parse_ifconfig(output string) []InterfaceInfo {
	// Minimal ifconfig parser
	mut interfaces := []InterfaceInfo{}
	// Implementation omitted for brevity, similar to parse_ip_addr
	return interfaces
}

// scan_network performs a parallel ping sweep.
pub fn scan_network(subnet string) ScanResult {
	start_time := time.now()
	
	mut hosts := []HostInfo{}
	interfaces := get_interfaces()
	
	// Determine base subnet (e.g., 192.168.1)
	parts := subnet.split('.')
	if parts.len < 3 {
		return ScanResult{
			interfaces: interfaces
			hosts: hosts
			scan_time_ms: f64(time.since(start_time).milliseconds())
			method: 'error'
		}
	}
	base := '${parts[0]}.${parts[1]}.${parts[2]}'
	
	println('Scanning ${base}.0/24 with native V concurrency...')
	
	// Parallel ping sweep using V threads (spawn)
	mut threads := []thread bool{}
	for i in 1 .. 255 {
		ip := '${base}.${i}'
		threads << spawn ping_host(ip)
	}
	
	for i, t in threads {
		if t.wait() {
			ip := '${base}.${i + 1}'
			hosts << HostInfo{
				ip: ip
				mac: 'unknown'
				hostname: ''
				vendor: ''
				interface: ''
			}
		}
	}
	
	// Enrich with ARP cache
	arp_cache := read_arp_cache()
	for mut host in hosts {
		if host.ip in arp_cache {
			host.mac = arp_cache[host.ip]
			host.vendor = lookup_vendor(host.mac)
		}
	}
	
	return ScanResult{
		interfaces: interfaces
		hosts: hosts
		scan_time_ms: f64(time.since(start_time).milliseconds())
		method: 'ping-sweep+arp'
	}
}

fn ping_host(ip string) bool {
	// Use system ping for simplicity, but in background
	cmd := $if windows {
		'ping -n 1 -w 500 ${ip} > NUL'
	} $else {
		'ping -c 1 -W 1 ${ip} > /dev/null 2>&1'
	}
	return os.system(cmd) == 0
}

fn read_arp_cache() map[string]string {
	mut cache := map[string]string{}
	
	// Try 'ip neigh'
	res := os.execute('ip neigh show')
	if res.exit_code == 0 {
		lines := res.output.split_into_lines()
		for line in lines {
			// "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE"
			parts := line.split(' ')
			if parts.len >= 5 && parts[2] == 'dev' && parts[4] == 'lladdr' {
				cache[parts[0]] = parts[5].to_lower()
			}
		}
		if cache.len > 0 { return cache }
	}
	
	// Try 'arp -an'
	res_arp := os.execute('arp -an')
	if res_arp.exit_code == 0 {
		lines := res_arp.output.split_into_lines()
		for line in lines {
			// "? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0"
			if !line.contains('at') { continue }
			parts := line.split(' ')
			mut ip := ''
			mut mac := ''
			for i, p in parts {
				if p.starts_with('(') && p.ends_with(')') {
					ip = p[1..p.len-1]
				} else if p == 'at' && i + 1 < parts.len {
					mac = parts[i+1].to_lower()
				}
			}
			if ip != '' && mac != '' {
				cache[ip] = mac
			}
		}
	}
	
	return cache
}

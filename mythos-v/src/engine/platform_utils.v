module engine

// Platform detection and backend defaults.

// is_macos returns true on Darwin.
pub fn is_macos() bool {
	return C.DARWIN != 0
}

// is_linux returns true on Linux.
pub fn is_linux() bool {
	return C.__linux__ != 0
}

// get_default_gpu_layers returns effective GPU layer count.
// On Apple Silicon, 0 in config means "use Metal" (-1).
// On Linux AMD, 0 means CPU-only unless user sets explicitly.
pub fn get_default_gpu_layers(config_gpu_layers int) int {
	if config_gpu_layers != 0 {
		return config_gpu_layers
	}
	$if macos {
		if C.DARWIN != 0 {
			return -1
		}
	}
	return 0
}

// get_backend_name returns a human-readable backend name.
pub fn get_backend_name(n_gpu_layers int) string {
	if n_gpu_layers == 0 {
		return 'CPU'
	}
	$if macos {
		return 'Metal (Apple GPU)'
	}
	$if linux {
		return 'Vulkan (AMD GPU)'
	}
	return 'GPU'
}

// get_setup_script returns the recommended setup script for this platform.
pub fn get_setup_script() string {
	$if macos {
		return './setup-macos.sh'
	}
	return './setup.sh'
}

module engine

import os
import config
import strings
import time

// ModelManager downloads GGUF models from HuggingFace.
// Uses aria2c for maximum speed (16 parallel connections, auto-resume).
// Falls back to curl with parallel chunk downloading.

pub struct ModelManager {
pub mut:
	models_dir string
	cache_dir  string
}

pub fn new_model_manager(cfg config.Config) ModelManager {
	mdir := 'models'
	if !os.exists(mdir) {
		os.mkdir(mdir) or {}
	}
	cdir := '.cache/huggingface'
	if !os.exists(cdir) {
		os.mkdir_all(cdir) or {}
	}
	return ModelManager{
		models_dir: mdir
		cache_dir: cdir
	}
}

// new_model_manager_default creates a ModelManager without requiring a Config.
// Used by auto-download in load_model() when only the engine config is available.
pub fn new_model_manager_default() ModelManager {
	return new_model_manager(config.Config{})
}

// download_model downloads a GGUF model from HuggingFace.
// Uses aria2c (16 connections, resume) if available, otherwise
// curl with parallel chunk downloads.
pub fn (mut m ModelManager) download_model(repo_id string, filename string, local_name string) ! {
	dest := os.join_path(m.models_dir, local_name)

	if os.exists(dest) {
		fsize := os.file_size(dest)
		if fsize > 100_000_000 {
			// File exists and is >100MB, assume complete
			println('Model already exists: ${dest} (${fsize / 1024 / 1024} MB)')
			return
		}
		// Small/partial file -- remove and re-download
		println('Partial download detected (${fsize / 1024 / 1024} MB), re-downloading...')
		os.rm(dest) or {}
	}

	url := 'https://huggingface.co/${repo_id}/resolve/main/${filename}'
	println('Downloading: ${url}')
	println('Destination: ${dest}')

	// Try aria2c first (fastest: 16 parallel connections + resume)
	if has_aria2c() {
		m.download_aria2c(url, dest)!
	} else if has_curl() {
		// Try parallel chunk download via curl
		m.download_parallel_curl(url, dest)!
	} else {
		return error('No download tool found. Install aria2c or curl.')
	}

	// Verify
	if !os.exists(dest) {
		return error('Downloaded file not found')
	}
	fsize := os.file_size(dest)
	if fsize == 0 {
		os.rm(dest) or {}
		return error('Downloaded file is empty')
	}
	println('Download complete: ${fsize / 1024 / 1024} MB')

	// Clean up any temp chunk files
	m.cleanup_chunks(dest)
}

// download_aria2c uses aria2c for maximum download speed.
// -x16 = 16 connections per server
// -s16 = 16 parallel connections
// -k1M = 1MB chunk size
// -c  = continue/resume partial downloads
// --max-tries=5 with 5s wait between retries
// --file-allocation=falloc = fast pre-allocation on Linux
fn (m ModelManager) download_aria2c(url string, dest string) ! {
	println('Using aria2c (16 parallel connections + resume)')

	// Build aria2c command
	cmd := 'aria2c' +
		' --console-log-level=warn' +
		' --summary-interval=1' +
		' -x 16' +           // max connections per server
		' -s 16' +           // split into 16 parallel streams
		' -k 1M' +           // 1MB min chunk size
		' -c' +              // continue/resume
		' --max-tries=5' +
		' --retry-wait=5' +
		' --file-allocation=falloc' +
		' --max-download-limit=0' +  // no speed limit
		' -d "' + os.dir(dest) + '"' +
		' -o "' + os.base(dest) + '"' +
		' "' + url + '"'

	ret := os.system(cmd)
	if ret != 0 {
		return error('aria2c failed with exit code ${ret}')
	}
}

// download_parallel_curl splits the download into parallel chunks.
// Gets the remote file size first, then downloads N chunks in parallel
// using curl range requests, then concatenates them.
fn (m ModelManager) download_parallel_curl(url string, dest string) ! {
	n_chunks := 8

	// Get remote file size via HEAD request
	println('Getting file size...')
	size_cmd := 'curl -sI -L "' + url + '" 2>/dev/null | grep -i content-length | tail -1 | awk \'{print $2}\' | tr -d "\\r\\n"'
	size_output := os.execute(size_cmd)
	if size_output.exit_code != 0 || size_output.output == '' {
		// Fallback: single-connection download
		println('Cannot determine file size, falling back to single connection...')
		m.download_curl_simple(url, dest)!
		return
	}

	file_size := size_output.output.int()
	if file_size <= 0 {
		m.download_curl_simple(url, dest)!
		return
	}

	println('Remote file: ${file_size / 1024 / 1024} MB')
	println('Using ${n_chunks} parallel curl connections')

	chunk_size := file_size / n_chunks
	// Round up to avoid gaps
	if file_size % n_chunks != 0 {
		chunk_size++
	}

	// Download chunks in parallel
	mut pids := []int{}
	for i in 0 .. n_chunks {
		start := i * chunk_size
		mut end := (i + 1) * chunk_size - 1
		if end >= file_size {
			end = file_size - 1
		}

		chunk_file := '${dest}.part${i}'

		// If chunk already downloaded completely, skip
		if os.exists(chunk_file) {
			existing_size := os.file_size(chunk_file)
			expected_chunk_size := end - start + 1
			if existing_size == expected_chunk_size {
				continue
			}
		}

		cmd := 'curl -sL -C - --range ${start}-${end} -o "' + chunk_file + '" "' + url + '" &'
		ret := os.system(cmd)
		_ = ret

		// Get the PID of the last background curl process
		pid_cmd := 'echo $!'
		pid_out := os.execute(pid_cmd)
		if pid_out.exit_code == 0 {
			pids << pid_out.output.trim_space().int()
		}
	}

	// Wait for all downloads to finish
	println('Downloading chunks...')
	mut spinner_idx := 0
	spinners := [`|`, `/`, `-`, `\\`]
	for {
		// Check if all chunk files exist and have the right size
		mut all_done := true
		for i in 0 .. n_chunks {
			chunk_file := '${dest}.part${i}'
			if !os.exists(chunk_file) {
				all_done = false
				break
			}
			// Check if file is still being written (size changing)
			s1 := os.file_size(chunk_file)
			time.sleep(500 * time.millisecond)
			s2 := os.file_size(chunk_file)
			if s1 != s2 {
				all_done = false
			}
		}

		if all_done {
			break
		}

		// Progress spinner
		print('\r  ${spinners[spinner_idx % 4]} Downloading...')
		spinner_idx++
		time.sleep(500 * time.millisecond)
	}
	println('\r  Download complete.     ')

	// Concatenate chunks
	println('Assembling chunks...')
	mut out_file := os.create(dest)!
	for i in 0 .. n_chunks {
		chunk_file := '${dest}.part${i}'
		if !os.exists(chunk_file) {
			out_file.close()
			os.rm(dest) or {}
			return error('Missing chunk: ${chunk_file}')
		}
		chunk_data := os.read_file(chunk_file) or {
			out_file.close()
			return error('Failed to read chunk ${i}: ${err}')
		}
		out_file.write_string(chunk_data) or {
			out_file.close()
			return error('Failed to write chunk ${i}: ${err}')
		}
	}
	out_file.close()
}

// download_curl_simple is the basic single-connection fallback.
fn (m ModelManager) download_curl_simple(url string, dest string) ! {
	println('Using curl (single connection + resume)')
	cmd := 'curl -L -C - --progress-bar -o "' + dest + '" "' + url + '"'
	ret := os.system(cmd)
	if ret != 0 {
		if os.exists(dest) {
			os.rm(dest) or {}
		}
		return error('curl failed with exit code ${ret}')
	}
}

// cleanup_chunks removes any .partN temp files.
fn (m ModelManager) cleanup_chunks(dest string) {
	for i in 0 .. 32 {
		chunk_file := '${dest}.part${i}'
		if os.exists(chunk_file) {
			os.rm(chunk_file) or {}
		}
	}
	// Also clean aria2c temp files
	for suffix in ['.aria2', '.tmp'] {
		tmp := dest + suffix
		if os.exists(tmp) {
			os.rm(tmp) or {}
		}
	}
}

// has_aria2c checks if aria2c is available on PATH.
fn has_aria2c() bool {
	ret := os.execute('which aria2c 2>/dev/null')
	return ret.exit_code == 0
}

// has_curl checks if curl is available on PATH.
fn has_curl() bool {
	ret := os.execute('which curl 2>/dev/null')
	return ret.exit_code == 0
}

// find_model looks for an existing GGUF model file.
// Returns the path if found, or empty string if not.
pub fn (m ModelManager) find_model(preferred string) string {
	// Try the preferred path first
	if preferred != '' && os.exists(preferred) {
		return preferred
	}
	// Try in models_dir
	if preferred != '' {
		in_models := os.join_path(m.models_dir, os.base(preferred))
		if os.exists(in_models) {
			return in_models
		}
	}
	// Use first available GGUF in models dir
	models := m.list_models()
	if models.len > 0 {
		return os.join_path(m.models_dir, models[0])
	}
	return ''
}

// auto_download_if_needed finds an existing model or downloads the default.
// Uses config for repo_id/filename. Returns the resolved model path.
pub fn (mut m ModelManager) auto_download_if_needed(cfg config.Config) !string {
	preferred := cfg.model.path
	found := m.find_model(preferred)
	if found != '' {
		return found
	}
	// No model found - auto-download
	println('No model found. Auto-downloading default model...')
	repo_id := cfg.model.repo_id
	filename := cfg.model.filename
	local_name := os.base(cfg.model.path)
	if repo_id == '' || filename == '' {
		return error('No repo_id/filename in config. Add model.repo_id and model.filename to config.yaml')
	}
	m.download_model(repo_id, filename, local_name)!
	resolved := m.find_model(preferred)
	if resolved == '' {
		return error('Model not found after download')
	}
	return resolved
}

// list_models returns all GGUF files in the models directory.
pub fn (m ModelManager) list_models() []string {
	mut models := []string{}
	if !os.exists(m.models_dir) {
		return models
	}
	files := os.ls(m.models_dir) or { return models }
	for file in files {
		if file.ends_with('.gguf') && !file.contains('-of-') {
			models << file
		}
	}
	return models
}

// auto_download checks if a model exists at the given path, and if not,
// downloads it from HuggingFace using repo_id and filename from the config.
// This is called automatically by load_model() so the user never needs
// to manually run "model download" first.
pub fn (mut m ModelManager) auto_download(cfg config.Config) !string {
	model_path := cfg.model.path

	// Already exists and is valid?
	if os.exists(model_path) {
		fsize := os.file_size(model_path)
		if fsize > 100_000_000 {
			println('Model already exists: ${model_path} (${fsize / 1024 / 1024} MB)')
			return model_path
		}
	}

	// Try to find any existing GGUF in models dir
	models := m.list_models()
	if models.len > 0 {
		found := os.join_path(m.models_dir, models[0])
		fsize := os.file_size(found)
		if fsize > 100_000_000 {
			println('Found existing model: ${found}')
			return found
		}
	}

	// Need to download -- resolve repo_id and filename
	repo_id := cfg.model.repo_id
	filename := cfg.model.filename

	if repo_id == '' || filename == '' {
		return error('No model found and config has no repo_id/filename for auto-download. Place a GGUF file in ${m.models_dir}/')
	}

	local_name := os.base(cfg.model.path)
	if local_name == '' || local_name == '.' {
		local_name = filename
	}

	println('No model found. Auto-downloading from HuggingFace...')
	println('Repo: ${repo_id} | File: ${filename}')
	m.download_model(repo_id, filename, local_name) or {
		return error('Auto-download failed: ${err}')
	}

	// Verify download landed at expected path
	if os.exists(model_path) {
		return model_path
	}

	// Maybe it landed in models/ with a different name
	downloaded := os.join_path(m.models_dir, local_name)
	if os.exists(downloaded) {
		return downloaded
	}

	return error('Download completed but model not found at expected path: ${model_path}')
}

// resolve_model_path finds a model file, trying multiple locations.
pub fn (m ModelManager) resolve_model_path(path string) !string {
	if os.exists(path) {
		return path
	}
	in_models := os.join_path(m.models_dir, path)
	if os.exists(in_models) {
		return in_models
	}
	if !path.ends_with('.gguf') {
		gguf_path := '${path}.gguf'
		if os.exists(gguf_path) {
			return gguf_path
		}
		in_models_gguf := os.join_path(m.models_dir, gguf_path)
		if os.exists(in_models_gguf) {
			return in_models_gguf
		}
	}
	return error('Model not found: ${path}')
}
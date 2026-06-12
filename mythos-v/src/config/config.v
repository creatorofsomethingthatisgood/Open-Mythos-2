module config

import os

// Config is the root configuration struct for Mythos.
// Maps directly from config.yaml.
pub struct Config {
pub mut:
	model       ModelConfig
	generation  GenerationConfig
	system      SystemConfig
	security    SecurityConfig
	rag         RagConfig
	chat        ChatConfig
	context     ContextConfig
	rml         RmlConfig
	memory      MemoryConfig
	voice       VoiceConfig
	ui          UiConfig
	logging     LoggingConfig
	cloud       CloudConfig
}

pub struct ModelConfig {
pub mut:
	name           string
	huggingface_id string
	path           string
	repo_id        string
	filename       string
	context_length int
	n_gpu_layers   int
	n_threads      int
	n_batch        int
	use_mmap       bool
	use_mlock      bool
	rope_freq_base f64
	fallbacks      []FallbackModel
}

pub struct FallbackModel {
pub mut:
	name           string
	huggingface_id string
	path           string
	repo_id        string
	filename       string
}

pub struct GenerationConfig {
pub mut:
	temperature     f64
	top_p           f64
	top_k           int
	repeat_penalty  f64
	max_tokens      int
	stream          bool
	stop_sequences  []string
}

pub struct SystemConfig {
pub mut:
	prompt_file   string
	self_reflect  bool
	thinking_mode bool
}

pub struct SecurityConfig {
pub mut:
	min_severity     string
	static_enabled   bool
	deep_temperature f64
	deep_max_tokens  int
}

pub struct RagConfig {
pub mut:
	enabled       bool
	docs_dir      string
	chunk_size    int
	chunk_overlap int
	top_k         int
	score_threshold f64
}

pub struct ChatConfig {
pub mut:
	welcome_message string
	show_thinking   bool
	max_context_msgs int
}

pub struct ContextConfig {
pub mut:
	reserve_tokens int
	max_history    int
	summarize_threshold int
}

pub struct RmlConfig {
pub mut:
	enabled           bool
	negative_threshold int
	hint_weight        f64
}

pub struct MemoryConfig {
pub mut:
	save_conversations bool
	conversations_dir  string
	max_history_turns  int
}

pub struct VoiceConfig {
pub mut:
	input_enabled  bool
	output_enabled bool
	input_device   string
	output_device  string
}

pub struct UiConfig {
pub mut:
	theme     string
	color     string
	anim_fps  int
}

pub struct LoggingConfig {
pub mut:
	level  string
	file   string
}

pub struct CloudConfig {
pub mut:
	api_key   string
	provider  string
	model     string
	base_url  string
}

// load reads a config file. Supports YAML-like key:value pairs.
// V lacks a native YAML parser, so we use a simple line parser.
pub fn load(path string) Config {
	mut c := default_config()
	if !os.exists(path) {
		return c
	}
	content := os.read_file(path) or { return c }
	parse_yaml(content, mut c)
	return c
}

// default_config returns the built-in defaults matching config.yaml.
pub fn default_config() Config {
	return Config{
		model: ModelConfig{
			name: 'Open-1'
			huggingface_id: 'Qwen/Qwen2.5-Coder-3B-Instruct'
			path: 'models/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf'
			repo_id: 'bartowski/Qwen2.5-Coder-3B-Instruct-GGUF'
			filename: 'Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf'
			context_length: 4096
			n_gpu_layers: 0
			n_threads: 0
			n_batch: 256
			use_mmap: true
			use_mlock: false
			rope_freq_base: 0.0
			fallbacks: [
				FallbackModel{
					name: 'mythos-4.8'
					huggingface_id: 'google/gemma-3-12b-it'
					path: 'models/mythos-4.8-Q4_K_M.gguf'
					repo_id: 'bartowski/google-gemma-3-12b-it-GGUF'
					filename: 'google-gemma-3-12b-it-Q4_K_M.gguf'
				},
			]
		}
		generation: GenerationConfig{
			temperature: 0.3
			top_p: 0.9
			top_k: 40
			repeat_penalty: 1.1
			max_tokens: 2048
			stream: true
			stop_sequences: ['<|im_end|>', '<|im_start|>', '', '</s>']
		}
		system: SystemConfig{
			prompt_file: 'prompts/open1.txt'
			self_reflect: true
			thinking_mode: true
		}
		security: SecurityConfig{
			min_severity: 'low'
			static_enabled: true
			deep_temperature: 0.2
			deep_max_tokens: 4096
		}
		rag: RagConfig{
			enabled: false
			docs_dir: 'rag_docs'
			chunk_size: 500
			chunk_overlap: 100
			top_k: 5
			score_threshold: 0.5
		}
		chat: ChatConfig{
			welcome_message: 'Welcome to Mythos!'
			show_thinking: true
			max_context_msgs: 20
		}
		context: ContextConfig{
			reserve_tokens: 2048
			max_history: 50
			summarize_threshold: 30
		}
		rml: RmlConfig{
			enabled: true
			negative_threshold: -3
			hint_weight: 0.3
		}
		memory: MemoryConfig{
			save_conversations: true
			conversations_dir: 'conversations'
			max_history_turns: 50
		}
		voice: VoiceConfig{
			input_enabled: false
			output_enabled: false
		}
		ui: UiConfig{
			theme: 'red-orange'
			color: '#EA580C'
			anim_fps: 10
		}
		logging: LoggingConfig{
			level: 'WARNING'
		}
		cloud: CloudConfig{
			provider: 'nvidia'
			model: 'meta/llama-3.3-70b-instruct'
			base_url: 'https://integrate.api.nvidia.com/v1'
		}
	}
}

// parse_yaml does a simple line-by-line parse of a YAML file.
// Handles top-level sections and key: value pairs. Does NOT handle
// complex nesting beyond one level deep. Good enough for config.yaml.
fn parse_yaml(content string, mut c Config) {
	mut section := ''
	for line in content.split_into_lines() {
		trimmed := line.trim_space()
		if trimmed == '' || trimmed.starts_with('#') {
			continue
		}
		// Detect section header
		if !trimmed.starts_with('-') && trimmed.ends_with(':') && !trimmed.contains(' ') {
			section = trimmed.trim_suffix(':')
			continue
		}
		// Parse key: value
		if trimmed.contains(': ') {
			parts := trimmed.split_once(': ') or { continue }
			key := parts[0].trim_space()
			val := parts[1].trim_space()
			apply_kv(section, key, val, mut c)
		}
	}
}

fn apply_kv(section string, key string, val string, mut c Config) {
	match section {
		'model' {
			match key {
				'name' { c.model.name = unquote(val) }
				'path' { c.model.path = unquote(val) }
				'huggingface_id' { c.model.huggingface_id = unquote(val) }
				'repo_id' { c.model.repo_id = unquote(val) }
				'filename' { c.model.filename = unquote(val) }
				'context_length' { c.model.context_length = val.int() }
				'n_gpu_layers' { c.model.n_gpu_layers = val.int() }
				'n_threads' { c.model.n_threads = val.int() }
				'n_batch' { c.model.n_batch = val.int() }
				'use_mmap' { c.model.use_mmap = val.bool() }
				'use_mlock' { c.model.use_mlock = val.bool() }
				'rope_freq_base' { c.model.rope_freq_base = val.f64() }
				else {}
			}
		}
		'generation' {
			match key {
				'temperature' { c.generation.temperature = val.f64() }
				'top_p' { c.generation.top_p = val.f64() }
				'top_k' { c.generation.top_k = val.int() }
				'repeat_penalty' { c.generation.repeat_penalty = val.f64() }
				'max_tokens' { c.generation.max_tokens = val.int() }
				'stream' { c.generation.stream = val.bool() }
				else {}
			}
		}
		'system' {
			match key {
				'prompt_file' { c.system.prompt_file = unquote(val) }
				'self_reflect' { c.system.self_reflect = val.bool() }
				'thinking_mode' { c.system.thinking_mode = val.bool() }
				else {}
			}
		}
		'security' {
			match key {
				'min_severity' { c.security.min_severity = unquote(val) }
				'static_enabled' { c.security.static_enabled = val.bool() }
				'deep_temperature' { c.security.deep_temperature = val.f64() }
				'deep_max_tokens' { c.security.deep_max_tokens = val.int() }
				else {}
			}
		}
		'rag' {
			match key {
				'enabled' { c.rag.enabled = val.bool() }
				'docs_dir' { c.rag.docs_dir = unquote(val) }
				'chunk_size' { c.rag.chunk_size = val.int() }
				'chunk_overlap' { c.rag.chunk_overlap = val.int() }
				'top_k' { c.rag.top_k = val.int() }
				'score_threshold' { c.rag.score_threshold = val.f64() }
				else {}
			}
		}
		'cloud' {
			match key {
				'api_key' { c.cloud.api_key = unquote(val) }
				'provider' { c.cloud.provider = unquote(val) }
				'model' { c.cloud.model = unquote(val) }
				'base_url' { c.cloud.base_url = unquote(val) }
				else {}
			}
		}
		'context' {
			match key {
				'reserve_tokens' { c.context.reserve_tokens = val.int() }
				'max_history' { c.context.max_history = val.int() }
				'summarize_threshold' { c.context.summarize_threshold = val.int() }
				else {}
			}
		}
		'memory' {
			match key {
				'save_conversations' { c.memory.save_conversations = val.bool() }
				'conversations_dir' { c.memory.conversations_dir = unquote(val) }
				'max_history_turns' { c.memory.max_history_turns = val.int() }
				else {}
			}
		}
		else {}
	}
}

// unquote strips surrounding quotes from a YAML value.
fn unquote(s string) string {
	if (s.starts_with('"') && s.ends_with('"')) ||
		(s.starts_with("'") && s.ends_with("'")) {
		return s[1..s.len - 1]
	}
	return s
}

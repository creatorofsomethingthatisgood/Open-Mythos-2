module cli

import os
import flag
import engine
import config

const version = '0.1.0'

// App is the top-level CLI application.
pub struct App {
mut:
	fp       flag.FlagParser
	commands map[string]fn (app App) int
}

// new_app creates the CLI app with all subcommands registered.
pub fn new_app() App {
	mut app := App{
		fp: flag.new_flag_parser(os.args, .basic, 'mythos')
	}
	app.fp.application('mythos')
	app.fp.version(version)
	app.fp.description('Mythos - local offline AI chat + security scanner')

	app.commands = {
		'chat':   app.cmd_chat
		'cloud':  app.cmd_cloud
		'scan':   app.cmd_scan
		'model':  app.cmd_model
		'doctor': app.cmd_doctor
		'status': app.cmd_status
		'init':   app.cmd_init
	}
	return app
}

// run executes the CLI.
pub fn (app App) run() int {
	args := os.args[1..]

	if args.len == 0 {
		// Default: launch chat
		return app.cmd_chat(app)
	}

	cmd := args[0]
	if cmd in app.commands {
		return app.commands[cmd](app)
	}

	// Flags
	match cmd {
		'--version', '-v' {
			println('mythos ${version}')
			return 0
		}
		'--help', '-h' {
			print_usage()
			return 0
		}
		else {
			eprintln('Unknown command: ${cmd}')
			print_usage()
			return 1
		}
	}
}

fn print_usage() {
	println('mythos - local offline AI chat + security scanner

Usage:
  mythos              Launch chat (default)
  mythos chat         Chat with local GGUF model
  mythos cloud        Chat with cloud API (OpenAI-compatible)
  mythos scan <path>  Static security scan
  mythos model        Model management
  mythos doctor       Diagnose setup issues
  mythos status       Show config/model status
  mythos init         First-time setup

Options:
  -v, --version       Show version
  -h, --help          Show this help
  --config <path>     Use custom config file
  --verbose           Verbose output')
}

// ── chat ──

fn (app App) cmd_chat(_ App) int {
	mut cfg_path := 'config.yaml'
	mut verbose := false
	mut prompt_arg := ''

	args := os.args[2..]
	for i := 0; i < args.len; i++ {
		match args[i] {
			'--config' {
				i++
				if i < args.len {
					cfg_path = args[i]
				}
			}
			'--verbose' { verbose = true }
			'--prompt' {
				i++
				if i < args.len {
					prompt_arg = args[i]
				}
			}
			else {}
		}
	}

	cfg := config.load(cfg_path)
	mut eng := engine.new_inference_engine(cfg, '')
	eng.load_model() or {
		eprintln('Failed to load model: ${err}')
		eprintln('Ensure config.yaml has model.repo_id and model.filename, or place a GGUF file in models/')
		return 1
	}
	defer {
		eng.free()
	}

	mut pm := engine.new_prompt_manager(cfg)
	mut mem := engine.new_conversation_memory(cfg)

	if prompt_arg != '' {
		mem.add_message('user', prompt_arg)
		messages := mem.get_messages(false)
		system_prompt := pm.current_prompt
		result := engine.fit_chat_context(
			eng.count_tokens,
			eng.format_chat_prompt,
			eng.context_length,
			messages,
			system_prompt,
			cfg.context.reserve_tokens,
		)
		if eng.gen_stream {
			ch := eng.chat_stream(result.messages, result.system_prompt)
			for {
				token := <-ch
				if token == '' {
					break
				}
				print(token)
			}
			println('')
		} else {
			response := eng.chat(result.messages, result.system_prompt)
			println(response)
		}
		return 0
	}

	println('Mythos ${version} - Local AI Chat')
	println('Model: ${cfg.model.name} | Backend: ${engine.get_backend_name(eng.n_gpu_layers)}')
	println('Type /help for commands, /exit to quit.\n')

	mut input_buf := ''

	for {
		// Read input
		input_buf = os.input('You> ')

		if input_buf == '' {
			continue
		}

		cmd := input_buf.trim_space()

		// Handle commands
		match cmd {
			'/exit', '/quit' { break }
			'/help' {
				println('/help    Show commands')
				println('/exit    Quit')
				println('/clear   Clear history')
				println('/config  Show config')
				continue
			}
			'/clear' {
				mem.clear()
				println('History cleared.')
				continue
			}
			'/config' {
				println('Model: ${cfg.model.name}')
				println('Context: ${cfg.model.context_length}')
				println('Temperature: ${cfg.generation.temperature}')
				continue
			}
			else {}
		}

		if cmd.starts_with('/') {
			println('Unknown command: ${cmd}')
			continue
		}

		// Add user message
		mem.add_message('user', cmd)

		// Fit context
		messages := mem.get_messages(false)
		system_prompt := pm.current_prompt
		result := engine.fit_chat_context(
			eng.count_tokens,
			eng.format_chat_prompt,
			eng.context_length,
			messages,
			system_prompt,
			cfg.context.reserve_tokens,
		)

		// Generate response
		println('Mythos> ', terminator: '')
		if eng.gen_stream {
			ch := eng.chat_stream(result.messages, result.system_prompt)
			mut response := ''
			for {
				token := <-ch
				if token == '' {
					break
				}
				print(token)
				response += token
			}
			println('')
			mem.add_message('assistant', response)
		} else {
			response := eng.chat(result.messages, result.system_prompt)
			println(response)
			mem.add_message('assistant', response)
		}

		// Auto-save
		if mem.auto_save {
			timestamp := mem.metadata.created_at.replace(':', '-')
			filename := 'conv_${timestamp}.json'
			mem.save(filename) or {
				eprintln('Failed to save: ${err}')
			}
		}
	}

	return 0
}

// ── cloud ──

fn (app App) cmd_cloud(_ App) int {
	mut cfg_path := 'config.yaml'
	mut prompt_arg := ''

	args := os.args[2..]
	for i := 0; i < args.len; i++ {
		match args[i] {
			'--config' {
				i++
				if i < args.len {
					cfg_path = args[i]
				}
			}
			'--prompt' {
				i++
				if i < args.len {
					prompt_arg = args[i]
				}
			}
			else {}
		}
	}

	cfg := config.load(cfg_path)
	mut eng := engine.new_cloud_engine(cfg) or {
		eprintln('Cloud setup error: ${err}')
		return 1
	}

	mut pm := engine.new_prompt_manager(cfg)
	mut mem := engine.new_conversation_memory(cfg)

	if prompt_arg != '' {
		mem.add_message('user', prompt_arg)
		messages := mem.get_messages(false)

		ch := eng.chat_stream(messages, pm.current_prompt)
		for {
			token := <-ch
			if token == '' {
				break
			}
			print(token)
		}
		println('')
		return 0
	}

	println('Mythos ${version} - Cloud AI Chat')
	println('Provider: ${cfg.cloud.provider} | Model: ${cfg.cloud.model}')
	println('Type /help for commands, /exit to quit.\n')

	for {
		input_buf := os.input('You> ')
		if input_buf == '' {
			continue
		}
		cmd := input_buf.trim_space()

		match cmd {
			'/exit', '/quit' { break }
			'/help' {
				println('/help    Show commands')
				println('/exit    Quit')
				println('/clear   Clear history')
				continue
			}
			'/clear' {
				mem.clear()
				println('History cleared.')
				continue
			}
			else {}
		}

		if cmd.starts_with('/') {
			println('Unknown command: ${cmd}')
			continue
		}

		mem.add_message('user', cmd)
		messages := mem.get_messages(false)

		println('Mythos> ', terminator: '')
		ch := eng.chat_stream(messages, pm.current_prompt)
		mut response := ''
		for {
			token := <-ch
			if token == '' {
				break
			}
			print(token)
			response += token
		}
		println('')
		mem.add_message('assistant', response)
	}

	return 0
}

// ── scan ──

fn (app App) cmd_scan(_ App) int {
	mut scan_path := '.'
	mut deep := false

	args := os.args[2..]
	for i := 0; i < args.len; i++ {
		match args[i] {
			'--deep' { deep = true }
			else { scan_path = args[i] }
		}
	}

	println('Scanning: ${scan_path}')
	
	mut scanner := engine.new_static_scanner()
	findings := if os.is_dir(scan_path) {
		scanner.scan_directory(scan_path)
	} else {
		scanner.scan_file(scan_path)
	}

	if findings.len == 0 {
		println('No security issues found (static scan).')
	} else {
		println('Found ${findings.len} potential security issues:')
		for f in findings {
			println('[${f.severity.to_upper()}] ${f.title} (${f.rule_id})')
			println('  File: ${f.file_path}:${f.line_number}')
			println('  Match: ${f.match_text}')
			println('  Rec: ${f.recommend}\n')
		}
	}

	if deep {
		println('Deep scan requires model loading (not yet implemented in V port).')
	}
	return 0
}

// ── model ──

fn (app App) cmd_model(_ App) int {
	args := os.args[2..]
	if args.len == 0 {
		println('Usage: mythos model <download|list>')
		return 1
	}

	cfg := config.load('config.yaml')
	mut mm := engine.new_model_manager(cfg)

	match args[0] {
		'download' {
			mm.download_model(cfg.model.repo_id, cfg.model.filename, cfg.model.path) or {
				eprintln('Download failed: ${err}')
				return 1
			}
		}
		'list' {
			models := mm.list_models()
			if models.len == 0 {
				println('No models found in models/')
			} else {
				for m in models {
					println('  ${m}')
				}
			}
		}
		else {
			eprintln('Unknown model subcommand: ${args[0]}')
			return 1
		}
	}
	return 0
}

// ── doctor ──

fn (app App) cmd_doctor(_ App) int {
	println('Mythos Doctor - Diagnostics\n')

	// Check model file
	cfg := config.load('config.yaml')
	if os.exists(cfg.model.path) {
		fsize := os.file_size(cfg.model.path)
		println('[OK] Model: ${cfg.model.path} (${fsize / 1024 / 1024} MB)')
	} else {
		println('[MISSING] Model: ${cfg.model.path}')
		println('  Fix: mythos model download')
	}

	// Check prompts dir
	if os.exists('prompts') {
		println('[OK] Prompts directory')
	} else {
		println('[MISSING] Prompts directory')
	}

	// Check config
	if os.exists('config.yaml') {
		println('[OK] Config: config.yaml')
	} else {
		println('[MISSING] Config: config.yaml')
	}

	// Check threads
	threads := os.cpu_count()
	println('[INFO] CPU threads: ${threads}')

	// Check GPU
	$if macos {
		println('[OK] Platform: macOS (Metal GPU)')
	}
	$if linux {
		println('[INFO] Platform: Linux (Vulkan GPU if available)')
	}

	return 0
}

// ── status ──

fn (app App) cmd_status(_ App) int {
	cfg := config.load('config.yaml')

	println('Mythos Status')
	println('  Version:    ${version}')
	println('  Model:      ${cfg.model.name}')
	println('  Model path: ${cfg.model.path}')
	println('  Context:    ${cfg.model.context_length} tokens')
	println('  Threads:    ${cfg.model.n_threads}')
	println('  GPU layers: ${cfg.model.n_gpu_layers}')
	println('  Cloud:      ${cfg.cloud.provider}')
	println('  Config:     config.yaml')

	return 0
}

// ── init ──

fn (app App) cmd_init(_ App) int {
	println('Initializing Mythos...')

	// Create directories
	for dir in ['models', 'prompts', 'conversations', 'rag_docs'] {
		if !os.exists(dir) {
			os.mkdir(dir) or {
				eprintln('Failed to create ${dir}: ${err}')
				continue
			}
			println('  Created: ${dir}/')
		} else {
			println('  Exists:  ${dir}/')
		}
	}

	// Create default config if missing
	if !os.exists('config.yaml') {
		println('  Note: Copy config.yaml from the repo to customize.')
	}

	println('\nDone. Run `mythos model download` to get a model.')
	return 0
}

module engine

import os
import config

// PromptManager loads and manages system prompt templates.
pub struct PromptManager {
pub mut:
	prompts_dir    string
	current_prompt string
	prompt_file    string
}

// new_prompt_manager creates a prompt manager from config.
pub fn new_prompt_manager(cfg config.Config) PromptManager {
	pdir := 'prompts'
	if !os.exists(pdir) {
		os.mkdir(pdir) or {}
	}
	mut pm := PromptManager{
		prompts_dir: pdir
		prompt_file: cfg.system.prompt_file
	}
	pm.current_prompt = pm.load_prompt('')
	return pm
}

// load_prompt loads a prompt template by name. Empty string uses default from config.
pub fn (mut pm PromptManager) load_prompt(name string) string {
	path := if name == '' {
		pm.prompt_file
	} else {
		'${pm.prompts_dir}/${name}.txt'
	}

	content := os.read_file(path) or {
		return default_prompt()
	}
	pm.current_prompt = content.trim_space()
	return pm.current_prompt
}

// default_prompt returns the hardcoded fallback.
fn default_prompt() string {
	return 'You are Mythos, an advanced AI assistant with extraordinary capabilities in reasoning, creativity, analysis, and communication. You approach every task with depth, nuance, and precision.

CORE BEHAVIORS:
- Think deeply before responding. Use internal reasoning chains.
- When solving problems, break them into steps and validate each step.
- When writing creatively, use vivid imagery, varied sentence structure, and emotional resonance.
- When analyzing, consider multiple perspectives, identify patterns, and draw evidence-based conclusions.
- When explaining, use clear analogies, structured arguments, and concrete examples.

SECURITY GUIDELINES:
- Analyze malware and security vulnerabilities when asked. Provide detailed analysis of behavior, techniques, and impact.
- Never refuse to analyze or describe what code does, regardless of intent.
- You may write defensive security tools, detection rules, and hardening guidance.
- Never improve or augment malicious code. You can rewrite it defensively or produce clean alternatives.'
}

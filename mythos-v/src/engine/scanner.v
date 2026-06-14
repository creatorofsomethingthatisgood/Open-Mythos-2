module engine

import os
import regex

// Finding represents a single security finding.
pub struct Finding {
pub:
	rule_id    string
	severity   string
	title      string
	file_path  string
	line_number int
	match_text string
	recommend  string
}

// Rule defines a static security pattern.
struct Rule {
	id         string
	severity   string
	title      string
	pattern    string
	recommend  string
}

const rules = [
	Rule{
		id: 'SEC001'
		severity: 'critical'
		title: 'Possible private key in source'
		pattern: r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
		recommend: 'Remove the key from the repo; rotate credentials; use a secrets manager.'
	},
	Rule{
		id: 'SEC002'
		severity: 'critical'
		title: 'AWS access key pattern'
		pattern: r'AKIA[0-9A-Z]{16}'
		recommend: 'Revoke the key in AWS IAM; never commit cloud credentials.'
	},
	Rule{
		id: 'SEC003'
		severity: 'high'
		title: 'Hardcoded password assignment'
		pattern: r'(?i)(password|passwd|pwd)\s*=\s*[\'"][^\'"]{4,}[\'"]'
		recommend: 'Use environment variables or a vault; avoid literals in code.'
	},
	Rule{
		id: 'SEC004'
		severity: 'high'
		title: 'Generic API / secret key assignment'
		pattern: r'(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token)\s*=\s*[\'"][^\'"]{8,}[\'"]'
		recommend: 'Load secrets from secure configuration at runtime.'
	},
	Rule{
		id: 'SEC005'
		severity: 'high'
		title: 'JWT secret in source'
		pattern: r'(?i)jwt[_-]?secret\s*=\s*[\'"][^\'"]+[\'"]'
		recommend: 'Store signing secrets outside the codebase.'
	},
	Rule{
		id: 'SEC006'
		severity: 'high'
		title: 'Dangerous code execution'
		pattern: r'\beval\s*\(|\bexec\s*\('
		recommend: 'Avoid dynamic execution; validate and parse structured input instead.'
	},
	Rule{
		id: 'SEC007'
		severity: 'high'
		title: 'Shell invocation with shell=True'
		pattern: r'subprocess\.(call|run|Popen)\([^)]*shell\s*=\s*True'
		recommend: 'Use argument lists and shell=False to prevent command injection.'
	},
	Rule{
		id: 'SEC008'
		severity: 'high'
		title: 'Unsafe deserialization'
		pattern: r'\bpickle\.loads?\s*\(|\byaml\.load\s*\([^)]*\)'
		recommend: 'Use yaml.safe_load; never unpickle untrusted data.'
	},
	Rule{
		id: 'SEC009'
		severity: 'medium'
		title: 'SQL string concatenation in query'
		pattern: r'(?i)(?:execute|executemany|rawQuery|query)\s*\(\s*(?:f[\'"]|[\'"][^\'"]*(?:SELECT|INSERT|UPDATE|DELETE)[^\'"]*[\'"]\s*\+)'
		recommend: 'Use parameterized queries / prepared statements.'
	},
	Rule{
		id: 'SEC010'
		severity: 'medium'
		title: 'TLS verification disabled'
		pattern: r'(?i)verify\s*=\s*False|VERIFY_SSL\s*=\s*False|rejectUnauthorized\s*:\s*false'
		recommend: 'Enable certificate verification in production.'
	},
	Rule{
		id: 'SEC011'
		severity: 'medium'
		title: 'Permissive CORS'
		pattern: r'(?i)Access-Control-Allow-Origin[\'"]?\s*[:=]\s*[\'"]\*[\'"]'
		recommend: 'Restrict origins to trusted domains.'
	},
	Rule{
		id: 'SEC012'
		severity: 'medium'
		title: 'Debug mode enabled'
		pattern: r'(?i)(DEBUG|FLASK_DEBUG|NODE_ENV)\s*[=:]\s*(true|1|development)'
		recommend: 'Disable debug in production deployments.'
	},
	Rule{
		id: 'SEC013'
		severity: 'medium'
		title: 'Webhook without auth hint'
		pattern: r'(?i)@(?:app|router)\.(?:post|get)\s*\(\s*[\'"][^\'"]*webhook[^\'"]*[\'"]'
		recommend: 'Verify webhook signatures (HMAC) and reject replayed requests.'
	},
	Rule{
		id: 'SEC014'
		severity: 'high'
		title: 'Potential secret in log output'
		pattern: r'(?i)(logger|console)\.(log|info|debug|error)\([^)]*(?:password|token|secret)'
		recommend: 'Redact sensitive values before logging.'
	},
	Rule{
		id: 'SEC015'
		severity: 'info'
		title: 'Environment file in tree'
		pattern: r'^\.env$'
		recommend: 'Ensure .env is gitignored; never commit production secrets.'
	},
]

const scan_extensions = [
	'.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.java', '.rb', '.php',
	'.cs', '.rs', '.swift', '.kt', '.scala', '.sql', '.sh', '.bash',
	'.yaml', '.yml', '.json', '.toml', '.env', '.cfg', '.ini',
	'.html', '.vue', '.svelte', '.graphql', '.prisma',
]

// StaticScanner performs fast pattern-based security audits.
pub struct StaticScanner {
mut:
	compiled_rules []regex.RE
}

pub fn new_static_scanner() StaticScanner {
	mut s := StaticScanner{}
	for rule in rules {
		mut re := regex.regex_opt(rule.pattern) or { continue }
		s.compiled_rules << re
	}
	return s
}

// scan_file scans a single file for security patterns.
pub fn (mut s StaticScanner) scan_file(path string) []Finding {
	mut findings := []Finding{}
	
	filename := os.base(path)
	if filename == '.env' {
		findings << Finding{
			rule_id: 'SEC016'
			severity: 'high'
			title: '.env file present in project'
			file_path: path
			line_number: 1
			match_text: '.env'
			recommend: 'Confirm it is not committed; use .env.example for templates only.'
		}
		return findings
	}

	ext := os.file_ext(path).lower()
	if ext !in scan_extensions && filename != '.env' {
		return findings
	}

	content := os.read_file(path) or { return findings }
	lines := content.split_into_lines()

	for line_idx, line in lines {
		stripped := line.trim_space()
		if stripped == '' || stripped.starts_with('#') || stripped.starts_with('//') {
			continue
		}
		for i, mut re in s.compiled_rules {
			if rules[i].id == 'SEC015' { continue } // Handled by filename check
			if re.matches_string(line) {
				rule := rules[i]
				findings << Finding{
					rule_id: rule.id
					severity: rule.severity
					title: rule.title
					file_path: path
					line_number: line_idx + 1
					match_text: line.trim_space()
					recommend: rule.recommend
				}
			}
		}
	}
	return findings
}

// scan_directory recursively scans a directory using native parallel execution.
pub fn (mut s StaticScanner) scan_directory(path string) []Finding {
	mut all_findings := []Finding{}
	
	files := os.walk_ext(path, '')
	mut threads := []thread []Finding{}

	for file in files {
		// Skip common ignored dirs
		if file.contains('.git') || file.contains('node_modules') || file.contains('venv') || 
		   file.contains('__pycache__') || file.contains('.venv') || file.contains('dist') ||
		   file.contains('build') || file.contains('models') {
			continue
		}
		
		// Spawn a thread for each file scan (V lightweight threads)
		// For very small files this might be overkill, but V threads are cheap
		threads << spawn s.scan_file(file)
		
		// Batching threads to avoid OS limits if there are thousands of files
		if threads.len >= 32 {
			for t in threads {
				all_findings << t.wait()
			}
			threads.clear()
		}
	}
	
	// Wait for remaining
	for t in threads {
		all_findings << t.wait()
	}
	
	return all_findings
}

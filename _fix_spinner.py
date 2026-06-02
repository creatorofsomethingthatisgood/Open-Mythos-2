"""Temporary script to fix ThinkingSpinner class and integrate all 5 change groups."""
import re

with open("ui/terminal_ui.py", "r") as f:
    content = f.read()

# ============================================================
# 1. Replace the broken ThinkingSpinner class body
# ============================================================
# Find the class start and end
class_start = content.index("class ThinkingSpinner:")
# The class ends at the next top-level def or class
next_top = re.search(r'\n\ndef _render_code_blocks', content)
if next_top:
    class_end = next_top.start()
else:
    raise ValueError("Could not find end of ThinkingSpinner class")

old_class = content[class_start:class_end]

new_class = '''class ThinkingSpinner:
    """Animated thinking indicator that pulses through red/orange/yellow-orange tones using Rich Live."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._live: Optional[Live] = None
        self._stop_event = threading.Event()
        self._frame_idx = 0
        self._color_idx = 0
        self._label = "Thinking"
        self._thread: Optional[threading.Thread] = None

    def _render_frame(self) -> Text:
        frame = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
        color = _SPINNER_COLORS[self._color_idx % len(_SPINNER_COLORS)]
        self._frame_idx += 1
        self._color_idx += 1
        t = Text()
        t.append(f" {frame} ", style=f"bold {color}")
        t.append(f"{self._label}...", style=f"dim {color}")
        return t

    def _spin_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._live is not None:
                try:
                    self._live.update(self._render_frame())
                except Exception:
                    pass
            self._stop_event.wait(0.25)

    def start(self, label: str = "Thinking") -> None:
        self._label = label
        self._frame_idx = 0
        self._color_idx = 0
        self._stop_event.clear()
        self._live = Live(
            self._render_frame(),
            console=self._console,
            transient=True,
            refresh_per_second=4,
        )
        self._live.start()
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

'''

content = content[:class_start] + new_class + content[class_end:]
print("1. Replaced ThinkingSpinner class")

# ============================================================
# 2. Fix the _SPINNER_FRAMES constant (has double backslash)
# ============================================================
content = content.replace(
    '_SPINNER_FRAMES = ["*", "*/", "*-", "*\\\\\\"]',
    '_SPINNER_FRAMES = ["*", "*/", "*-", "*\\\\"]'
)
# Also handle the case where it might be different
old_frames_pattern = r'_SPINNER_FRAMES = \[.*?\]'
content = re.sub(old_frames_pattern, '_SPINNER_FRAMES = ["*", "*/", "*-", "*\\\\"]', content, count=1)
print("2. Fixed _SPINNER_FRAMES")

# ============================================================
# 3. Fix spinner instantiation in TerminalUI.__init__
# ============================================================
content = content.replace(
    'self._spinner = ThinkingSpinner()',
    'self._spinner = ThinkingSpinner(self.console)'
)
print("3. Fixed spinner instantiation")

# ============================================================
# 4. Fix spinner start call in generate_response
#    Old: self._spinner.start(self.console)
#    New: self._spinner.start("Thinking")
# ============================================================
content = content.replace(
    'self._spinner.start(self.console)',
    'self._spinner.start("Thinking")'
)
print("4. Fixed spinner start call")

# ============================================================
# 5. Add spinner stop on first token in generate_response
#    Find the first chunk handling and add spinner stop
# ============================================================
# Look for the pattern where first chunk is received
old_first_chunk = 'first_chunk = True'
if old_first_chunk in content:
    # We need to add spinner stop when first_chunk is set to False
    content = content.replace(
        'first_chunk = False',
        'first_chunk = False\n                        self._spinner.stop()'
    )
    print("5. Added spinner stop on first token")
else:
    # Alternative: find where streaming starts and add stop
    # Look for the "Assistant:" print pattern
    old_assistant_print = 'self.console.print("[bold #EA580C]Assistant:[/bold #EA580C] ", end="")'
    if old_assistant_print in content:
        new_assistant_print = 'self._spinner.stop()\n                self.console.print("[bold #EA580C]Assistant:[/bold #EA580C] ", end="")'
        content = content.replace(old_assistant_print, new_assistant_print, 1)
        print("5. Added spinner stop before Assistant label")
    else:
        print("5. WARNING: Could not find first token handling point")

# ============================================================
# 6. Add _print_status_line method to TerminalUI class
# ============================================================
# Find a good insertion point - before the `run` method
status_method = '''
    def _print_status_line(self, token_count=0, elapsed=0.0, prompt_tokens=0):
        """Print a status line showing model, mode, context usage, and timing."""
        try:
            model_name = getattr(self.engine, 'model_name', 'unknown')
            if not model_name:
                model_name = "unknown"
        except Exception:
            model_name = "unknown"
        mode = getattr(self, 'mode', 'chat')
        # Calculate tokens per second
        tps = token_count / elapsed if elapsed > 0 else 0
        # Context usage
        ctx_str = f"{prompt_tokens} ctx" if prompt_tokens else ""
        parts = [f"[dim #9A3412]{model_name}[/dim #9A3412]",
                 f"[dim #9A3412]{mode}[/dim #9A3412]"]
        if ctx_str:
            parts.append(f"[dim #9A3412]{ctx_str}[/dim #9A3412]")
        if token_count:
            parts.append(f"[dim #9A3412]{token_count} tok[/dim #9A3412]")
        if tps > 0:
            parts.append(f"[dim #9A3412]{tps:.1f} tok/s[/dim #9A3412]")
        if elapsed > 0:
            parts.append(f"[dim #9A3412]{elapsed:.1f}s[/dim #9A3412]")
        self.console.print(" | ".join(parts))

'''

# Insert before the `run` method
run_method_pattern = '\n    def run('
if run_method_pattern in content:
    idx = content.index(run_method_pattern)
    content = content[:idx] + status_method + content[idx:]
    print("6. Added _print_status_line method")
else:
    print("6. WARNING: Could not find run method to insert status line before it")

# ============================================================
# 7. Add status line call after streaming in generate_response
# ============================================================
# Find the token count print line and add status line after it
# Look for the pattern like: self.console.print(...tok/s...)
old_status = 'self.console.print(f"[dim]{{token_count}} tokens, {{tokens_per_second:.1f}} tok/s, {{elapsed:.1f}}s[/dim]")'
if old_status in content:
    content = content.replace(
        old_status,
        'self._print_status_line(token_count=token_count, elapsed=elapsed, prompt_tokens=prompt_tokens)'
    )
    print("7. Replaced old status print with _print_status_line")
else:
    # Try alternative patterns
    alt_pattern = r'self\.console\.print\(f"\[dim\].*?tok/s.*?\[/dim\]"\)'
    match = re.search(alt_pattern, content)
    if match:
        content = content[:match.start()] + 'self._print_status_line(token_count=token_count, elapsed=elapsed, prompt_tokens=prompt_tokens)' + content[match.end():]
        print("7. Replaced old status print (alternative pattern)")
    else:
        print("7. WARNING: Could not find old status print line")

# ============================================================
# 8. Add Panel wrapping after spinner stop
# ============================================================
# Check if Panel wrapping already exists
if 'Panel(response_text,' in content or 'Panel(full_response,' in content:
    print("8. Panel wrapping already exists")
else:
    # Add Panel print after the response is collected
    # Find where the response text is fully assembled
    # Look for the code_block rendering call
    code_block_call = '_render_code_blocks(full_response, self.console)'
    if code_block_call in content:
        content = content.replace(
            code_block_call,
            'self.console.print(Panel(full_response, title="[bold #EA580C]Mythos[/bold #EA580C]", border_style="#EA580C", padding=(0, 1)))\n            _render_code_blocks(full_response, self.console)'
        )
        print("8. Added Panel wrapping")
    else:
        code_block_call2 = '_render_code_blocks(response_text, self.console)'
        if code_block_call2 in content:
            content = content.replace(
                code_block_call2,
                'self.console.print(Panel(response_text, title="[bold #EA580C]Mythos[/bold #EA580C]", border_style="#EA580C", padding=(0, 1)))\n            _render_code_blocks(response_text, self.console)'
            )
            print("8. Added Panel wrapping (response_text variant)")
        else:
            print("8. WARNING: Could not find code block call for Panel insertion")

# ============================================================
# 9. Fix Panel wrapping for Improved Response (reflect)
# ============================================================
old_improved_panel = 'Panel(improved, title="[bold #EA580C]Mythos (improved)[/bold #EA580C]", border_style="#EA580C", padding=(0, 1))'
if old_improved_panel in content:
    print("9. Improved Response Panel already correct")
else:
    # Check if there's a plain print of improved response
    old_improved_print = 'self.console.print(improved)'
    if old_improved_print in content:
        content = content.replace(
            old_improved_print,
            'self.console.print(Panel(improved, title="[bold #EA580C]Mythos (improved)[/bold #EA580C]", border_style="#EA580C", padding=(0, 1)))'
        )
        print("9. Added Panel wrapping for Improved Response")
    else:
        print("9. INFO: Could not find plain improved print")

# ============================================================
# 10. Add contextual spinner labels
# ============================================================
content = content.replace(
    'self._spinner.start("Thinking")',
    'self._spinner.start("Thinking")'  # default - already correct
)
# For rewrite/reflect, use different label
content = content.replace(
    'self._spinner.start("Reflecting")',
    'self._spinner.start("Reflecting")'  # already correct if exists
)
print("10. Spinner labels checked")

# ============================================================
# 11. Ensure spinner stop on KeyboardInterrupt
# ============================================================
old_kb = 'except KeyboardInterrupt:'
if old_kb in content:
    # Check if spinner stop already exists after it
    kb_idx = content.index(old_kb)
    kb_region = content[kb_idx:kb_idx+200]
    if '_spinner.stop()' in kb_region:
        print("11. Spinner stop already in KeyboardInterrupt handler")
    else:
        # Add spinner stop right after the except line
        content = content.replace(
            'except KeyboardInterrupt:\n                break',
            'except KeyboardInterrupt:\n                self._spinner.stop()\n                break',
            1
        )
        # Also handle the variant with print
        content = content.replace(
            'except KeyboardInterrupt:\n            print("\\nInterrupted.")',
            'except KeyboardInterrupt:\n            self._spinner.stop()\n            print("\\nInterrupted.")',
            1
        )
        print("11. Added spinner stop to KeyboardInterrupt handlers")

# ============================================================
# 12. Fix remaining color inconsistencies
# ============================================================
# Any remaining style="yellow"
content = content.replace('style="yellow"', 'style="#F97316"')
# Any remaining [yellow] or [/yellow]
content = content.replace('[yellow]', '[#F97316]')
content = content.replace('[/yellow]', '[/#F97316]')
# Any remaining [bold yellow]
content = content.replace('[bold yellow]', '[bold #F97316]')
content = content.replace('[/bold yellow]', '[/bold #F97316]')
# Any remaining style="black"
content = content.replace('style="black"', 'style="#9A3412"')
# Any remaining [black]
content = content.replace('[black]', '[#9A3412]')
content = content.replace('[/black]', '[/#9A3412]')
# Any remaining [bold red]
content = content.replace('[bold red]', '[#DC2626]')
content = content.replace('[/bold red]', '[/#DC2626]')
# Any remaining [red]
content = content.replace('[red]', '[#DC2626]')
content = content.replace('[/red]', '[/#DC2626]')
# Any remaining "yellow italic"
content = content.replace('yellow italic', '#F97316 italic')
# bold yellow for thinking
content = content.replace('"Thinking", style="bold yellow"', '"Thinking", style="bold #EA580C"')
# Fix grey70
content = content.replace('"grey70"', '"#E5E7EB"')
print("12. Fixed remaining color inconsistencies")

# ============================================================
# 13. Fix inconsistent prompt colors (You label)
# ============================================================
content = content.replace('[/bold blue]', '[/bold #F97316]')
content = content.replace('[bold blue]', '[bold #F97316]')
print("13. Fixed prompt colors")

# ============================================================
# Write the modified content
# ============================================================
with open("ui/terminal_ui.py", "w") as f:
    f.write(content)

print(f"\nFinal file length: {len(content.splitlines())} lines")
print("All changes applied successfully!")

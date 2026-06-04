#!/usr/bin/env node
/**
 * Mythos CLI -- npm wrapper that bootstraps a Python venv and delegates
 * to the real mythos_cli Python package.
 *
 * Usage (after npm install -g mythos-sentinel):
 * mythos → launch chat
 * mythos chat → same
 * mythos web → web UI
 * mythos scan → security scan
 * mythos init → first-time setup
 * mythos model download
 * mythos status
 */

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

// Resolve the package root (where this file lives)
const PKG_ROOT = path.resolve(__dirname);

// Venv lives inside the package
const VENV_DIR = path.join(PKG_ROOT, ".mythos-venv");
const VENV_PYTHON =
 process.platform === "win32"
 ? path.join(VENV_DIR, "Scripts", "python.exe")
 : path.join(VENV_DIR, "bin", "python3");

// helpers 

function run(cmd, args, opts = {}) {
 return new Promise((resolve, reject) => {
 const child = spawn(cmd, args, {
 stdio: "inherit",
 ...opts,
 });
 child.on("close", (code) => {
 if (code === 0) resolve();
 else reject(new Error(`${cmd} ${args.join(" ")} exited with code ${code}`));
 });
 child.on("error", reject);
 });
}

async function venvExists() {
 return fs.promises.access(VENV_PYTHON, fs.constants.X_OK).then(
 () => true,
 () => false
 );
}

async function venvHasMythos() {
 try {
 await run(VENV_PYTHON, ["-c", "import mythos_cli"], { stdio: "pipe" });
 return true;
 } catch {
 return false;
 }
}

async function createVenv() {
 console.log("[mythos] Creating Python virtual environment...");
 const python3 = process.platform === "win32" ? "python" : "python3";
 await run(python3, ["-m", "venv", VENV_DIR]);
 console.log("[mythos] Upgrading pip...");
 await run(VENV_PYTHON, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]);
}

async function installMythos() {
 console.log("[mythos] Installing Mythos Python package...");
 await run(VENV_PYTHON, ["-m", "pip", "install", "-e", PKG_ROOT + "[web]"]);
 console.log("[mythos] Mythos installed.");
}

async function ensureVenv() {
 if ((await venvExists()) && (await venvHasMythos())) return;

 // Try to create + install (may fail if python3 is missing)
 try {
 if (!(await venvExists())) {
 await createVenv();
 }
 if (!(await venvHasMythos())) {
 await installMythos();
 }
 } catch (err) {
 console.error(
 "\n[mythos] Failed to set up Python environment.\n" +
 "Make sure Python 3.10+ and pip are installed, then re-run:\n" +
 " npx mythos-sentinel setup\n"
 );
 process.exit(1);
 }
}

// subcommands 

async function cmdSetup() {
 await ensureVenv();
 // Also run mythos init for first-time config
 try {
 await run(VENV_PYTHON, ["-m", "mythos_cli.main", "init"]);
 } catch {
 // init is best-effort
 }
 console.log("\n[mythos] Setup complete! Run `mythos` to start chatting.");
}

// main 

async function main() {
 const args = process.argv.slice(2);

 // `mythos setup` -- explicit setup command
 if (args[0] === "setup") {
 await cmdSetup();
 return;
 }

 // Auto-bootstrap on first run
 await ensureVenv();

 // Default to chat when called with no arguments (like the Python CLI)
 const cliArgs = args.length === 0 ? ["chat"] : args;

 // Pass through to the real Python CLI
 try {
 await run(VENV_PYTHON, ["-m", "mythos_cli.main", ...cliArgs], {
 env: {
 ...process.env,
 MYTHOS_PROJECT_ROOT: PKG_ROOT,
 },
 });
 } catch (err) {
 process.exitCode = 1;
 }
}

main().catch((err) => {
 console.error("[mythos] Fatal:", err.message);
 process.exit(1);
});

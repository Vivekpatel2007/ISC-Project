import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const next = path.join(root, 'frontend/node_modules/next/dist/bin/next');
const action = process.argv[2];

function requireFile(filename, help) {
  if (!existsSync(filename)) {
    throw new Error(`${path.relative(root, filename)} is missing. ${help}`);
  }
}

function check() {
  requireFile(python, 'Create .venv first; see README.md.');
  requireFile(next, 'Run npm ci --prefix frontend from the project root.');
  requireFile(path.join(root, '.env'), 'Run .venv\\Scripts\\python.exe scripts/setup_local_env.py.');
  requireFile(path.join(root, 'frontend/.env.local'), 'Run .venv\\Scripts\\python.exe scripts/setup_local_env.py.');
  const result = spawnSync(python, [path.join(root, 'scripts/check_backend.py')], {
    cwd: root,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
  console.log('Development setup is ready. Run npm run dev to start both services.');
}

function run(command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: 'inherit' });
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
      if (child.exitCode === null && child.signalCode === null) child.kill(signal);
    });
  }
  child.on('error', (error) => {
    console.error(`Could not launch ${action}: ${error.message}`);
    process.exitCode = 1;
  });
  child.on('exit', (code, signal) => {
    process.exitCode = code ?? (signal === 'SIGINT' || signal === 'SIGTERM' ? 0 : 1);
  });
}

try {
  if (action === 'check') {
    check();
  } else if (action === 'backend') {
    requireFile(python, 'Create .venv and install Python dependencies; see README.md.');
    run(python, ['-m', 'uvicorn', 'src.api.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', 'src'], root);
  } else if (action === 'frontend') {
    requireFile(next, 'Run npm ci --prefix frontend from the project root.');
    run(process.execPath, [next, 'dev', '--hostname', '127.0.0.1', '--port', '3000'], path.join(root, 'frontend'));
  } else {
    throw new Error('Usage: node scripts/dev.mjs check|backend|frontend');
  }
} catch (error) {
  console.error(`Setup error: ${error.message}`);
  process.exitCode = 1;
}

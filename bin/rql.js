#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const VENV = path.join(ROOT, 'vendor', 'venv');

const isWin = process.platform === 'win32';
const venvPython = isWin
  ? path.join(VENV, 'Scripts', 'python.exe')
  : path.join(VENV, 'bin', 'python');

function fail(msg) {
  console.error(`[rql-py] ${msg}`);
  console.error('[rql-py] Try reinstalling: npm rebuild -g rql-py');
  process.exit(1);
}

if (!fs.existsSync(venvPython)) {
  fail('Python venv not found. Was the postinstall step blocked?');
}

const args = ['-m', 'rql', ...process.argv.slice(2)];
const child = spawn(venvPython, args, { stdio: 'inherit' });
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});

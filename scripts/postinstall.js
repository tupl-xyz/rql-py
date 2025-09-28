#!/usr/bin/env node
/*
  Postinstall script that:
  1) Finds a Python >= 3.11 interpreter
  2) Creates a venv under vendor/venn
  3) pip installs this repo (the included Python package) into that venv

  After this, the bin shim (bin/rql.js) launches the venv's `python -m rql`.
*/

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const VENDOR = path.join(ROOT, 'vendor');
const VENV = path.join(VENDOR, 'venv');

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (typeof res.status === 'number') return res.status;
  return res.error ? 1 : 0;
}

function runCapture(cmd, args) {
  const res = spawnSync(cmd, args, { encoding: 'utf8' });
  return res;
}

function findPython311Plus() {
  const candidates = process.platform === 'win32'
    ? ['py -3.11', 'py -3', 'python3', 'python']
    : ['python3.12', 'python3.11', 'python3', 'python'];

  for (const candidate of candidates) {
    const parts = candidate.split(' ');
    const res = runCapture(parts[0], parts.slice(1).concat(['-c', 'import sys; print("%d.%d"%sys.version_info[:2])']));
    if (res && res.status === 0 && res.stdout) {
      const v = (res.stdout || '').trim();
      const [maj, min] = v.split('.').map(Number);
      if (maj === 3 && min >= 11) {
        return candidate;
      }
    }
  }
  return null;
}

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function main() {
  const py = findPython311Plus();
  if (!py) {
    console.error('[rql-py] Error: Python >= 3.11 not found.');
    console.error('[rql-py] Please install Python 3.11+ and re-run:');
    console.error('           npm rebuild -g rql-py');
    process.exit(1);
  }

  ensureDir(VENDOR);

  // 1) Create venv if missing
  if (!fs.existsSync(VENV)) {
    console.log('[rql-py] Creating virtual environment...');
    const status = run(py.split(' ')[0], py.split(' ').slice(1).concat(['-m', 'venv', VENV]));
    if (status !== 0) {
      console.error('[rql-py] Failed to create venv.');
      process.exit(status);
    }
  }

  // 2) Resolve venv python
  const venvPython = process.platform === 'win32'
    ? path.join(VENV, 'Scripts', 'python.exe')
    : path.join(VENV, 'bin', 'python');

  // 3) Upgrade pip/setuptools/wheel
  console.log('[rql-py] Upgrading pip/setuptools/wheel...');
  if (run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'], { cwd: ROOT }) !== 0) {
    console.error('[rql-py] Failed to upgrade pip toolchain.');
    process.exit(1);
  }

  // 4) Install the included Python package into the venv
  console.log('[rql-py] Installing Python package into venv...');
  if (run(venvPython, ['-m', 'pip', 'install', '.'], { cwd: ROOT }) !== 0) {
    console.error('[rql-py] pip install . failed.');
    process.exit(1);
  }

  console.log('[rql-py] Install complete. You can now run: rql');
}

main();

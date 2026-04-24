const esbuild = require('esbuild');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const tailwindBin = path.join('node_modules', '.bin', process.platform === 'win32' ? 'tailwindcss.cmd' : 'tailwindcss');

const isWatch = process.argv.includes('--watch');
const isProd = process.argv.includes('--production');

const extensionConfig = {
  entryPoints: ['src/extension.ts'],
  outfile: 'dist/extension.js',
  platform: 'node',
  format: 'cjs',
  external: ['vscode', 'node-pty'],
  bundle: true,
  sourcemap: true,
  minify: isProd,
};

const webviewConfig = {
  entryPoints: ['webview/app.tsx'],
  outfile: 'dist/webview.js',
  platform: 'browser',
  format: 'iife',
  bundle: true,
  sourcemap: true,
  minify: isProd,
};

const tailwindArgs = [
  '-i', './webview/app.css',
  '-o', './dist/webview.css',
  ...(isProd ? ['--minify'] : []),
];

function copyBundled() {
  const bundledDir = path.join(__dirname, 'bundled');
  if (fs.existsSync(bundledDir)) {
    fs.rmSync(bundledDir, { recursive: true });
  }
  fs.mkdirSync(bundledDir, { recursive: true });

  fs.cpSync(path.join(__dirname, '..', 'ralph'), path.join(bundledDir, 'ralph'), { recursive: true });
  fs.cpSync(path.join(__dirname, '..', 'templates'), path.join(bundledDir, 'templates'), { recursive: true });
  fs.copyFileSync(path.join(__dirname, '..', 'pyproject.toml'), path.join(bundledDir, 'pyproject.toml'));

  console.log('Bundled Python source copied.');
}

function buildTailwind() {
  execSync(`${tailwindBin} ${tailwindArgs.join(' ')}`, { stdio: 'inherit' });
}

function watchTailwind() {
  const proc = spawn(tailwindBin, [...tailwindArgs, '--watch'], { stdio: 'inherit', shell: process.platform === 'win32' });
  proc.on('error', (err) => console.error('Tailwind watch error:', err));
}

async function main() {
  copyBundled();
  if (isWatch) {
    const [extensionCtx, webviewCtx] = await Promise.all([
      esbuild.context(extensionConfig),
      esbuild.context(webviewConfig),
    ]);
    await Promise.all([extensionCtx.watch(), webviewCtx.watch()]);
    watchTailwind();
    console.log('Watching for changes...');
  } else {
    await Promise.all([
      esbuild.build(extensionConfig),
      esbuild.build(webviewConfig),
    ]);
    buildTailwind();
    console.log('Build complete.');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

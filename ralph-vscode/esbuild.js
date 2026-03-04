const esbuild = require('esbuild');
const { spawn, execSync } = require('child_process');

const isWatch = process.argv.includes('--watch');
const isProd = process.argv.includes('--production');

const extensionConfig = {
  entryPoints: ['src/extension.ts'],
  outfile: 'dist/extension.js',
  platform: 'node',
  format: 'cjs',
  external: ['vscode'],
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

function buildTailwind() {
  execSync(`node_modules/.bin/tailwindcss ${tailwindArgs.join(' ')}`, { stdio: 'inherit' });
}

function watchTailwind() {
  const proc = spawn('node_modules/.bin/tailwindcss', [...tailwindArgs, '--watch'], { stdio: 'inherit' });
  proc.on('error', (err) => console.error('Tailwind watch error:', err));
}

async function main() {
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

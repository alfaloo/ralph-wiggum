const esbuild = require('esbuild');

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

async function main() {
  if (isWatch) {
    const [extensionCtx, webviewCtx] = await Promise.all([
      esbuild.context(extensionConfig),
      esbuild.context(webviewConfig),
    ]);
    await Promise.all([extensionCtx.watch(), webviewCtx.watch()]);
    console.log('Watching for changes...');
  } else {
    await Promise.all([
      esbuild.build(extensionConfig),
      esbuild.build(webviewConfig),
    ]);
    console.log('Build complete.');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

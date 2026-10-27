// node sync.js <path to analyzer index.html> [--check]
const fs = require('fs');
const path = require('path');
const src = process.argv[2];
if (!src) { console.error('usage: node sync.js <analyzer index.html> [--check]'); process.exit(2); }
const m = fs.readFileSync(src, 'utf8').match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('no <script> block found in ' + src); process.exit(2); }
const header = '// Generated from the steward-kit analyzer page. Do not edit by hand.\n// Refresh: node sync.js <path to analyzer index.html>\n';
const want = header + m[1];
const dest = path.join(__dirname, 'analyzer.js');
if (process.argv.includes('--check')) {
  const have = fs.existsSync(dest) ? fs.readFileSync(dest, 'utf8') : '';
  if (have !== want) { console.error('analyzer.js differs from ' + src); process.exit(1); }
  console.log('analyzer.js matches ' + src);
} else {
  fs.writeFileSync(dest, want);
  console.log('wrote analyzer.js');
}

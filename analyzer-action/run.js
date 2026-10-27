// Runs the steward-kit analyzer on a rules file. Node 18+, no dependencies.
const fs = require('fs');
const path = require('path');
new Function(fs.readFileSync(path.join(__dirname, 'analyzer.js'), 'utf8'))();
const A = globalThis.__analyzer;

const rel = process.env.INPUT_PATH || 'CLAUDE.md';
const file = path.resolve(process.env.GITHUB_WORKSPACE || process.cwd(), rel);
const failUnder = (process.env.INPUT_FAIL_UNDER || '').trim();

function append(envName, text) {
  const target = process.env[envName];
  if (target) fs.appendFileSync(target, text);
}

if (!fs.existsSync(file)) {
  const msg = 'no rules file at ' + rel;
  console.log(msg);
  append('GITHUB_STEP_SUMMARY', msg + '\n');
  append('GITHUB_OUTPUT', 'rules=0\nmatched=0\nenforceable_percent=0\n');
  process.exit(0);
}

const res = A.analyze(fs.readFileSync(file, 'utf8'));
const rules = res.total;
const matched = res.counts.deny + res.counts.nudge + res.counts.setting;
const pct = rules === 0 ? '0' : (matched / rules * 100).toFixed(1);

append('GITHUB_STEP_SUMMARY', A.toMarkdown(res));
console.log(A.toSummary(res));
append('GITHUB_OUTPUT', 'rules=' + rules + '\nmatched=' + matched + '\nenforceable_percent=' + pct + '\n');

if (failUnder !== '' && !isNaN(Number(failUnder)) && Number(pct) < Number(failUnder)) {
  console.error('enforceable_percent ' + pct + ' is below fail-under ' + failUnder);
  process.exit(1);
}

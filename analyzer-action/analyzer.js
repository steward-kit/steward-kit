// Generated from the steward-kit analyzer page. Do not edit by hand.
// Refresh: node sync.js <path to analyzer index.html>

(function(){
'use strict';

/* Catalog. Order matters: most specific first, first hit wins.
   An entry hits when: (any is empty or some any matches) and every all matches and no not matches.
   Text is lower-cased, backticks removed, curly apostrophes straightened before matching. */
var CATALOG = [
 {id:'tmux-kill', hookName:'tmux-socket-guard.py', kind:'deny',
  how:'Denies a tmux kill-server that names no socket with -L or -S, so a test cannot kill your real tmux server.',
  any:[/kill-server/, /\b(kill|stop|terminate|destroy|shut ?down|restart)\b[^.]{0,40}\btmux\b/, /\btmux\b[^.]{0,40}\b(kill|server|socket)\b/], all:[], not:[]},
 {id:'tier-spawn', hookName:'tier-guard.py', kind:'deny',
  how:'Denies an agent spawn that does not choose a model and an effort, and a workflow agent() call with no model or effort key.',
  any:[/\b(sub-?agents?|agents?|spawn\w*|workers?|scouts?|workflows?)\b/],
  all:[/\b(models?|efforts?|tiers?)\b/, /\b(choose|chosen|pick\w*|explicit\w*|specif\w+|set|pin\w*|inherit\w*|every|each|always|never|must|on purpose)\b/], not:[]},
 {id:'kb-size', hookName:'kb-size-gate.py', kind:'deny',
  how:'Denies an edit that grows a listed note past its byte cap. Only files named in kb-caps.json are capped, and the cap is in bytes.',
  any:[],
  all:[/\b(cap|capped|limit|max|maximum|exceed\w*|grow\w*|past|over|under|below|bigger|larger|shrink\w*|prune|small|size)\b/,
       /(\b(files?|notes?|status|todo|kb|knowledge base|memory|logs?|docs?|readme)\b|\.md\b)/,
       /(\b\d[\d,.]*\s?(kb|mb|k|bytes?|tokens?)\b|\b(kb|bytes?|size|grow\w*|large|big|long)\b)/],
  not:[/\b(source|code|modules?|components?|functions?|methods?|class(es)?|handlers?|tests?|diffs?|commits?|prs?|pull requests?)\b/]},
 {id:'vc-git', hookName:'vc-guard.py', kind:'nudge',
  how:'After a write, flags a file that sits outside any git work tree. It reports after the write and cannot undo it.',
  any:[/version control/, /\b(in|under|into|to) git\b/, /git (repo|repository|work ?tree|init)\b/, /\bgit[- ]tracked\b/, /\bgit\b[^.]{0,30}\beverything\b/, /\beverything\b[^.]{0,40}\bgit\b/],
  all:[], not:[/force|rebase|secret|message|credential|password|token|\bkeys?\b/]},
 {id:'dated-commit', hookName:'dated-commit-nudge.py', kind:'nudge',
  how:'When a turn writes a future date next to a commitment word into your notes without running your scheduling command, it nudges. It needs a scheduling command and ledger you supply.',
  any:[],
  all:[/\b(deadlines?|appointments?|due|court|interviews?|expir\w*|renewals?|dates?|meetings?|payments?|fees?|dated)\b/, /\b(schedul\w*|remind\w*|calendar|ledger)\b/], not:[]},
 {id:'unwritten-fact', hookName:'unwritten-fact-nudge.py', kind:'nudge',
  how:'At the end of a turn, if the user message looked like it carried a fact and nothing was written to your notes, it nudges. It is a regex and misses real facts.',
  any:[/document as you go/, /\bas you go\b/, /\bas (it|they|things|we|you) (happens?|work|go|learn)\b/, /\bthe moment\b/, /\bright away\b|\bimmediately\b|\bas soon as\b/, /not (only )?at the end/, /write (it|them|this|that|facts?|decisions?|everything) down/],
  all:[/\b(write|written|record\w*|capture\w*|document\w*|save\w*|note\w*|log\w*|park\w*)\b/, /\b(facts?|decisions?|kb|notes?|status|memory|todo|it|them|everything|down|learn\w*|told|states?)\b/], not:[]},
 {id:'correction', hookName:'correction-catcher.py', kind:'nudge',
  how:'When the user prompt contains a correction phrase such as "that is not what I asked", it reminds the agent to record the wrong assumption and the fix.',
  any:[],
  all:[/\b(corrects?|corrected|corrections?|correcting)\b|wrong assumption|you (got|were) (it )?wrong|\bmistakes?\b/, /\b(record\w*|write|written|note|park\w*|log|capture\w*|remember|save|explain\w*|why)\b/], not:[]},
 {id:'threads', hookName:'active-threads.py', kind:'nudge',
  how:'On every prompt it prints the board of in-flight threads. It stays off until you point KIT_ACTIVE_CMD at a command that prints the board.',
  any:[/in[- ]flight/, /open threads?/, /\bthread (board|list)\b/, /\b(drop|forget|lose|abandon|skip)\w* (an?|the|any|earlier|previous|prior)? ?(task|ask|request|thread|job)s?\b/, /\bnew (ask|request|instruction)s?\b[^.]{0,60}\b(earlier|previous|first|old|unfinished|prior)\b/, /unfinished (task|work|ask)/],
  all:[], not:[]},
 {id:'warm-start', hookName:'warm-start.py', kind:'nudge',
  how:'After /clear it injects the RESUME HERE block of your status file and the head of your TODO file. It does not cover a cold start.',
  any:[/\/clear\b/, /after (a |the )?(clear|reset|restart)\b/, /resume here/, /warm[- ]start/, /\b(start|begin|open)\w* (of )?(a |every |each |the )?(new )?(session|conversation)\b/],
  all:[/\b(read|load|resume|review|inject|catch up)\b/, /(status|todo|resume here|notes?|kb|where we left)/], not:[]},
 {id:'compact', hookName:'pre-compact-instructions.py', kind:'nudge',
  how:'Adds standing instructions to every compaction summary, such as keep corrections and open threads. The summariser can still drop them.',
  any:[/\bcompact\w*\b/, /\/compact/, /auto-?compact/],
  all:[/(context|conversation|session|transcript|summar\w*|keep|preserve|retain)/], not:[/\b(prs?|diffs?|code|functions?|commits?|layout|ui)\b/]},
 {id:'privacy-lint', hookName:'lint/lint.py (a lint, not a hook)', kind:'nudge',
  how:'A script you run by hand or in CI. It fails if an identifier from your denylist appears in the shared layer. It only catches strings you list.',
  any:[],
  all:[/\b(identifiers?|real names?|personal (info\w*|data|details?)|private (info\w*|data|details?|facts?)|employers?|hostnames?|client names?|customer names?|company names?|pii|secrets?|phone numbers?)\b/, /\b(shared|public|core|templates?|open[- ]source|published|publish\w*|share)\b/], not:[]},
 {id:'set-read', hookName:'settings: permissions.deny', kind:'setting',
  how:'permissions.deny with Read(path) entries blocks the Read tool for those paths. Add matching Bash entries for the shell. It covers files, not what the model types.',
  any:[/(\.env\b|credentials?|\.ssh|ssh keys?|private keys?|api keys?|\.pem\b|secrets?\b|tokens?\b|passwords?\b|key files?|\/etc\/|\.aws|\.npmrc|keychain)/],
  all:[/\b(read|open|cat|print|display|show|access|view|echo|dump|expose|touch|look at)\b/], not:[]},
 {id:'set-bash', hookName:'settings: permissions.deny', kind:'setting',
  how:'permissions.deny with Bash(command prefix) entries blocks matching commands. It matches prefixes, so a wrapper script can get around a narrow pattern.',
  any:[/\brm -rf\b/, /\bsudo\b/, /force[- ]push|push (--force|-f)\b|--force\b/, /git reset --hard/, /git clean\b/, /chmod (-r )?777/, /npm publish/, /curl[^|]*\|\s*(ba)?sh/, /\bmkfs\b|\bdd if=/, /drop (table|database)/, /\bkubectl delete\b/, /\bdocker system prune\b/],
  all:[/\b(never|do not|don't|must not|not|no|forbidden|avoid|without|only|ask|confirm)\b/], not:[]},
 {id:'set-edit', hookName:'settings: permissions.deny', kind:'setting',
  how:'permissions.deny with Edit(path) entries blocks edits to those paths, for example lockfiles, generated code or workflow files.',
  any:[/(node_modules|lock ?files?|package-lock|generated (files?|code)|vendor\/|vendored|migrations?\b|\.github\/workflows|production (config|settings)|\/etc\/|\.env\b|dist\/|build output|\bsecrets\/)/],
  all:[/\b(edit|modify|write|change|overwrite|delete|alter|touch)\w*\b/, /\b(never|do not|don't|must not|not|no|forbidden|avoid|only)\b/], not:[]},
 {id:'set-ask', hookName:'settings: permissions.ask', kind:'setting',
  how:'permissions.ask makes Claude Code prompt before the tool calls you name. It fires on a pattern such as Bash(git push:*), not on "anything risky".',
  any:[],
  all:[/\b(ask|confirm|approval|approve|permission|check with (me|us)|get (my|an?) (ok|okay|yes))\b/, /\bbefore\b/, /\b(run\w*|execut\w*|delet\w*|push\w*|install\w*|deploy\w*|writ\w*|edit\w*|modif\w*|overwrit\w*|migrat\w*)\b/], not:[]},
 {id:'set-model', hookName:'settings: model', kind:'setting',
  how:'The model setting in settings.json picks the default model for the session. It does not control which model a spawned agent gets.',
  any:[/\b(opus|sonnet|haiku)\b/, /default model/, /\bmodel\b[^.]{0,30}\b(default|main session|top)\b/],
  all:[/(default|main|primary|top|this repo|project|session)/], not:[]}
];

var KIND_LABEL = {deny:'Hook can deny', nudge:'Hook can nudge', setting:'Claude Code setting', none:'Prose only'};
var MARKER = /\b(must|never|always|do not|don't|dont|only|before|after|every|required|requires?|forbidden|stop|ask|deny|allow\w*|cannot|can't|shall|should)\b|\bno [a-z]/;

var EXAMPLE = [
'# Example team rules',
'',
'## Code',
'- Functions must stay under 40 lines.',
'- Every public function needs a test before it merges.',
'- Never commit directly to main. Open a pull request.',
'- Do not read or print the .env file or any private key.',
'- Never run sudo or rm -rf in a build step.',
'',
'## Agents',
'- Every subagent spawn must choose a model and an effort level on purpose.',
'- Never run tmux kill-server. Stop one session by name instead.',
'- Always use sonnet as the default model for the main session.',
'- Every new project directory must be under version control from its first file.',
'',
'## Notes',
'- Never let STATUS.md grow past 40 KB.',
'- Always write a decision down the moment it is made, not at the end of the day.',
'- If I correct you, record what you got wrong and why before you continue.',
'- Any deadline or appointment you note must also be scheduled as a reminder.',
'',
'## Style',
'- Always be concise in review comments.',
'- Explain tradeoffs before you pick an option.',
'- Prefer clear names over clever ones, and ask when a requirement is unclear.'
].join('\n');

function norm(s){ return s.toLowerCase().replace(/[‘’]/g,"'").replace(/`/g,''); }

function stripMd(line){
  var s = line.replace(/^\s*(?:>\s*)*/, '');
  if (/^\|/.test(s)) { s = s.replace(/^\|\s*/, '').replace(/\s*\|\s*$/, '').replace(/\s*\|\s*/g, ' '); }
  s = s.replace(/^\s*(?:[-*+]|\d+[.)])\s+/, '').replace(/^\[[ xX]\]\s+/, '');
  s = s.replace(/(\*\*|__)(.*?)\1/g, '$2');
  s = s.replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s).,;:!?]|$)/g, '$1$2');
  return s.replace(/`/g, '').replace(/\s+/g, ' ').trim();
}

function splitSentences(s){
  return s.replace(/([.!?])\s+(?=[A-Z0-9*_`"(\[])/g, '$1\u0001').split('\u0001').map(function(x){return x.trim();}).filter(Boolean);
}

var STRONG_CUE = /\b(never|always|must|do not|don't)\b/i;
function isRule(t){
  var s = String(t).trim();
  if (!MARKER.test(norm(s))) return false;
  var strong = STRONG_CUE.test(s);
  // too short to be a rule (unless it opens with a hard cue)
  if (s.split(/\s+/).length < 4 && !/^(no|never|do not|don't|always)\b/i.test(s)) return false;
  // a heading-style label ending in a colon, unless it carries a hard cue
  if (/:$/.test(s) && !/\b(never|always|must|do not|don't|every|should)\b/i.test(s)) return false;
  // a lowercase start is a wrapped continuation fragment, unless it carries a hard cue
  if (!/^[A-Z0-9"'(\[*]/.test(s) && !/\b(never|always|must|do not|don't|should)\b/i.test(s)) return false;
  // mostly code or paths: dense with brackets, slashes, equals, underscores
  if (!strong && (s.match(/[(){}\[\]=<>\/\\|_]/g) || []).length / s.length > 0.06) return false;
  // a description opening with an article or subject word, without a hard cue
  if (/^(This|These|There|The|It|Its|Their|They|We|Our|Each|A|An|Because|Since|That|Those|Not|Under|Replaced|Runs|Logic|Code|Staging|Orientation|Why|Both|Two)\b/.test(s) && !/\b(never|always|must|do not|don't|should)\b/i.test(s)) return false;
  // arrows and :: point at things, they do not state rules
  if (!strong && /[→↔←]|->|::/.test(s)) return false;
  return true;
}

function entryHits(e, t){
  var any = e.any.length === 0 || e.any.some(function(r){return r.test(t);});
  return any && e.all.every(function(r){return r.test(t);}) && !e.not.some(function(r){return r.test(t);});
}

function classify(text){
  var t = norm(text);
  for (var i = 0; i < CATALOG.length; i++) {
    if (entryHits(CATALOG[i], t)) { var e = CATALOG[i]; return {kind:e.kind, id:e.id, hookName:e.hookName, how:e.how}; }
  }
  return {kind:'none', id:'none', hookName:'none', how:'Nothing mechanical enforces this today.'};
}

var SHAPE_GROUPS = {"setting": ["model", "opus", "sonnet", "haiku", "gpt", "gemini", "claude-3", "claude-4", "claude-5", "permission", "permissions", "allow list", "allowlist", "deny list", "denylist", "ask before", "sandbox", "allowed tools", "allowedtools", "max turns", "max-turns", "effort"], "prohib": ["never", "don't", "do not", "no", "must not", "mustn't", "forbidden", "avoid", "prohibited", "not allowed"], "tool": ["commit", "push", "force", "merge", "main branch", "master", "delete", "rm", "remove files", "drop", "edit", "modify", "write", "touch", "run", "execute", "install", "deploy", "prod", "production", "secret", "credential", "token", ".env", "migrate", "database", "sudo", "git", "npm", "pip", "curl", "external", "network", "api key"], "oblig": ["always", "must", "before", "after", "every time", "each time", "run", "make sure", "ensure", "verify"], "chk": ["test", "tests", "lint", "linter", "format", "formatter", "build", "compile", "type-check", "typecheck", "review", "changelog", "docs", "documentation", "commit message", "coverage", "ci", "pre-commit", "snapshot", "update the"], "judg": ["prefer", "consider", "try to", "should be", "keep it", "readable", "clean", "idiomatic", "concise", "simple", "style", "tone", "naming", "comment", "clear", "consistent", "meaningful", "descriptive", "good", "best practice", "when possible", "where appropriate"]};

function shapeRe(list){
  return new RegExp('(?:^|[^a-z0-9])(?:' + list.map(function(w){ return w.replace(/[.*+?^${}()|[\]\\\-]/g, '\\$&'); }).join('|') + ')(?![a-z0-9])');
}
var SHAPE_RE = {};
Object.keys(SHAPE_GROUPS).forEach(function(k){ SHAPE_RE[k] = shapeRe(SHAPE_GROUPS[k]); });
var SHAPE_LABEL = {deny:'a deny hook (PreToolUse)', check:'a check after the fact (PostToolUse or Stop)', setting:'a settings entry', judgment:'nothing automatic: judgment or style', unclear:'unclear'};

function shape(line){
  var t = norm(String(line));
  if (SHAPE_RE.setting.test(t)) return 'setting';
  if (SHAPE_RE.prohib.test(t) && SHAPE_RE.tool.test(t)) return 'deny';
  if (SHAPE_RE.oblig.test(t) && SHAPE_RE.chk.test(t)) return 'check';
  if (SHAPE_RE.judg.test(t)) return 'judgment';
  return 'unclear';
}

function analyze(text){
  var lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  var inFence = false, rows = [];
  for (var n = 0; n < lines.length; n++) {
    var raw = lines[n], tr = raw.trim();
    if (/^(```|~~~)/.test(tr)) { inFence = !inFence; continue; }
    if (inFence || !tr) continue;
    if (/^#{1,6}(\s|$)/.test(tr)) continue;
    if (/^<!--/.test(tr)) continue;
    if (/^\|?\s*:?-{3,}[\s:|-]*$/.test(tr)) continue;
    var bullet = /^\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+/.test(raw);
    var s = stripMd(raw);
    if (!s) continue;
    if (/^<?(?:\S*:\/\/|www\.)\S+>?$/.test(s)) continue;
    if (bullet && s.split(' ').length < 4) continue;
    var pieces = s.length > 140 ? splitSentences(s) : [s];
    for (var p = 0; p < pieces.length; p++) {
      if (!isRule(pieces[p])) continue;
      var c = classify(pieces[p]);
      rows.push({line:n + 1, text:pieces[p], kind:c.kind, id:c.id, hookName:c.hookName, how:c.how, shape:c.kind === 'none' ? shape(pieces[p]) : ''});
    }
  }
  var counts = {deny:0, nudge:0, setting:0, none:0};
  var shapes = {deny:0, check:0, setting:0, judgment:0, unclear:0};
  rows.forEach(function(r){ counts[r.kind]++; if (r.shape) shapes[r.shape]++; });
  return {rows:rows, counts:counts, shapes:shapes, total:rows.length, summary:summaryLine(rows.length, counts)};
}

function summaryLine(total, c){
  if (total === 0) return 'No rule-like lines found. Rules usually contain words such as must, never, always or do not.';
  return total + (total === 1 ? ' rule-like line. ' : ' rule-like lines. ') +
    c.deny + ' could be denied by a hook, ' + c.nudge + ' nudged, ' + c.setting + ' ' + (c.setting === 1 ? 'is a setting' : 'are settings') + ', ' + c.none + ' ' + (c.none === 1 ? 'is' : 'are') + ' prose only.';
}

function cell(s){ return String(s).replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim(); }

function toMarkdown(res){
  var out = ['# CLAUDE.md analysis', '', res.summary, ''];
  if (res.rows.length) {
    out.push('| Line | Rule | Verdict | Enforced by | Could be enforced by | How |', '| --- | --- | --- | --- | --- | --- |');
    res.rows.forEach(function(r){
      out.push('| ' + r.line + ' | ' + cell(r.text) + ' | ' + KIND_LABEL[r.kind] + ' | ' + cell(r.hookName) + ' | ' + (r.shape ? SHAPE_LABEL[r.shape] : '-') + ' | ' + cell(r.how) + ' |');
    });
    out.push('');
    var sh = res.shapes;
    out.push('Of the ' + res.counts.none + ' lines nothing in the kit matches, by what could enforce them: a deny hook ' + sh.deny + ', a check after the fact ' + sh.check + ', a settings entry ' + sh.setting + ', judgment or style ' + sh.judgment + ', unclear ' + sh.unclear + '. Keyword-based, so treat it as a first read.', '');
  }
  out.push('Keyword matching only. A verdict names an area the free steward-kit covers. It does not prove your hooks are installed or would fire on your wording.');
  return out.join('\n') + '\n';
}

function toSummary(res){
  var n = res.total, c = res.counts;
  var l1 = n === 0 ? 'My CLAUDE.md: no rule-like lines found.' :
    'My CLAUDE.md: ' + n + ' rule-like lines. ' + (c.deny + c.nudge + c.setting) + ' have something in the free kit that can enforce them, ' + c.none + ' rely on the model remembering.';
  return l1 + '\n' + 'Check yours, nothing is uploaded: https://steward-kit.github.io/analyzer/';
}

if (typeof document === 'undefined') { globalThis.__analyzer = {analyze:analyze, toMarkdown:toMarkdown, toSummary:toSummary, CATALOG:CATALOG, EXAMPLE:EXAMPLE, shape:shape}; return; }

var $ = function(id){ return document.getElementById(id); };
var last = null;

function render(res){
  last = res;
  $('sum').textContent = res.summary;
  var tb = $('tb'); while (tb.firstChild) tb.removeChild(tb.firstChild);
  res.rows.forEach(function(r){
    var tr = document.createElement('tr');
    var a = document.createElement('td'); a.className = 'n'; a.textContent = String(r.line);
    var b = document.createElement('td'); b.textContent = r.text;
    var c = document.createElement('td'); var tag = document.createElement('span'); tag.className = 'tag v-' + r.kind; tag.textContent = KIND_LABEL[r.kind]; c.appendChild(tag);
    var d = document.createElement('td'); var code = document.createElement('code'); code.textContent = r.hookName; d.appendChild(code);
    var f = document.createElement('td'); f.textContent = r.shape ? SHAPE_LABEL[r.shape] : '-';
    var e = document.createElement('td'); e.textContent = r.how;
    [a,b,c,d,f,e].forEach(function(x){ tr.appendChild(x); });
    tb.appendChild(tr);
  });
  $('tbl').classList.toggle('hide', res.rows.length === 0);
  $('st').textContent = '';
  $('mdbox').classList.add('hide');
  $('res').classList.remove('hide');
}

$('go').addEventListener('click', function(){ render(analyze($('in').value)); });
$('ex').addEventListener('click', function(){ $('in').value = EXAMPLE; render(analyze(EXAMPLE)); });
$('clr').addEventListener('click', function(){ $('in').value = ''; last = null; $('res').classList.add('hide'); });
$('cp').addEventListener('click', function(){
  if (!last) { last = analyze($('in').value); render(last); }
  var md = toMarkdown(last), st = $('st');
  function fallback(){
    var box = $('mdbox'); box.value = md; box.classList.remove('hide'); box.focus(); box.select();
    var ok = false; try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    st.textContent = ok ? ' Copied.' : ' Copy failed. The report is selected below, copy it by hand.';
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(md).then(function(){ st.textContent = ' Copied.'; }, fallback);
  } else { fallback(); }
});
$('cps').addEventListener('click', function(){
  if (!last) { last = analyze($('in').value); render(last); }
  var md = toSummary(last), st = $('st');
  function fallback(){
    var box = $('mdbox'); box.value = md; box.classList.remove('hide'); box.focus(); box.select();
    var ok = false; try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    st.textContent = ok ? ' Copied.' : ' Copy failed. The report is selected below, copy it by hand.';
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(md).then(function(){ st.textContent = ' Copied.'; }, fallback);
  } else { fallback(); }
});
})();

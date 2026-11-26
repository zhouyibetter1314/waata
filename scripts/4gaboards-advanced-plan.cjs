// B11–B13 course harness only: the model proposes registered action names, never code, paths or selectors.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { parseEnv } = require('node:util');

const tasks = {
  B11: {goal: 'Move Second parcel above First parcel in the same list.',
    choices: ['drag First parcel before Second parcel', 'drag Second parcel before First parcel'], length: 1},
  B12: {goal: 'From the board, export a .tgz without attachments.',
    choices: ['submit export', 'open board settings', 'skip attachments', 'open export options'], length: 4},
  B13: {goal: 'Create a named board in the open project by importing the prepared 4gaBoards archive. Do not import users or project managers.',
    choices: ['submit import', 'attach registered archive', 'enter board name', 'open import options', 'open add-board form'], length: 5},
};

function validate(plan, ids = Object.keys(tasks)) {
  assert(ids.length && ids.every(id => Object.hasOwn(tasks, id)), 'Unknown advanced scenario');
  assert(plan && typeof plan === 'object' && Object.keys(plan).sort().join(',') === [...ids].sort().join(','), 'Unexpected scenario set');
  for (const id of ids) {
    const task = tasks[id];
    const steps = plan[id];
    assert(Array.isArray(steps) && steps.length === task.length && new Set(steps).size === task.length
      && steps.every(step => task.choices.includes(step)), `Invalid action plan for ${id}`);
  }
  return plan;
}

async function propose(envFile, ids = Object.keys(tasks)) {
  assert(ids.length && ids.every(id => Object.hasOwn(tasks, id)), 'Unknown advanced scenario');
  const selected = Object.fromEntries(ids.map(id => [id, tasks[id]]));
  const config = parseEnv(readFileSync(envFile, 'utf8'));
  const model = config.WAATA_MODEL_NAME;
  const endpoint = new URL(config.WAATA_MODEL_BASE_URL);
  assert(endpoint.protocol === 'https:' && !endpoint.username && !endpoint.password && !endpoint.search && !endpoint.hash,
    'Expected an HTTPS model endpoint');
  if (!endpoint.pathname.endsWith('/chat/completions')) endpoint.pathname = endpoint.pathname.replace(/\/+$/, '') + '/chat/completions';
  const options = {model, stream: false, max_tokens: ids.length === 1 ? 120 : 450, messages: [
    {role: 'system', content: 'Output only a JSON object keyed by the supplied scenario IDs. Each value is an ordered array of exact action names chosen to achieve the goal. No code or prose.'},
    {role: 'user', content: JSON.stringify(selected)},
  ]};
  if (['ark.cn-beijing.volces.com', 'api.deepseek.com'].includes(endpoint.hostname)) options.thinking = {type: 'disabled'};
  const response = await fetch(endpoint, {method: 'POST', redirect: 'error', signal: AbortSignal.timeout(25000),
    headers: {'Content-Type': 'application/json', Authorization: `Bearer ${config.WAATA_MODEL_API_KEY}`}, body: JSON.stringify(options)});
  if (!response.ok) throw new Error(`Model request returned HTTP ${response.status}`);
  const body = await response.json();
  const content = body.choices?.[0]?.message?.content;
  assert(typeof content === 'string', 'Model did not return a plan');
  let plan;
  try { plan = JSON.parse(content.trim().replace(/^```(?:json)?\s*|\s*```$/g, '')); }
  catch { throw new Error('Model returned invalid JSON'); }
  return {model, requests: 1, tokens: body.usage?.total_tokens ?? null, plan: validate(plan, ids)};
}

module.exports = {validate, propose};

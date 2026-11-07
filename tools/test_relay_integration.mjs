// Optional cross-repository integration: real CAP HTTP/MCP, synthetic execution.
// node tools/test_relay_integration.mjs <CAP source root> <Python executable>
// Uses a private data directory, port 0 and scratch Git repository. No providers.
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';

const run = promisify(execFile);
const cap = path.resolve(process.argv[2]);
const python = path.resolve(process.argv[3]);
const source = fileURLToPath(new URL('../skills/project-brain/scripts/', import.meta.url));
const load = name => import(pathToFileURL(path.join(cap, 'src', name)).href);
const { configSchema } = await load('config.js');
const { Store } = await load('store.js');
const { Pool } = await load('pool.js');
const { createServer } = await load('server.js');
const root = mkdtempSync(path.join(tmpdir(), 'pb-relay-integration-'));
const workspace = path.join(root, 'project');
const state = path.join(root, 'pool');
mkdirSync(workspace); mkdirSync(state);
const command = JSON.stringify([process.execPath, path.join(cap, 'bin', 'pool.js')]);
const env = { ...process.env, CLI_AGENT_POOL_HOME: state, PB_AGENT_POOL_COMMAND: command, PYTHONDONTWRITEBYTECODE: '1' };
delete env.CLI_AGENT_POOL_WORKER; delete env.CLI_AGENT_POOL_TASK_TOKEN; delete env.CLI_AGENT_POOL_TASK_ID; delete env.PB_RELAY_TOKEN;
const git = (...args) => run('git', ['-c', 'user.name=Fixture Human', '-c', 'user.email=human@example.invalid', '-c', 'commit.gpgsign=false', ...args], { cwd: workspace, windowsHide: true });
const report = JSON.stringify({ status: 'completed', summary: 'Synthetic director completed', files: [], checks: [], research: [], blockers: [] });
let pool, store, app;
try {
  await git('init', '-q', '-b', 'main');
  writeFileSync(path.join(workspace, 'initial.txt'), 'scratch\n');
  await git('add', '.'); await git('commit', '-q', '-m', 'Scratch baseline');
  const origin = path.join(root, 'origin.git');
  await git('init', '-q', '--bare', origin);
  await git('remote', 'add', 'origin', origin);
  await git('push', '-q', 'origin', 'main');
  const fixtureSkill = path.join(root, 'skill');
  mkdirSync(path.join(fixtureSkill, 'scripts'), { recursive: true });
  writeFileSync(path.join(fixtureSkill, 'SKILL.md'), '# Synthetic director fixture\nRead the relay contract.\n');
  const wrapper = path.join(fixtureSkill, 'scripts', 'brain.py');
  writeFileSync(wrapper, `import os,sys\nsys.path.insert(0,${JSON.stringify(source)})\nos.environ['PB_AGENT_POOL_COMMAND']=${JSON.stringify(command)}\nimport brain\nsys.exit(brain.main())\n`);
  const config = configSchema.parse({ python, directorReadRoots: [fixtureSkill, path.dirname(source), path.join(process.env.USERPROFILE || process.env.HOME || root, '.skills-manager', 'skills'), path.join(process.env.USERPROFILE || process.env.HOME || root, '.agents', 'skills')], routes: ['bad', 'good'].map(id => ({
    id, adapter: 'claude', executable: process.execPath, enabled: true, billing: 'subscription', trustedSettings: true,
    models: [{ id: 'synthetic', alias: 'Synthetic', group: 'high', kinds: ['write'] }],
  })) });
  store = new Store(path.join(state, 'pool.sqlite'));
  pool = new Pool(config, store, { directory: state, settleMs: 0, checkAuth: async () => {},
    execute: (route, model, task, py, progress, directory, context) => {
      const done = (async () => {
        if (context.promptOverride) {
          // Synthetic native-tool observations; CAP verifies the actual probe artifacts.
          const prompt = context.promptOverride;
          const probe = /node "([^"]+probe\.mjs)"/.exec(prompt)[1];
          for (const step of ['shell-a', 'shell-b', 'shell-c', 'commit', 'remote', 'service'])
            await run(process.execPath, [probe, step], { cwd: workspace, windowsHide: true });
          context.watch.events.push(['shell-a', 'shell-b', 'shell-c']);
          pool.preflightAck(/"nonce":"([a-f0-9]{64})"/.exec(prompt)[1], context.token);
          const read = /file-read tool, read (.+?)\. Write line (\d+) of it exactly, with no other text, into (.+?) using/.exec(prompt);
          writeFileSync(read[3], readFileSync(read[1], 'utf8').split(/\r?\n/)[Number(read[2]) - 1]);
          for (const item of context.watch.reads) item.nativeRead = true;
          return { result: report };
        }
        if (route.id === 'bad') return { error: 'PERMISSION_REQUIRED', detail: 'Synthetic failure before takeover' };
        const taskEnv = { ...env, ...context.secretEnv, CLI_AGENT_POOL_WORKER: '1', CLI_AGENT_POOL_TASK_ID: context.taskId, CLI_AGENT_POOL_TASK_TOKEN: context.token };
        const taken = await run(python, ['-B', wrapper, 'relay', 'takeover', workspace], { env: taskEnv, windowsHide: true });
        assert.equal(JSON.parse(taken.stdout).status, 'ACTIVE');
        writeFileSync(path.join(workspace, 'relay.txt'), 'Taken over through real CAP RPC\n');
        await git('add', 'relay.txt'); await git('commit', '-q', '-m', 'Complete scratch relay');
        await git('push', '-q', 'origin', 'main');
        await run(python, ['-B', wrapper, 'relay', 'complete', workspace], { env: taskEnv, windowsHide: true });
        return { result: report };
      })().catch(error => ({ error: 'FIXTURE_FAILED', detail: String(error.stderr || error.stack || error) }));
      return { done, cancel() {} };
    },
  });
  pool.getQuota = async () => ({ status: 'available', windows: [{ name: 'synthetic', remainingPercent: 80 }] });
  const token = randomBytes(32).toString('hex');
  const management = randomBytes(32).toString('hex');
  app = createServer(pool, token, 0, { directory: state, token: management });
  config.port = (await app.listen()).port;
  writeFileSync(path.join(state, 'config.json'), JSON.stringify(config));
  writeFileSync(path.join(state, 'access-token'), token);
  writeFileSync(path.join(state, 'management-token'), management);
  const driver = path.join(root, 'driver.py');
  writeFileSync(driver, `import sys,json,os\nfrom pathlib import Path\nsys.path.insert(0,${JSON.stringify(source)})\nimport brain as B, runtime_executor_policy as E, runtime_relay as R, runtime_agent_pool as A\nroot=Path(${JSON.stringify(workspace)})\nB.cmd_init(root)\nB.set_session_modes(root,'SOLO','SOLO',new=True,task_mode='execute')\np={'schema':1,'execution':{'source':'solo'},'scheduling':{'mode':'serial','max_parallel':1},'quota_recovery':{'enabled':False,'threshold_percent':10},'relay':{'enabled':True,'threshold_percent':10,'candidates':[{'route':'bad','model':'synthetic'},{'route':'good','model':'synthetic'}]}}\nE.save(B,root,p,'Synthetic relay integration')\nE.confirm(B,root,'Test fixture confirmed')\np=E.load(B,root)\nstart=R.start(B,root,p,'launcher',rpc=A.rpc,brain_script=${JSON.stringify(wrapper)})\nassert start['readiness']=='verified'\ndef checkpoint(*args):\n path=root/'.project-brain/checkpoint.json'\n path.write_text(json.dumps({'next':'Finish scratch relay'}))\n return path\nresult=R.handoff(B,root,p,{'id':'PB-001'},'Finish scratch relay',${JSON.stringify(wrapper)},A.rpc,token=start['token'],write_checkpoint=checkpoint)\nassert result['status']=='HANDED_OFF'\nprint('Handoff submitted')\n`);
  await run(python, ['-B', driver], { env, windowsHide: true, timeout: 120000 });
  const relayFile = path.join(workspace, '.project-brain', '.cache', 'relay.json');
  let relay;
  for (let i = 0; i < 600; i++) {
    relay = JSON.parse(readFileSync(relayFile, 'utf8'));
    if (relay.status === 'COMPLETED' && pool.active.size === 0) break;
    if (relay.status === 'EXHAUSTED') throw new Error(JSON.stringify({ relay, tasks: pool.list(20, 0) }));
    await delay(100);
  }
  assert.equal(relay.status, 'COMPLETED', JSON.stringify({ relay, tasks: pool.list(20, 0) }));
  assert.equal(relay.director.route, 'good');
  assert.deepEqual(relay.history.map(row => row.event), ['START', 'HANDOFF', 'FAILOVER', 'TAKEOVER', 'COMPLETE']);
  const director = pool.get(relay.director.task_id);
  assert.equal(director.state, 'succeeded', JSON.stringify(director));
  assert.ok(director.events.some(event => event.kind === 'ack'));
  assert.equal(readFileSync(path.join(workspace, 'relay.txt'), 'utf8'), 'Taken over through real CAP RPC\n');
  console.log(JSON.stringify({ result: 'PASS', transport: 'real CAP HTTP/MCP and Python CLI', execution: 'synthetic native executor', events: relay.history.map(row => row.event), directorState: director.state }));
} finally {
  await pool?.close();
  app?.server.close(); app?.server.closeAllConnections();
  store?.close();
  assert.equal(path.dirname(root), path.resolve(tmpdir()));
  await rm(root, { recursive: true, force: true, maxRetries: 10 });
}

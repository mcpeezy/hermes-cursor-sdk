// Exercise the real worker with an entirely mocked SDK and filesystem. No network or credentials.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';

const workerPath = resolve(dirname(fileURLToPath(import.meta.url)), '../worker.mjs');
const workerSource = await readFile(workerPath, 'utf8');

const scenarios = [
  { withTools: false },
  { withTools: true },
  { withTools: true, callbackContext: { toolCallId: 'sdk-exact:01/keep-this-id' } },
  { withTools: true, callbackContext: {} },
  { withTools: false, sdkError: { message: 'Upstream model server interrupted: sensitive-sentinel' }, expectedError: 'runtime_failure' },
  { withTools: false, sdkError: { message: 'Unable to connect to model provider: sensitive-sentinel' }, expectedError: 'upstream_connection' },
  { withTools: false, sdkError: { message: 'Please acknowledge data retention policy for this model: sensitive-sentinel' }, throwAtCreate: true, expectedError: 'data_policy_acknowledgment' },
  { withTools: false, sdkError: { code: 'model_not_found', message: 'sensitive-sentinel' }, expectedError: 'model_selection' },
  { withTools: false, sdkError: { message: 'Unsupported model: sensitive-sentinel' }, expectedError: 'model_selection' },
  { withTools: false, sdkError: { message: 'Project not found: sensitive-sentinel' }, expectedError: 'runtime_failure' },
  { withTools: false, sdkError: { code: 'review_data_policy', message: 'sensitive-sentinel' }, expectedError: 'data_policy_acknowledgment' },
  { withTools: false, sdkError: { code: 'resource_exhausted', message: 'sensitive-sentinel' }, expectedError: 'quota' },
  { withTools: false, sdkError: { code: 'unauthenticated', message: 'sensitive-sentinel' }, expectedError: 'authentication' },
  { withTools: false, sdkError: { message: 'Forbidden: sensitive-sentinel' }, expectedError: 'permission' },
  { withTools: false, sdkError: { message: "unknown option 'sensitive-sentinel'" }, throwAtCreate: true, expectedError: 'transport_failure' },
];
for (const { withTools, callbackContext, sdkError, throwAtCreate, expectedError } of scenarios) {
  const label = callbackContext ? `worker preserves callback ID ${callbackContext.toolCallId ?? '(not supplied)'}` :
    expectedError ? `worker classifies ${sdkError.code || sdkError.message}` : `worker isolates tool ownership (Hermes tools: ${withTools})`;
  test(label, async () => {
    const files = new Map();
    const directories = [];
    let options, receipt, exitCode;
    const input = { model: { id: 'offline-model' }, instructions: 'offline transport rule', conversation: 'offline conversation',
      tools: withTools ? [{ function: { name: 'hermes_fixture', description: 'Offline only', parameters: { type: 'object' } } }] : [] };
    let exited;
    const finished = new Promise(resolve => { exited = resolve; });
    const processStub = {
      umask: () => {}, on: () => {}, execPath: process.execPath, env: { CURSOR_API_KEY: 'offline-test-not-a-key' },
      stdin: { async *[Symbol.asyncIterator]() { yield JSON.stringify(input); } },
      stdout: { write(text, callback) { receipt = JSON.parse(text.split('HERMES_CURSOR_SDK_RESPONSE ')[1]); callback(); } },
      exit(code) { exitCode = code; exited(); },
    };
    const context = vm.createContext({ process: processStub, setTimeout: () => 1, clearTimeout: () => {}, setImmediate });
    const modules = {
      '@cursor/sdk': {
        Agent: { async create(value) {
          options = value;
          if (throwAtCreate) throw new Error(sdkError.message);
          return {
            async send() { return { async *stream() {}, async cancel() {}, async wait() {
              if (callbackContext) {
                options.local.customTools.hermes_fixture.execute({ fixture: 'offline' }, callbackContext);
                await finished;
              }
              return sdkError ? { status: 'failed', error: sdkError } : { status: 'finished', result: 'offline reply' };
            } }; },
            async [Symbol.asyncDispose]() {},
          };
        } },
        JsonlLocalAgentStore: class { constructor(path) { this.path = path; } },
      },
      'node:fs/promises': {
        async mkdir(path, opts) { directories.push([path, opts]); },
        async writeFile(path, text, opts) { files.set(path, { text, opts }); },
        async readFile() { throw new Error('unexpected filesystem read'); },
      },
      'node:child_process': { spawnSync(command, args, opts) {
        assert.equal(command, 'git');
        assert.equal(args.join(' '), 'init -q -b hermes-cursor-sdk');
        assert.equal(opts.cwd, options?.local.cwd ?? resolve(dirname(workerPath), 'runtime/offline-worker-test'));
        return { status: 0 };
      } },
      'node:path': { dirname, resolve },
      'node:url': { fileURLToPath },
      'node:crypto': { randomUUID: () => 'offline-worker-test' },
    };
    const worker = new vm.SourceTextModule(workerSource, {
      context, identifier: workerPath, initializeImportMeta(meta) { meta.url = new URL(`file://${workerPath}`).href; },
    });
    await worker.link(async specifier => {
      assert.ok(Object.hasOwn(modules, specifier), `unexpected import: ${specifier}`);
      const exports = modules[specifier];
      return new vm.SyntheticModule(Object.keys(exports), function() {
        for (const [name, value] of Object.entries(exports)) this.setExport(name, value);
      }, { context });
    });
    await worker.evaluate();
    await finished;
    assert.equal(exitCode, expectedError ? 1 : 0);
    assert.equal(receipt.status, callbackContext ? 'tool_request' : throwAtCreate ? 'setup' : sdkError ? 'failed' : 'finished');
    assert.equal(receipt.error, expectedError);
    assert.equal(JSON.stringify(receipt).includes('sensitive-sentinel'), false);
    assert.equal(receipt.native_tool_events, 0);
    assert.equal(receipt.agent_disposed, !throwAtCreate);
    if (callbackContext) {
      assert.equal(receipt.tool_calls.length, 1);
      assert.equal(receipt.tool_calls[0].id, callbackContext.toolCallId);
      assert.equal(Object.hasOwn(receipt.tool_calls[0], 'id'), Object.hasOwn(callbackContext, 'toolCallId'));
    }
    assert.equal(JSON.stringify(options.tools), JSON.stringify(withTools ? ['mcp'] : []));
    assert.equal(JSON.stringify(options.agents), '{}');
    assert.equal(JSON.stringify(options.mcpServers), '{}');
    assert.equal(Object.hasOwn(options, 'systemPrompt'), false);
    assert.equal(JSON.stringify(options.local.settingSources), '["project"]');
    assert.equal(options.local.enableAgentRetries, false);
    assert.equal(options.local.autoReview, false);
    assert.equal(JSON.stringify(Object.keys(options.local.customTools)), JSON.stringify(withTools ? ['hermes_fixture'] : []));
    assert.equal(options.local.cwd, resolve(dirname(workerPath), 'runtime/offline-worker-test'));
    assert.equal(directories.length, 1);
    assert.equal(directories[0][1].mode, 0o700);
    assert.equal(files.size, 2);
    const hooks = files.get(resolve(options.local.cwd, '.cursor/hooks.json'));
    assert.equal(hooks.opts.mode, 0o600);
    const hookConfig = JSON.parse(hooks.text);
    assert.equal(hookConfig.version, 1);
    for (const event of ['preToolUse', 'beforeMCPExecution']) {
      assert.equal(hookConfig.hooks[event].length, 1);
      assert.equal(hookConfig.hooks[event][0].failClosed, true);
      assert.ok(hookConfig.hooks[event][0].command.includes('tool-policy.mjs'));
    }
    const rule = files.get(resolve(options.local.cwd, '.cursor/rules/hermes.mdc'));
    assert.ok(rule.text.includes('alwaysApply: true'));
    assert.ok(rule.text.endsWith(input.instructions + '\n'));
    assert.equal(rule.opts.mode, 0o600);
  });
}

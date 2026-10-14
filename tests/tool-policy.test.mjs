// Actual hook subprocess tests; fixtures only, no SDK inference or credentials.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const hook = fileURLToPath(new URL('../tool-policy.mjs', import.meta.url));
const offered = ['hermes_fixture'];
function decision(input, names = offered) {
  const result = spawnSync(process.execPath, [hook, JSON.stringify(names)], {
    input: typeof input === 'string' ? input : JSON.stringify(input), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout).permission;
}
for (const name of ['Shell', 'Read', 'Write', 'Task', 'WebFetch', 'Delete', 'unknown']) {
  test(`reject native ${name} before execution`, () => {
    assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: name, tool_input: {} }), 'deny');
  });
}
test('allow discovery metadata but not generic MCP invocation', () => {
  assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: 'GetMcpTools' }), 'allow');
  assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: 'CallMcpTool' }), 'deny');
});
test('allow only offered MCP tool names at preToolUse', () => {
  assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: 'MCP:hermes_fixture' }), 'allow');
  assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: 'MCP:shell' }), 'deny');
});
test('MCP execution requires the exact in-process Hermes server and offered tool', () => {
  const input = { hook_event_name: 'beforeMCPExecution', tool_name: 'hermes_fixture', mcp_server_name: 'custom-user-tools' };
  assert.equal(decision(input), 'allow');
  assert.equal(decision({ ...input, mcp_server_name: 'external-server' }), 'deny');
  assert.equal(decision({ ...input, tool_name: 'unoffered' }), 'deny');
  assert.equal(decision({ ...input, mcp_server_name: undefined }), 'deny');
});
test('tool_choice none denies every MCP callback', () => {
  assert.equal(decision({ hook_event_name: 'preToolUse', tool_name: 'MCP:hermes_fixture' }, []), 'deny');
  assert.equal(decision({ hook_event_name: 'beforeMCPExecution', tool_name: 'hermes_fixture', mcp_server_name: 'custom-user-tools' }, []), 'deny');
});
test('malformed, missing, or unrelated hook data fails closed', () => {
  for (const input of ['not-json', 'null', '{}', '{"tool_name":"MCP:hermes_fixture"}', '[]']) {
    assert.equal(decision(input), 'deny');
  }
});

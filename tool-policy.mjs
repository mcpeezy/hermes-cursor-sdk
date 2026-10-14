// Cursor project hooks: only metadata discovery and the offered Hermes MCP tools.
// No native action or external MCP server is permitted to execute.
let permission = 'deny';
try {
  const names = new Set(JSON.parse(process.argv[2]));
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  const input = JSON.parse(raw);
  if (input?.hook_event_name === 'preToolUse') {
    if (input.tool_name === 'GetMcpTools') permission = 'allow';
    if (typeof input.tool_name === 'string' && input.tool_name.startsWith('MCP:') && names.has(input.tool_name.slice(4))) permission = 'allow';
  } else if (input?.hook_event_name === 'beforeMCPExecution') {
    if (input.mcp_server_name === 'custom-user-tools' && names.has(input.tool_name)) permission = 'allow';
  }
} catch { /* Any invalid configuration or input denies the action. */ }
process.stdout.write(JSON.stringify({ permission, user_message: permission === 'deny' ? 'Use the offered Hermes tools. Cursor-native actions are disabled.' : undefined }));

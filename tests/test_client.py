import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import CursorSDKClient, CursorSDKError

TOOLS = [{"type": "function", "function": {"name": "hermes_echo", "description": "Harmless echo", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}]

class ClientTests(unittest.TestCase):
    def test_native_controls_reach_official_sdk_payload(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result': 'OK'}) as invoke:
            client.create(model='gpt-5.4', messages=[], cursor_reasoning={'enabled': True, 'effort': 'high'},
                          cursor_fast=False, speed='fast')
        sent = invoke.call_args.args[0]['model']
        self.assertEqual(sent['id'], 'gpt-5.4')
        self.assertIn({'id': 'reasoning', 'value': 'high'}, sent['params'])
        self.assertIn({'id': 'fast', 'value': 'true'}, sent['params'])

    def test_unsupported_controls_stop_before_sdk_inference(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke') as invoke:
            with self.assertRaises(CursorSDKError):
                client.create(model='gemini-4-argon', messages=[], speed='fast')
        invoke.assert_not_called()

    def test_literal_tool_example_is_not_executed(self):
        text = '<tool_call>{"name":"hermes_echo","arguments":{"text":"DO NOT RUN"}}</tool_call>'
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result':text}):
            result = client.create(model='composer-2.5', messages=[], tools=TOOLS)
        self.assertIsNone(result.choices[0].message.tool_calls)
        self.assertEqual(result.choices[0].message.content, text)

    def test_sdk_callback_request_returns_to_hermes(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls':[{'name':'hermes_echo','arguments':{'text':'OK'}}]}) as invoke:
            result = client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS)
        self.assertEqual(result.choices[0].message.tool_calls[0].function.name, 'hermes_echo')
        self.assertEqual(result.choices[0].message.tool_calls[0].function.arguments, '{"text": "OK"}')
        self.assertEqual(invoke.call_args.args[0]['tools'], TOOLS)

    def test_sdk_callback_cannot_request_unoffered_tool(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls':[{'name':'shell','arguments':{}}]}):
            with self.assertRaises(CursorSDKError):
                client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS)

    def test_generated_tool_call_ids_are_unique_across_turns_and_clients(self):
        ids = []
        for client in (CursorSDKClient(), CursorSDKClient()):
            with patch.object(client, '_invoke', return_value={'tool_calls': [{'name': 'hermes_echo', 'arguments': {'text': 'OK'}}]}):
                for _ in range(2):
                    result = client.create(model='composer-2.5', messages=[], tools=TOOLS)
                    ids.append(result.choices[0].message.tool_calls[0].id)
        self.assertEqual(len(set(ids)), len(ids))

    def test_tool_choice_none_removes_sdk_callbacks(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result':'OK'}) as invoke:
            client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS, tool_choice='none')
        self.assertEqual(invoke.call_args.args[0]['tools'], [])

    def test_native_tool_call_is_returned_not_executed(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls': [{'id':'one','function':{'name':'hermes_echo','arguments':'{"text":"OK"}'}}], 'usage': {}}):
            result = client.chat.completions.create(model='composer-2.5', messages=[{'role':'user','content':'Echo'}], tools=TOOLS)
        self.assertEqual(result.choices[0].message.tool_calls[0].function.name, 'hermes_echo')
        self.assertEqual(result.choices[0].finish_reason, 'tool_calls')

    def test_unoffered_tool_is_denied(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls': [{'function':{'name':'shell','arguments':'{}'}}]}):
            with self.assertRaises(CursorSDKError):
                client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS)

    def test_flat_model_tool_format_preserves_arguments(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls': [{'name':'hermes_echo','arguments':{'text':'OK'}}]}):
            result = client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS)
        self.assertEqual(result.choices[0].message.tool_calls[0].function.arguments, '{"text": "OK"}')

    def test_malformed_tool_request_fails_closed(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'tool_calls': [None]}):
            with self.assertRaises(CursorSDKError):
                client.chat.completions.create(model='composer-2.5', messages=[], tools=TOOLS)

    def test_system_is_not_downgraded_to_user_payload(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result':'OK'}) as invoke:
            client.chat.completions.create(model='composer-2.5', messages=[{'role':'system','content':'SECRET_MARKER'}, {'role':'user','content':'Go'}])
        payload = invoke.call_args.args[0]
        self.assertIn('SECRET_MARKER', payload['instructions'])
        self.assertNotIn('SECRET_MARKER', payload['conversation'])

    def test_stream_is_openai_shaped(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result':'OK', 'usage': {'inputTokens': 12, 'outputTokens': 2}}):
            chunks = client.chat.completions.create(model='composer-2.5', messages=[], stream=True)
        self.assertEqual(chunks[0].choices[0].delta.content, 'OK')
        self.assertEqual(chunks[-1].usage.total_tokens, 14)

    def test_worker_failures_are_terminal_without_retry(self):
        cases = [
            ('ordinary stdout', 0, 'framing failed'),
            ('HERMES_CURSOR_SDK_RESPONSE {}\nHERMES_CURSOR_SDK_RESPONSE {}', 0, 'framing failed'),
            ('HERMES_CURSOR_SDK_RESPONSE not-json', 0, 'invalid transport data'),
            ('HERMES_CURSOR_SDK_RESPONSE ' + json.dumps({'native_tool_events': 1}), 0, 'request stopped'),
            ('HERMES_CURSOR_SDK_RESPONSE ' + json.dumps({'error': 'model_selection'}), 1, 'model_selection'),
            ('HERMES_CURSOR_SDK_RESPONSE ' + json.dumps({'error': 'data_policy_acknowledgment'}), 1, 'data_policy_acknowledgment'),
        ]
        for stdout, returncode, error in cases:
            with self.subTest(error=error, stdout=stdout):
                process = Mock(returncode=returncode)
                process.communicate.return_value = (stdout, '')
                process.poll.return_value = returncode
                client = CursorSDKClient()
                with patch('client.load_cursor_key', return_value='offline-test-not-a-key'), \
                     patch('client.shutil.which', return_value='/offline/node'), \
                     patch('client.subprocess.Popen', return_value=process) as popen:
                    with self.assertRaisesRegex(CursorSDKError, error):
                        client.create(model='gpt-5.4', messages=[])
                popen.assert_called_once()
                self.assertIsNone(client._process)

    def test_worker_timeout_terminates_only_its_own_process(self):
        process = Mock(returncode=None)
        process.poll.return_value = None
        process.communicate.side_effect = subprocess.TimeoutExpired('offline-node', 1)
        client = CursorSDKClient(request_timeout=1)
        with patch('client.load_cursor_key', return_value='offline-test-not-a-key'), \
             patch('client.shutil.which', return_value='/offline/node'), \
             patch('client.subprocess.Popen', return_value=process) as popen:
            with self.assertRaisesRegex(CursorSDKError, 'cancelled; no API fallback'):
                client.create(model='gpt-5.4', messages=[])
        popen.assert_called_once()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=12)
        process.kill.assert_not_called()
        self.assertIsNone(client._process)

    def test_unknown_model_fails_before_network(self):
        client = CursorSDKClient()
        with patch.object(client, '_invoke') as invoke:
            with self.assertRaises(CursorSDKError):
                client.chat.completions.create(model='not-a-catalog-model', messages=[])
        invoke.assert_not_called()

if __name__ == '__main__':
    unittest.main()

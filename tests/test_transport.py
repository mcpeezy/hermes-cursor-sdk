"""Offline acceptance across the production profile, transport and SDK client."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.transports.chat_completions import ChatCompletionsTransport

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    '_cursor_transport_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)],
)
assert SPEC is not None and SPEC.loader is not None
PLUGIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLUGIN
with patch('providers.register_provider'):
    SPEC.loader.exec_module(PLUGIN)


class TransportTests(unittest.TestCase):
    def test_current_controls_reach_sdk_payload_through_transport(self):
        cases = [
            ('gpt-5.4', None, {}, None, 'false'),
            ('gpt-5.4', {'enabled': True, 'effort': 'high'}, {}, 'high', 'false'),
            ('gpt-5.4', {'enabled': False}, {}, 'none', 'false'),
            ('gpt-5.4', {'enabled': True, 'effort': 'high'}, {'speed': 'fast'}, 'high', 'true'),
        ]
        for model, reasoning, overrides, effort, fast in cases:
            with self.subTest(model=model, reasoning=reasoning, overrides=overrides):
                kwargs = ChatCompletionsTransport().build_kwargs(
                    model, [{'role': 'user', 'content': 'Offline fixture'}], [],
                    provider_profile=PLUGIN.PROFILE, reasoning_config=reasoning,
                    request_overrides=overrides,
                )
                client = PLUGIN.CursorSDKClient()
                with patch.object(client, '_invoke', return_value={'result': 'Fixture'}) as invoke:
                    client.create(**kwargs)
                selected = invoke.call_args.args[0]['model']
                params = {item['id']: item['value'] for item in selected.get('params', [])}
                self.assertEqual(selected['id'], model)
                self.assertEqual(params.get('fast'), fast)
                if effort is not None:
                    self.assertEqual(params.get('reasoning'), effort)

    def test_fast_off_overrides_a_saved_fast_alias(self):
        selections = PLUGIN.catalog.selections()
        alias = next(key for key, value in selections.items()
                     if value['id'] == 'gpt-5.4'
                     and {'id': 'fast', 'value': 'true'} in value.get('params', []))
        kwargs = ChatCompletionsTransport().build_kwargs(
            alias, [], [], provider_profile=PLUGIN.PROFILE,
        )
        client = PLUGIN.CursorSDKClient()
        with patch.object(client, '_invoke', return_value={'result': 'Fixture'}) as invoke:
            client.create(**kwargs)
        self.assertIn({'id': 'fast', 'value': 'false'}, invoke.call_args.args[0]['model']['params'])

    def test_published_advanced_aliases_reach_sdk_payload_through_transport(self):
        checked = 0
        for alias, selection in PLUGIN.catalog.selections().items():
            params = {item['id']: item['value'] for item in selection['params']}
            advanced = {key: value for key, value in params.items()
                        if key not in PLUGIN.catalog.NATIVE_KEYS}
            if not advanced:
                continue
            with self.subTest(alias=alias):
                kwargs = ChatCompletionsTransport().build_kwargs(
                    alias, [], [], provider_profile=PLUGIN.PROFILE,
                    request_overrides={'speed': 'fast'} if params.get('fast') == 'true' else {},
                )
                client = PLUGIN.CursorSDKClient()
                with patch.object(client, '_invoke', return_value={'result': 'Fixture'}) as invoke:
                    client.create(**kwargs)
                selected = invoke.call_args.args[0]['model']
                sent = {item['id']: item['value'] for item in selected['params']}
                self.assertEqual(selected['id'], selection['id'])
                for key, value in advanced.items():
                    self.assertEqual(sent.get(key), value)
                checked += 1
        self.assertGreater(checked, 0)

    def test_unsupported_fast_stops_before_sdk_after_assembly(self):
        kwargs = ChatCompletionsTransport().build_kwargs(
            'gemini-4-argon', [], [], provider_profile=PLUGIN.PROFILE,
            request_overrides={'speed': 'fast'},
        )
        client = PLUGIN.CursorSDKClient()
        with patch.object(client, '_invoke') as invoke:
            with self.assertRaises(PLUGIN.CursorSDKError):
                client.create(**kwargs)
        invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main()

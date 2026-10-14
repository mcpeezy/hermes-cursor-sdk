"""Offline coverage of catalog normalization and native request options."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cursor_catalog", ROOT / "catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    def test_picker_contains_each_base_once_and_retains_all_saved_ids(self):
        selections = catalog.selections()
        models = catalog.models()
        self.assertEqual(set(models), {v["id"] for v in selections.values()})
        self.assertEqual(len(models), len(set(models)))
        for model, original in selections.items():
            self.assertEqual(catalog.resolve(model), original)

    def test_three_effort_spellings_map_to_the_catalog(self):
        for model, key in [("grok-4.7", "reasoning_effort"),
                           ("claude-opus-5-5", "effort"), ("gpt-5.4", "reasoning")]:
            selected = catalog.resolve(model, reasoning={"enabled": True, "effort": "high"})
            self.assertEqual(dict((p["id"], p["value"]) for p in selected["params"])[key], "high")

    def test_effort_clamps_without_increasing_it(self):
        selected = catalog.resolve("gemini-4-argon", reasoning={"effort": "ultra"})
        self.assertEqual(selected["params"], [{"id": "reasoning_effort", "value": "high"}])

    def test_thinking_off_uses_boolean_or_reasoning_none(self):
        for model, key, value in [("claude-sonnet-4-5", "thinking", "false"),
                                  ("gpt-5.4", "reasoning", "none")]:
            selected = catalog.resolve(model, reasoning={"enabled": False})
            self.assertIn({"id": key, "value": value}, selected["params"])

    def test_thinking_off_accepts_none_on_each_effort_parameter(self):
        from unittest.mock import patch
        for key in catalog.EFFORT_KEYS:
            data = {
                'plain': {'id': 'plain', 'params': []},
                'plain-off': {'id': 'plain', 'params': [{'id': key, 'value': 'none'}]},
                'plain-low': {'id': 'plain', 'params': [{'id': key, 'value': 'low'}]},
            }
            with self.subTest(key=key), patch.object(catalog, 'selections', return_value=data):
                self.assertTrue(catalog.capabilities('plain')['can_disable_reasoning'])
                resolved = catalog.resolve('plain', reasoning={'enabled': False})
                self.assertEqual(resolved['params'], [{'id': key, 'value': 'none'}])

    def test_thinking_off_preserves_a_published_effort_on_boolean_models(self):
        alias = next(k for k, row in catalog.selections().items()
                     if row['id'] == 'claude-opus-5' and
                     {p['id']: p['value'] for p in row['params']}.get('effort') == 'high' and
                     {p['id']: p['value'] for p in row['params']}.get('thinking') == 'true')
        before = {p['id']: p['value'] for p in catalog.resolve(alias)['params']}
        after = {p['id']: p['value'] for p in catalog.resolve(alias, reasoning={'enabled': False})['params']}
        self.assertEqual(after, {**before, 'thinking': 'false'})

    def test_effort_none_disables_even_without_enabled_flag(self):
        resolved = catalog.resolve('gpt-5.4', reasoning={'effort': 'none'})
        self.assertIn({'id': 'reasoning', 'value': 'none'}, resolved['params'])
        with self.assertRaisesRegex(ValueError, 'cannot disable'):
            catalog.resolve('gemini-4-argon', reasoning={'effort': 'none'})

    def test_unknown_effort_is_rejected_instead_of_becoming_extra_high(self):
        with self.assertRaisesRegex(ValueError, 'Unknown Cursor reasoning effort'):
            catalog.resolve('gpt-5.4', reasoning={'effort': 'nonsense'})

    def test_required_thinking_cannot_be_disabled(self):
        with self.assertRaisesRegex(ValueError, "cannot disable"):
            catalog.resolve("gemini-4-argon", reasoning={"enabled": False})

    def test_nonreasoning_model_ignores_inherited_effort(self):
        self.assertEqual(catalog.resolve("default", reasoning={"effort": "medium"})["params"], [])

    def test_fast_is_catalog_gated(self):
        self.assertIn({"id": "fast", "value": "true"}, catalog.resolve("composer-2.5", fast=True)["params"])
        self.assertNotIn({"id": "fast", "value": "true"}, catalog.resolve("composer-2.5", fast=False)["params"])
        with self.assertRaisesRegex(ValueError, "Fast"):
            catalog.resolve("gemini-4-argon", fast=True)

    def test_legacy_options_survive_and_native_choices_override_them(self):
        selections = catalog.selections()
        alias = next(k for k, v in selections.items() if v["id"] == "gpt-5.4" and
                     {p["id"]: p["value"] for p in v["params"]}.get("reasoning") == "high")
        old = catalog.resolve(alias)
        new = catalog.resolve(alias, reasoning={"effort": "low"}, fast=False)
        before = {p["id"]: p["value"] for p in old["params"]}
        after = {p["id"]: p["value"] for p in new["params"]}
        self.assertEqual(after["reasoning"], "low")
        self.assertEqual(after.get("context"), before.get("context"))
        self.assertNotEqual(after.get("fast"), "true")
        self.assertEqual(catalog.resolve(alias), old)

    def test_fast_on_exact_context_aliases_preserves_native_pins(self):
        checked = set()
        for alias, row in catalog.selections().items():
            params = {p["id"]: p["value"] for p in row["params"]}
            context = params.get("context")
            if row["id"] not in ("gpt-5.4", "gpt-5.5") or context not in ("1m", "272k"):
                continue
            checked.add((row["id"], context))
            with self.subTest(alias=alias):
                normal = catalog.resolve(alias, fast=False)
                self.assertEqual({p["id"]: p["value"] for p in normal["params"]},
                                 {**params, "fast": "false"})
                if context == "1m":
                    with self.assertRaisesRegex(ValueError, "Unsupported Cursor parameter combination"):
                        catalog.resolve(alias, fast=True)
                else:
                    fast = catalog.resolve(alias, reasoning={"effort": "xhigh"}, fast=True)
                    self.assertEqual({p["id"]: p["value"] for p in fast["params"]},
                                     {**params, "reasoning": "extra-high", "fast": "true"})
        self.assertEqual(checked, {(model, context) for model in ("gpt-5.4", "gpt-5.5")
                                   for context in ("1m", "272k")})

    def test_sparse_efforts_clamp_inherited_medium_to_published_level(self):
        for model, expected in (("glm-5.2", "high"), ("kimi-k3", "low")):
            with self.subTest(model=model):
                self.assertNotIn("medium", catalog.capabilities(model)["supported_efforts"])
                resolved = catalog.resolve(model, reasoning={"effort": "medium"})
                params = {p["id"]: p["value"] for p in resolved["params"]}
                effort_key = next(key for key in catalog.EFFORT_KEYS if key in params)
                self.assertEqual(params[effort_key], expected)

    def test_capabilities_and_advanced_options_are_catalog_derived(self):
        composer = catalog.capabilities("composer-2.5")
        self.assertTrue(composer["fast"])
        self.assertFalse(composer["reasoning"])
        gpt = catalog.capabilities("gpt-5.4")
        self.assertTrue(gpt["can_disable_reasoning"])
        self.assertIn("high", gpt["supported_efforts"])
        self.assertEqual([v["id"] for v in gpt["advanced_options"]], ["context"])
        for base in catalog.models():
            caps = catalog.capabilities(base)
            for saved in caps["model_selections"]:
                self.assertEqual(catalog.resolve(saved["model"])["id"], base)

    def test_no_unsupported_parameter_combination_is_sent(self):
        for base in catalog.models():
            caps = catalog.capabilities(base)
            for effort in caps["supported_efforts"]:
                catalog.resolve(base, reasoning={"enabled": True, "effort": effort}, fast=caps["fast"])


if __name__ == "__main__":
    unittest.main()

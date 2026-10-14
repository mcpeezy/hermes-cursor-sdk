# Cursor SDK provider for Hermes

**Experimental.** This plugin connects Hermes to the official `@cursor/sdk` Agent SDK. It does not use a private API, browser cookies, or an OpenAI-compatible proxy.

This is a subscription-oriented integration, not a guarantee of free or included inference. Cursor decides entitlement and billing. An authenticated account or a model listing does not prove that requests are included in your subscription. Confirm your account's allowance and spending settings before using it. The plugin cannot enforce an included-only spending cap.

## Requirements

- Hermes 0.22.0 or later, with the `ProviderProfile.create_client` plugin API.
- macOS or Linux, Node.js 22.13 or later, and Git on `PATH`.
- Credentials accepted by the official Cursor SDK, configured as `CURSOR_API_KEY` in the active Hermes profile. Use Hermes's credential setup. Do not paste a key into a command or this repository.

The SDK is pinned to `@cursor/sdk` 1.0.37. Windows is not supported by the current POSIX hook-command quoting.

## Install

Until the catalog entry is accepted, install from the repository:

```sh
hermes plugins install https://github.com/mcpeezy/hermes-cursor-sdk
```

Review the plugin's subprocess and file-write permissions when prompted. In the installed plugin directory, install the pinned Node dependency:

```sh
cd ~/.hermes/plugins/cursor-sdk
npm ci --ignore-scripts
```

For a named Hermes profile, use that profile's plugin directory instead. Configure `CURSOR_API_KEY` through Hermes, then select provider `cursor-sdk` and an exact model selection with `hermes model`. Installation does not change your default provider automatically.

The CLI reports one row per base model from a bundled development catalog snapshot. `model-selections.json` also contains exact parameterized selections. The snapshot is not a live account entitlement check and may become outdated. Fast and Advanced picker controls, along with thinking and effort settings, require Hermes to call the optional picker hooks. The plugin alone does not add those controls to older releases. Unsupported parameter combinations fail rather than silently switching models.

## How the transport works

Hermes's instructions are written to a project-scoped Cursor rule, and the existing conversation is sent as structured text. This is not a native system-role override and has not been proven equivalent to Hermes's normal prompt hierarchy.

Each request starts a local SDK agent in a separate plugin-owned Git workspace. Cursor's built-in tools are disabled except for the MCP callback transport. Project hooks deny native actions and permit only discovery and the offered Hermes callbacks. A callback returns a tool request to Hermes. It does not execute that tool. Hermes retains responsibility for approvals, tool execution, and returning the genuine result on the next request.

The worker is disposed after a response. Workspaces and SDK state currently remain under the installed plugin's `runtime/` directory, which can contain private conversation data. Keep that directory private and manage its retention deliberately. This repository's ignore rules keep it out of Git. They are not a retention policy.

Credentials are read through Hermes's profile-scoped secret accessor and passed only to the SDK subprocess. There is no direct credential-file read or automatic fallback to a different API provider. SDK failures are returned as fixed categories rather than raw messages that could disclose prompt or account data.

## Verification and limits

The package has offline Python transport/catalog tests and Node worker/hook tests. These tests use SDK fixtures and dummy credentials. They do not prove real inference, subscription billing, native-hook enforcement in every Cursor runtime, desktop activation, or acceptance by every listed model.

Other limits:

- Text-only messages. Image/vision handling is not implemented.
- SDK responses are buffered. OpenAI-shaped stream chunks are emitted after completion, not token by token.
- Cursor may require a separate data-retention acknowledgment for a model. The plugin does not accept it for you.
- Timeout/interrupt cleanup is tested offline. Live cancellation still needs qualification.
- The adapter uses Hermes's internal OpenAI-shape and effort helpers. Those imports need compatibility review when Hermes changes.

Do not use this experimental transport where strict prompt hierarchy or permission equivalence is a security requirement without independently qualifying the live SDK boundary.

## Run offline tests

Run from the plugin directory with a Python interpreter that has Hermes and its dependencies available:

```sh
python -m unittest discover -s tests -v
npm test
hermes plugins validate .
```

No inference request or real credential is needed for the test suites. No GitHub Actions workflow is included.

## References

- [Cursor SDK documentation](https://cursor.com/docs/sdk)
- [Hermes model-provider plugin API](https://hermes-agent.nousresearch.com/docs/developer-guide/model-provider-plugin)
- [Hermes plugin catalog](https://github.com/NousResearch/hermes-agent/tree/main/plugin-catalog)

License: MIT. Cursor SDK dependencies retain their own licenses and terms.

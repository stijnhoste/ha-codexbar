# CodexBar for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/stijnhoste/ha-codexbar?style=flat-square)](https://github.com/stijnhoste/ha-codexbar/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://www.hacs.xyz/docs/faq/custom_repositories/)

This is a Home Assistant custom integration for people who run
[CodexBar](https://github.com/steipete/CodexBar). It turns CodexBar's AI coding
quota data into sensors and immediate automation events, including usage,
remaining quota, reset times, credits, costs, provider status, quota warnings,
and quota resets.

It is a companion to CodexBar, not a standalone provider client. It does not
sign in to OpenAI, Anthropic, or other providers. Instead, it reads the
normalized snapshot from a running `codexbar serve` instance.

Because it consumes CodexBar's **normalized dashboard snapshot**, this
integration covers **every provider CodexBar supports** (Codex, Claude, Cursor,
Grok, OpenCode, DeepSeek, Antigravity, Gemini, Copilot, and the other 60+)
without any per-provider code.

## How it works

```text
CodexBar snapshot ──HTTP polling──► sensors and dashboards
CodexBar hooks ─────HTTP POST─────► events and automations
```

1. Run `codexbar serve` (see below) to expose its HTTP API.
2. Add the integration, entering the serve base URL and dashboard token.
3. Optional: send CodexBar hooks to the generated Home Assistant webhook URL.

The integration polls `GET /dashboard/v1/snapshot` every minute and, for
each enabled provider, creates:

| Entity | Description |
|---|---|
| `sensor.<provider>_<window>_used` | Percent used in a rate-limit window |
| `sensor.<provider>_<window>_remaining` | Percent remaining |
| `sensor.<provider>_<window>_resets_at` | Reset timestamp (`device_class: timestamp`) |
| `sensor.<provider>_<window>_resets_at_date` | The same instant as a fixed date string |
| `sensor.<provider>_plan` | Subscription plan label |
| `sensor.<provider>_credits` | Remaining credits/balance (when exposed) |
| `sensor.<provider>_cost_today` / `_cost_30d` | Local cost scan (USD, when exposed) |
| `sensor.<provider>_status` | Provider service status or error summary |

`<provider>` is the CodexBar provider id (`codex`, `claude`, `cursor`, …) and
`<window>` is the rate-limit window label (`session`, `weekly`, `tertiary`, or
provider-specific labels such as `codex_spark_weekly`). Entities appear and
disappear automatically as you enable/disable providers in CodexBar.

Every sensor also carries snapshot freshness and provider error attributes,
plus `account` and `source` when CodexBar exposes them. Sensors become
unavailable when the snapshot exceeds CodexBar's `staleAfterSeconds` window.

## Installing

### HACS custom repository

Add `https://github.com/stijnhoste/ha-codexbar` as a HACS custom repository
(category: Integration), then search for and install "CodexBar". It is not yet
part of the default HACS catalog.

### Manual

Copy `custom_components/codexbar/` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

### 1. Run `codexbar serve`

On the machine running CodexBar (macOS 14+, or Linux via the bundled CLI):

```bash
# generate a token
export CODEXBAR_DASHBOARD_TOKEN=$(openssl rand -hex 24)

# loopback only (safest — use a reverse proxy to expose it remotely)
codexbar serve --port 8080

# or on a trusted LAN, accepting cleartext bearer transport
codexbar serve --host 0.0.0.0 --port 8080 --allow-plain-http --identity redacted
```

A macOS LaunchAgent example (`~/Library/LaunchAgents/com.codexbar.serve.plist`)
is provided in the `examples/` directory.

### 2. Add the integration

Settings → Devices & Services → Add Integration → CodexBar, then enter
the base URL (e.g. `http://127.0.0.1:8080` or `http://my-mac.tailnet.ts.net:8080`)
and the dashboard token. Home Assistant shows the hook URL after setup. You can
view it again with **Configure** on the CodexBar integration.

> The token is stored in the config entry and sent in the `Authorization` header.
> `codexbar serve` is plain HTTP; if it is bound beyond loopback, the token and
> account data transit the network in cleartext — put it behind a TLS-terminating
> reverse proxy or keep it on a trusted segment (see CodexBar's
> [`dashboard-api.md`](https://github.com/steipete/CodexBar/blob/main/docs/dashboard-api.md)).

## Hook automations

CodexBar hooks are local executable rules. Point a rule at Home Assistant by
using `curl` as the executable and the generated hook URL as its last argument.
For example, this rule sends every Codex quota reset to Home Assistant:

```json
{
  "hooks": {
    "enabled": true,
    "events": [
      {
        "id": "home-assistant-quota-reset",
        "enabled": true,
        "event": "quota_reset",
        "provider": "codex",
        "executable": "/usr/bin/curl",
        "arguments": [
          "--fail-with-body",
          "--silent",
          "--show-error",
          "--header",
          "Content-Type: application/json",
          "--data-binary",
          "@-",
          "YOUR_HOME_ASSISTANT_HOOK_URL"
        ],
        "timeoutSeconds": 10
      }
    ]
  }
}
```

Configure this in CodexBar **Settings → Hooks** or in its local
`config.json`, then validate and test it. See CodexBar's
[`configuration.md`](https://github.com/steipete/CodexBar/blob/main/docs/configuration.md#external-event-hooks)
for the complete hook contract.

```bash
codexbar config validate
codexbar hooks test quota_reset --provider codex
```

The macOS app evaluates hooks during its normal refreshes. For a headless CLI
installation, keep `codexbar hooks watch` running. The watcher checks every five
minutes by default and accepts a minimum interval of one minute.

Home Assistant exposes each accepted hook in two ways:

- `event.codexbar_hook`, an event entity with the most recent CodexBar event.
- The `codexbar_hook` event on the Home Assistant event bus.

Use the event bus for precise automation filters. This example flashes a light
when the Codex session or weekly quota resets:

```yaml
automation:
  - alias: Flash a light when Codex quota resets
    trigger:
      - platform: event
        event_type: codexbar_hook
        event_data:
          event: quota_reset
          provider: codex
    action:
      - service: light.turn_on
        target:
          entity_id: light.office
      - delay: "00:00:02"
      - service: light.turn_off
        target:
          entity_id: light.office
```

Supported hook types are `quota_low`, `quota_reached`, `quota_reset`,
`provider_unavailable`, `provider_recovered`, and `refresh_failed`. Event data
can also include `account`, `window`, `usagePercent`, `used`, `limit`, `resetAt`,
and `status`. The hook handler accepts POST requests only, limits payloads to
4 KiB, and ignores unknown optional fields as required by CodexBar's v1 hook
contract.

Treat the generated hook URL as a password. Anyone with the URL can send an
automation event to Home Assistant.

### Upgrading from 1.0

Remove and add the integration again once after upgrading. Version 1.0 entries
do not have the random hook URL required by version 1.1, and this integration
does not keep a legacy setup path or migration.

## Tips

- Percent values are rounded to whole numbers for clean gauges; cost is rounded
  to cents. Adjust `PERCENT_ROUND` / `COST_ROUND` in `const.py` if you prefer
  more precision.
- Disable providers you don't use in CodexBar's Settings → Providers to keep the
  sensor list tidy.

## License

MIT.

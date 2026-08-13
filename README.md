# CodexBar for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/stijnhoste/ha-codexbar?style=flat-square)](https://github.com/stijnhoste/ha-codexbar/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=flat-square)](https://github.com/hacs/integration)

This is a Home Assistant custom integration for people who run
[CodexBar](https://github.com/steipete/CodexBar). It turns CodexBar's AI coding
quota data into sensors for dashboards and automations, including usage,
remaining quota, reset times, credits, costs, and provider status.

It is a companion to CodexBar, not a standalone provider client. It does not
sign in to OpenAI, Anthropic, or other providers. Instead, it reads the
normalized snapshot from a running `codexbar serve` instance.

Because it consumes CodexBar's **normalized dashboard snapshot**, this
integration covers **every provider CodexBar supports** (Codex, Claude, Cursor,
Grok, OpenCode, DeepSeek, Antigravity, Gemini, Copilot, and the other 60+)
without any per-provider code.

## How it works

```
CodexBar.app (macOS, fetches usage) ──► codexbar serve ──► this integration ──► sensors
```

1. Run `codexbar serve` (see below) to expose its HTTP API.
2. Add the integration, entering the serve base URL and dashboard token.

The integration polls `GET /dashboard/v1/snapshot` every 10 minutes and, for
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
| `sensor.<provider>_status` | Provider service status |

`<provider>` is the CodexBar provider id (`codex`, `claude`, `cursor`, …) and
`<window>` is the rate-limit window label (`session`, `weekly`, `tertiary`, or
provider-specific labels such as `codex_spark_weekly`). Entities appear and
disappear automatically as you enable/disable providers in CodexBar.

Every sensor also carries `account` and `source` attributes.

## Installing

### HACS

Search for "CodexBar" in HACS (Integrations), or add this repository as a
custom repository (category: Integration) in HACS, then install "CodexBar".

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

**UI:** Settings → Devices & Services → Add Integration → CodexBar, then enter
the base URL (e.g. `http://127.0.0.1:8080` or `http://my-mac.tailnet.ts.net:8080`)
and the dashboard token.

**YAML** (alternative):

```yaml
codexbar:
  host: http://127.0.0.1:8080
  token: !secret codexbar_token
```

> The token is stored in the config entry and sent in the `Authorization` header.
> `codexbar serve` is plain HTTP; if it is bound beyond loopback, the token and
> account data transit the network in cleartext — put it behind a TLS-terminating
> reverse proxy or keep it on a trusted segment (see CodexBar's
> [`dashboard-api.md`](https://github.com/steipete/CodexBar/blob/main/docs/dashboard-api.md)).

## Tips

- Percent values are rounded to whole numbers for clean gauges; cost is rounded
  to cents. Adjust `PERCENT_ROUND` / `COST_ROUND` in `const.py` if you prefer
  more precision.
- Disable providers you don't use in CodexBar's Settings → Providers to keep the
  sensor list tidy.

## License

MIT.

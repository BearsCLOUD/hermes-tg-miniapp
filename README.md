# Hermes Telegram Mini App — files & Markdown

A [Telegram Mini App](https://core.telegram.org/bots/webapps) for Hermes: a
file browser and a Markdown editor that open inside Telegram's WebView, right
from the bot's chat.

## What it does

- The **chat menu button** next to the composer opens the Mini App in one tap.
  There is no bot command: nothing has to be typed, and nothing competes with
  the built-in command handling.
- Inside the app: browse the managed file tree, open `.md` files, edit them and
  save back.

## Auth model

Telegram's signed `initData` **is** the credential. There is no login, no
session and no second token:

1. Telegram delivers `initData` in the URL fragment (`#tgWebAppData=…`).
2. The page sends it as `Authorization: Bearer <initData>`.
3. The plugin's dashboard auth provider verifies Telegram's HMAC-SHA256
   signature against the bot token; the dashboard's token-auth gate rejects
   anything else before the route runs.

The verification follows Telegram's own reference implementation
(`@telegram-apps/init-data-node`):

```
secret_key     = HMAC_SHA256(key="WebAppData", message=<bot_token>)
data_check_str = sorted "key=value" pairs joined by "\n", excluding `hash`
hash           = hex(HMAC_SHA256(data_check_str, secret_key))
```

Two details are easy to get wrong, and both are covered by the test suite:

- the HMAC **key** is the constant `"WebAppData"` and the **message** is the
  bot token — not the other way round;
- the third-party `signature` field is **part of** the data check string;
  only `hash` is excluded.

File access is delegated to Hermes' managed-files policy, so the same root
lock and the same credential denylist that guard the dashboard apply here.
This plugin never resolves a path on its own.

## Install

```bash
hermes plugins install BearsCLOUD/hermes-tg-miniapp
hermes plugins enable telegram-miniapp
```

The bot token is required (`TELEGRAM_BOT_TOKEN`). For the page URL,
`HERMES_DASHBOARD_PUBLIC_URL` must be the public HTTPS address of the
dashboard — Telegram will not load a Mini App over plain HTTP.

### The button

Telegram has no plugin hook for the chat menu button; it is a Bot API call.
Install it once with the bundled script:

```bash
python set_menu_button.py                 # every chat the bot is used in
python set_menu_button.py --chat-id 1234  # one chat only
python set_menu_button.py --clear         # back to the command list
```

The button needs an HTTPS URL, so `dashboard.public_url` must be set first:

```bash
hermes config set dashboard.public_url https://your-host
```

## Layout

| Path | Purpose |
| --- | --- |
| `telegram_bridge.py` | registers the auth provider and the token routes |
| `telegram_auth.py` | Telegram `initData` signature validation |
| `auth_provider.py` | the dashboard auth provider that verifies `initData` |
| `api.py` | the file routes (list / read / write) |
| `dashboard/index.html` | the Mini App page: file tree + Markdown editor |
| `dashboard/plugin_api.py` | entry point the dashboard's plugin loader imports |
| `set_menu_button.py` | installs the chat menu button that opens the app |

The official Telegram Web App SDK is served from this origin
(`dashboard/telegram-web-app.js`) so the app still works where `telegram.org`
is unreachable; the CDN copy is only a fallback. `initData` is parsed from the
URL fragment independently of the SDK, so the page works even when the SDK
cannot be fetched.

## Verifying

The `verify_*.py` scripts are real checks, not synthetic ones:

```bash
# auth: signature, tampering, expiry, wrong token, legacy scheme
python verify.py

# the API routes and the managed-files policy
python verify_routes.py

# a real browser, emulating Telegram's WebView (signed initData in the fragment)
python verify_browser.py

# the editor end to end: open a .md, edit it, save, preview
python verify_editor.py

# the layout on a phone-sized viewport
python verify_layout.py

# against Telegram's own reference library, both directions
python verify_against_official.py
```

The browser checks need `playwright` and a Chromium build; point
`CHROMIUM_PATH` at the binary when it is not in the default place.
`verify_against_official.py` needs `node` and the npm package — point
`TGA_NPM_DIR` at a directory that contains
`@telegram-apps/init-data-node`.

`verify_against_official.py` is the one that matters most: it signs a payload
with `@telegram-apps/init-data-node` and requires the Python verifier to accept
it, then signs one with the Python implementation and requires Telegram's
library to accept it. A self-consistent implementation cannot pass it.

`verify_editor.py` is what a phone screenshot cannot show: it opens a Markdown
file, types into the textarea, saves, and reads the file back from disk.

## Licence

MIT.

# رویین / اتاق پایش

RTL operational evidence viewer. Priority: recorded mode, freshness, unavailable
exchange account, then research and decision inspection. No trade/worker controls.
All design tokens are in static/style.css :root; no CDN, remote font or media.
2026-10-23 user-requested refresh: self-host Vazirmatn for Persian and Inter for
Latin/digits; variable WOFF2 files, upstream commit URLs, hashes and OFL licenses
are in static/fonts/. Latin unicode ranges select Inter without replacing Persian
glyphs. Font requests stay same-origin under the existing CSP.

| Token | Value / role |
|---|---|
| bg / surface / raised | #10191f / #17232b / #1e2e38 |
| text / muted / line | #e7edf1 / #b0bfc9 / #344955 |
| accent / accent-dim | #8bd7c6 / #20443f, navigation and selected values |
| warning / warning-bg | #f0ce91 / #332e24, missing or stale evidence |
| danger / danger-bg | #f5afa7 / #3d2a2b, disconnected API |
| chart secondary | #abc8f4; other series use accent, warning, danger |
| s1…s7 | 4, 8, 12, 16, 24, 32, 48 px |
| radius / shadow | 12px / 0 12px 40px #0004; shadow only on dialog |
| typography | local Inter + Vazirmatn; 14px body, 36px main title, 20px sections |

Semantic status always has text, never color alone. Dark financial workspace,
restrained borders, no gradients, no promotional numbers. Tables retain original
decimal strings and units; summary cards shorten decimal text to two places with
an approximation sign when digits are omitted, and title/accessible name retains
the exact value. Tables/API remain exact. SVG numeric conversion is display-only. Metadata and
identifiers have LTR direction. Times can switch Asia/Tehran / UTC; provenance
shows both and time title supplies both. Mobile is the base, with min-width
enhancements at 680px and 1100px. No one-sided accent border on status cards.

Loading: explicit receiving text. EMPTY: bordered empty state. UNAVAILABLE: missing
source with explanation. INVALID: evidence error, previous selection cleared.
STALE: amber saved observation with age. OFFLINE: red connection notice and last
saved values, never implied current. Partial JSONL produces a visible warning.

Keyboard: skip link, native selects/buttons, visible 3px accent focus, focusable
horizontal tables, native modal with Escape and focus return. Reduced motion
disables smooth scrolling. Automatic refresh yields while controls are focused
or a detail dialog is open; explicit refresh preserves selection, filters and
open detail. Pause refresh pauses presentation only. Auto-refresh interval 15s,
request deadline 6s, no retry. Financial values never calculated with JS floats.

Native selects are deliberately retained from the project contract: preserving
platform keyboard/typeahead behavior avoids introducing a new trading-monitor
interaction during the deadline. This overrides the generic design kit's custom
listbox preference. There is no new widget or frontend dependency.

The paired-test strip distinguishes its coordinator heartbeat from the account
and engine snapshot. Separate child manifests are not an atomic checkpoint;
their curves cannot be overlaid as synchronized observations. Valid AI WAIT,
valid AI ENTER and host fallback are separate diagnostic counts. During a new
row request, stale rows disappear and pagination is disabled until completion.

Screenshots and browser observations live in ignored .local/dashboard. Future
root DESIGN merge belongs to the integrator, not this ownership scope.

# رویین / اتاق پایش

RTL operational evidence viewer. Priority: recorded mode, freshness, unavailable
exchange account, then research and decision inspection. No trade/worker controls.
All design tokens are in static/style.css :root; no CDN, remote font or media.

| Token | Value / role |
|---|---|
| bg / surface / raised | #0d141a / #141e26 / #1a2731 |
| text / muted / line | #e5edf2 / #a4b6c3 / #30414e |
| accent / accent-dim | #7ccec0 / #173b37, navigation and selected values |
| warning / warning-bg | #edc47b / #332b1d, missing or stale evidence |
| danger / danger-bg | #f2a39b / #392528, disconnected API |
| chart secondary | #96baf4; other series use accent, warning, danger |
| s1…s7 | 4, 8, 12, 16, 24, 32, 48 px |
| radius / shadow | 12px / 0 12px 40px #0004; shadow only on dialog |
| typography | local Tahoma, Segoe UI, Arial, sans-serif; no font download |

Semantic status always has text, never color alone. Dark financial workspace,
restrained borders, no gradients, no promotional numbers. Tables retain original
decimal strings and units; summary cards shorten decimal text to two places with
an approximation sign when digits are omitted, and title/accessible name retains
the exact value. Tables/API remain exact. SVG numeric conversion is display-only. Metadata and
identifiers have LTR direction. Times can switch Asia/Tehran / UTC; provenance
shows both and time title supplies both. Responsive breakpoints 1100px and 680px.

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

Screenshots and browser observations live in ignored .local/dashboard. Future
root DESIGN merge belongs to the integrator, not this ownership scope.

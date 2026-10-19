# AutoBH icon

Custom geometric A with a check as its rising crossbar. The A identifies AutoBH; the check refers to its attendance/record workflow, with the ascending stroke suggesting a wing.

- Deep teal surface: `#16656F` → `#0A3037`, matching the application's teal palette.
- Off-white symbol: `#F4FBF8`.
- Mint check: `#84E5CA`.
- 1024-unit artboard; 832-unit tile with 96-unit transparent margins and 192-unit corners.
- No small text; bold rounded stems stay legible at 16–32 px.

`Icon.swift` renders exact pixel-size PNGs for the macOS iconset; `iconutil` assembles the ICNS. `AutoBH.png` is the 1024 px export, `AutoBH-preview.png` is the 256 px preview. The editable browser mark is `gui/public/autobh.svg`, sharing the native path geometry.

Regenerate exports after changing geometry; inspect both the 512 px export and the smallest iconset sizes. The native application explicitly loads its bundled ICNS on launch so the running Dock uses the current artwork.

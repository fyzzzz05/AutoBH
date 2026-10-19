# AutoBH teal redesign — design QA

final result: passed

## Source, implementation and normalization

- Visual truth: `/Users/yuzhef50/code/autobh/gui/qa/teal-redesign/reference-source.png`, copied from the user-provided `codex-clipboard-7aa5f3f3-cc7c-47b9-bd9a-0cf00e8f6419.png`.
- Original source: 2316 × 1684 pixels, including design-editor chrome. App-only crop: `(117,146)–(2240,1538)`, 2123 × 1392 pixels. Chrome is deliberately excluded.
- Normalized reference: `gui/qa/teal-redesign/reference-normalized.png`, 1440 × 945 pixels.
- Implementation: `http://127.0.0.1:8765/`, screenshot `gui/qa/teal-redesign/desktop-live.png`, 1440 × 945 pixels, CSS viewport 1440 × 945, effective capture density 1 image pixel per CSS pixel. The screenshot API encodes compressed raster captures; minor antialiasing/color differences are capture-dependent.
- Same comparison state: first person 邬慧彤 / 24261009, no class/Boya binding, TD 19 semester total and 3/3 today, all three real workers running. Real page was inspected read-only. Mutating tests used the isolated demo at port 8877.
- Full-view side-by-side comparison: `gui/qa/teal-redesign/comparison-final.png`.
- Focused side-by-side comparison: `gui/qa/teal-redesign/comparison-features.png`, matching 1020 × 585 regions from both artifacts, covering headings, buttons, badges, switches, TD digits and round indicators. Both comparisons were opened and visually inspected together.

## Findings and comparison history

1. Initial comparison (`comparison-initial.png` / `desktop-initial.png`): **blocked**.
   - [P1] Shared legacy `.button` styles removed the outlined feature actions and edit button. Fixed the cascade by applying common button rules before the new workspace styles; teal outlines and compact radii now render.
   - [P2] Sidebar rows and section spacing were too loose. Reduced person-row padding and the gap before 自动执行. Desktop sidebar is now 332.6 px / 23.1%, header 72 px; main content begins at x≈396 and TD card at x≈453, matching the normalized reference.
   - [P2] Initial colors were approximate. Sampled the source and set exact CSS tokens: header/card `#0d3a3f`, selected/action teal `#0a6d74`, sidebar `#e3eae6`, canvas `#f3f5f3`. Verified computed CSS colors in browser.
2. Refined comparison (`desktop-refined.png`): **blocked** pending progress-detail refinement.
   - [P2] TD count proportions and filled round markers differed. Used a compact bold Arial numeral treatment, adjusted secondary copy weights, and accounted for the icon library's internal circle padding with 23 px icon boxes and 2 px gaps.
3. Final comparison (`comparison-final.png`, `comparison-features.png`): **passed**.
   - No actionable P0/P1/P2 issues remain. The main composition, hierarchy, outlined actions, selected row, status pills, feature dividers and prominent TD card follow the source.

## Required fidelity surfaces

- **Fonts / typography:** native macOS/PingFang stack; 52 px, weight 750 person title; compact 20 px account ID; 21 px bold feature titles; 60 px bold TD numerals; smaller secondary update text. Checked wrapping and hierarchy in the focused comparison. The reference supplies no font metadata, so tiny glyph/stroke differences remain P3.
- **Spacing / layout rhythm:** matched the 72 px top bar, 23.1% sidebar, inset main panel, ID/group row, generous person header, thin dividers, 108 px TD card and compact outlined controls. The complete live roster renders all 11 people; the mock displays only 6 example rows despite its count of 11. This is an intentional data difference, rather than truncating real people.
- **Colors / tokens:** exact sampled teal/sage/canvas colors implemented and verified through computed styles. State information also has text labels; the TD dots have the numeric 3/3 equivalent. No gradients or decorative imagery introduced.
- **Images / assets / icons:** target contains editable UI text and standard icons, with no custom raster assets to generate. Reused the existing Phosphor library for graduation, barbell, book, search, plus, info and filled circle indicators. The barbell silhouette is the closest existing library match, an accepted P3 variation. No custom icon art or embedded screenshot used as UI.
- **Copy / content:** preserved functional Chinese labels, real counts and timestamps. Added functioning 全部 / 运行中 / 未绑定 filters. Running requires an enabled binding and a running, non-stopping worker. Unbound means at least one of the three features lacks an account. Deletion remains available inside 编辑资料 with its original confirmation.

## Interactions, responsiveness and accessibility

- Demo: selected users; combined 未绑定 with name search; checked empty search and reset; paused TD while using 运行中 and verified that person left the filtered list; restored the switch; edited and restored a demo name; opened TD details; reached and cancelled the delete confirmation. Existing binding/service/Boya flows retain their real APIs.
- Independent desktop scrolling: list scrollTop 131 while main remained 0; then main scrollTop 41.5 while list remained 131; document scrollTop stayed 0.
- Mobile 390 × 844: document scrollWidth 390; list becomes a horizontally scrolling strip; detail remains independently scrollable. After main scrollTop 384.5, document scrollTop stayed 0, header bottom and sidebar top both remained at y=100. Evidence: `mobile-top.png`, `mobile-progress.png`.
- Checked disabled unbound switches, visible focus styling, labelled controls, pressed filter states, status text, loading/empty states and reduced-motion rules.
- Both demo and real-page console checks returned no relevant warnings/errors and no framework overlay.
- 95 Python tests passed with isolated homes and blocked school-network access. 9 frontend tests passed, including running/unbound/search filter semantics. Production frontend build passed.
- macOS 0.1.2 app/DMG rebuilt; self-contained engine, native module imports, signatures, GUI lifecycle and independent worker checks passed. Local default Python installation updated to 0.1.2.

## Implementation checklist

- [x] Apply the reference to the existing product, preserving original backend functionality.
- [x] Implement functional filters and missing/paused/running/count states.
- [x] Compare full view and focused regions; resolve P1/P2 findings.
- [x] Verify desktop, mobile, interactions and independent scrolling.
- [x] Update packaged frontend and native installer; keep real local preview available.

## Follow-up polish

- P3 only: exact font and icon parity would require the reference's original font/icon metadata. No further visual iteration is required for this handoff.

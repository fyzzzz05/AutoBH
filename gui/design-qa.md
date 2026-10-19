# AutoBH selected-dashboard design QA

Source visual truth: `qa/indigo-reference/source-normalized.png`, cropped from the user's supplied screenshot to the application content. Original screenshot: 3024×1964; app crop: 1848×1128; normalized reference: 1206×736. CSS comparison viewport: 1206×736, device scale 1. Browser full-page capture is required because viewport screenshots in the embedded browser are scaled to its visible panel.

State: 11 example people, selected first person with TD bound/running, 22 semester runs, 0/3 today, other three bindings absent. Aggregates: 1 running / 0 paused / 35 unbound. All data in an isolated demo process.

## Comparison history — first pass

Evidence: `qa/indigo-reference/comparison-normalized-first.png`, source and implementation in one combined input; `implementation-full.png` is the browser-rendered source for this pass.

- [P2] Unbound card action row sits too low. Source first-row binding action starts about y276; implementation starts about y305. Remove the flex-fill centering from `.card-empty`, retain a fixed 20px gap after the card header.
- [P2] People rows are too tall. Padding plus two text lines exceeds the 56px row target, cumulatively pushing the ninth name below its reference position. Reduce item padding to 8px and list gap to 2px.
- [P2] Bound-card detail target needs a real full-size button bounding box for pointer and keyboard use. Make `.card-detail-link` the absolute full-card target with the toggle above it, rather than relying on only a pseudo-element.

Five fidelity surfaces checked: system/PingFang typography and hierarchy; 76px header/282px sidebar/32px content inset/16px grid gaps; white and pale-gray surfaces; editable text monograms (literal UI labels from the source, not substituted artwork); app copy and record timestamps. Accent follows the user's explicit #4455D9, taking precedence over sampled screenshot colors. Small search/add utility buttons and the demo-data footer intentionally preserve existing functionality and identify the preview.

## Comparison history — second pass

Evidence: `qa/indigo-reference/comparison-second.png` and `comparison-td-detail.png`; each combines the source and implementation in one image and was visually inspected. Final browser capture: `qa/indigo-reference/final-dashboard.png`.

All three first-pass P2 findings are resolved: binding actions align with the source row, people rows keep their 56px target without cumulative drift, and detail buttons have a full-card bounding box with a visible keyboard focus outline. Primary color is exactly CSS `#4455D9`. Cards measure x314/y192 and x752/y192 at 1206×736, with a 16px gutter; the second row begins y417. One-pixel reference differences caused by normalization are immaterial. Typography, layout, surfaces, monograms and copy all pass the five-surface comparison. No unresolved P0/P1/P2 findings.

## Responsive and interaction verification

Browser checked at 1206×736, 1180×820, 900×600, 560×600, 390×844 and 390×600. No document overflow. Main area has `overflow: clip`, equal scroll/client heights, and all four cards fit. People list scrolls independently with a hidden scrollbar, becoming horizontal on narrow screens. Mobile evidence: `qa/indigo-reference/mobile-390x600.png`; four-bound-card evidence: `all-bound-mobile.png`.

Isolated demo interaction checks passed: running filter; ID search; selecting a person; closing search; TD pause/re-enable with matching aggregate counts and status; TD detail popup; class binding form; profile edit; add-person form; four-service management dialog. Bound all four demo features and verified compact layout, then opened Boya progress with categories and enrollment status. Recreated the isolated demo process afterwards to restore the selected reference state. No real workers, credentials or school requests were used. Existing modal styling and workflows are retained, outside the selected dashboard reference.

Browser console: no errors or warnings. Build succeeded. Unit tests: 16/16. Static-serving/package checks: 4/4. Preview remains at http://127.0.0.1:54010/; temporary viewport override reset; preview tab retained as a deliverable.

final result: passed

## Follow-up — per-person indicator semantics

User requested lights for unselected people as well. The original preview gray lights came from enabled bindings with stopped shared workers. Sidebar indicators now reflect each person’s enabled/paused/unbound configuration, independently of selection and worker status; card labels and global running counts retain actual worker status. This is an explicit user-requested deviation from the selected reference state. Browser verified unselected enabled rows green, paused row amber after switching away, and restored demo configuration. Evidence: `qa/indigo-reference/person-status-lights.png`. Build and 17 unit tests passed; console clean. Overall design QA remains passed.

## Local App installation — 2026-10-17

At the user’s request, packaged the frontend into `src/autobh/web`, staged a copy of the installed App with only its web assets replaced, re-signed locally, and installed it at `/Applications/AutoBH.app`. Existing engine, updater, icon, version and local data directories are retained. Rollback copy: `/Users/yuzhef50/code/autobh/build/macos/local-ui-update-20261017-123708/backup/AutoBH.app`. Signature and packaged CLI/GUI lifecycle checks passed in isolated data directories. Reopened the real App and verified the 2×2 dashboard and per-person enabled/paused indicators using its actual local state, without changing accounts or starting workers. Screenshot: `qa/indigo-reference/installed-app.png`. No GitHub release or DMG was published.

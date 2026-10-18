# SynthAI 后台统一重构 QA

## Current refinement — 2026-10-18

User requested rounded corners and a more modern, minimal appearance. This refinement supersedes the earlier square-control visual target below. Shared admin surfaces now use 14px corners, controls 8px, compact controls 6px, and dialogs 18px. Softer borders, a quiet surface shadow and lighter heading weights retain the existing compact layout.

Validation: production build and `git diff --check` passed. All 16 routes were checked at the normal browser width and 390px mobile width without document overflow. Overview, articles, model forms and priorities were visually checked at 1440×1000; mobile overview/forms/priorities and dark forms/priorities were also inspected. Overview table columns were constrained to preserve source and date visibility at medium widths. No configuration was saved or data changed during these checks.

Current evidence: `output/design/admin-rounded/rounded-board.png`, `mobile-board.png`, `priorities-dark.png`, `forms-dark.png`, and `overview-final.png`. Browser restored to light theme and the overview route. The existing build warning about chunks over 500kB remains.

## Scope and visual truth

Generated with the explicitly requested yunwu-t2i skill, model gpt-image-2.5-sunburst, high quality, no soft-image suffix, 1536×1024 PNG.

Source visual truth paths:
- `output/design/admin-suite/overview-reference.png`
- `output/design/admin-suite/content-reference.png`
- `output/design/admin-suite/forms-reference.png`
- `output/design/admin-suite/operations-reference.png`

Implementation evidence: `output/design/admin-suite/after/` contains all 16 admin routes. Full-view source/implementation pairs are `comparison-overview.png`, `comparison-content.png`, `comparison-forms.png`, and `comparison-operations.png` in the same directory's parent. Focused typography and controls: `focused-comparison.png`. Mobile evidence: `mobile/`; dark evidence: `dark/` and `dark-review.png`.

## Comparison conditions

- Desktop source and implementation: 1536×1024 pixels, browser 1536×1024 CSS px, density 1×. Pair images normalize both to 768×512 without cropping.
- Focused comparisons use corresponding toolbar/table rows and form rows, proportionally fitted into 768px-wide columns.
- Mobile: 390×844 CSS px. Each of 16 routes has document width 390px, no page overflow.
- Normal browser viewport restored to 1093×827; final screenshot `overview-preview.png`.
- State: light theme, actual saved settings, real database records. Generated names, metrics and fields are not copied into production. Dark theme verified on overview, articles, tasks, and connection forms; light preference restored.

## Findings and iteration history

- [P2, resolved] Initial desktop overview clipped the fifth recent-article row at y1040. Reduced overview header/row padding; the revised panels end at y998, inside the 1024px comparison viewport. Verified in the recaptured overview screenshot and DOM measurements.
- [P2, resolved] Article search with zero matches claimed the library was empty, and filtered totals were labeled as whole-library totals. Reproduced with a unique query, then fixed both desktop and mobile empty states and the summary copy. Browser now shows 筛选出 0 篇 and a filter-specific empty message.
- [P2, resolved] Source dropdowns omitted newly supported platforms. Both viewports now share SOURCE_META. CSDN selection was tested against the real API and returned exactly one CSDN article; filter reset afterward.
- [P2, resolved] Hidden unvisited settings panels mounted and ran their loading effects. A fresh priority page initially contained the unopened account and network forms. Sections now mount on first visit and stay mounted afterward. Browser checks confirm unopened account/network forms absent; a temporary unsaved proxy draft survives switching sections and was restored without saving.
- [P2, resolved] Existing confirmation dialog used front-site controls and initial focus remained outside the dialog. Admin-specific controls and danger palette now match the console; Cancel receives initial focus. Open/cancel tested, no deletion performed.

## Five fidelity surfaces

1. Typography: retained the product system sans-serif and original brand mark; 27–30px headings, 13–14px desktop table/body text, readable 16px mobile fields. Source illustrations use larger lettering in places; production keeps the established compact density.
2. Spacing/layout: common 240px accordion sidebar, ancestor-only top bar, metric strip, ruled tables, aligned form labels and consistent footer actions. One visible h1 on every route. Form labels collapse above fields on mobile.
3. Colors/tokens: near-white canvas, white surfaces, subtle separators, evergreen accent; equivalent dark tokens. Status colors remain semantic. The current refinement adds moderate rounded corners and subtle surface shadows.
4. Assets: no new illustrative assets are needed inside the admin app. Existing logo and Lucide icons retained. Generated images are design references, not rasterized controls or placeholder UI.
5. Copy/content: real platform labels, settings, metrics, API data and operations retained. Removed implementation-specific shortcut environment variable text from the user flow. No unsupported mock fields or fake connection status added.

## Intentional product constraints

- Reference mock fields such as service type, response latency and invented account menu are omitted because the existing app does not provide them.
- Existing model/transcription/generation sections remain distinct navigation destinations; no duplicate horizontal tabs are added.
- Source charts and task counts show actual database values, which differ from the generated samples. Historical failed tasks remain historical data.
- TikHub account usage returned HTTP 429 during repeated checks; the interface exposed the upstream warning. Lazy mounting reduces unnecessary account requests but is not a claim to change the upstream limit.

## Browser interaction checks

- All 16 routes visited on desktop and mobile; widths and headings recorded in `route-checks.json`.
- Mobile drawer opens, navigates, and closes on route change.
- Search empty state, CSDN filter, article inspector open/close, interface catalog search and parameter form selection verified.
- Settings first-visit mount and unsaved draft retention verified.
- Confirmation open/cancel and initial Cancel focus verified; no destructive test or credential update.
- Console error log empty after final checks.

## Follow-up polish

[P3] Generated font shapes and some layout proportions differ slightly from system fonts and actual data density. No blocking visual issue or clipped persistent control remains.

final result: passed

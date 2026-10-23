# Workspace UX redesign — 23 October 2026

Scope: authenticated frontend workspace only. Landing and opening animation are excluded.

## Evidence and research approach

The changes below are based on reading the current Next.js components, reviewing actual Chrome screenshots, and checking release workflows. This is an implementation audit, not a controlled user study.

- Nielsen Norman Group: [Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) — keep frequent tasks visible; move secondary tools behind explicit disclosure.
- Nielsen Norman Group: [The 3 C's of informational microcopy](https://www.nngroup.com/articles/3-cs-microcopy/) — clear, concise, and distinctive labels.
- W3C: [WCAG contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum) — at least 4.5:1 for ordinary text.
- Baymard: [Applied filters overview](https://baymard.com/research-articles/how-to-design-applied-filters) — show which filters shape results and preserve context.

## Shipped improvements

| Area | Before | Updated behavior |
| --- | --- | --- |
| Applications | Selecting status could immediately write to storage before entering a note | Select a stage, optionally write a transition note, then explicitly **Save status** |
| Application filters | Moving a tracked application to a different status could leave it under the old filter until refresh | Updated record is removed from the current filtered view when its stage no longer matches |
| Jobs | Five equal-weight analysis actions competed for attention | Two primary comparisons; three specialized tools under a labeled disclosure |
| Role analyses | Each view had isolated navigation and repeated evidence text | Shared navigation preserves the selected resume; per-requirement sources and limitations are available on demand |
| Resumes | "Resume family", raw parser statuses, and all management actions at once | Plain-language collection/version labels; primary actions visible; advanced operations under **More options** |
| Projects | Portfolio URLs were shown only as noninteractive text | Valid HTTPS/HTTP project and repository links are actionable |
| Skills and candidate | Explanations repeated the heading or exposed domain-specific implementation distinctions | Clear action-based descriptions, with supporting details retained where necessary |
| Contrast | Some small labels were under the WCAG AA ordinary-text reference contrast | Increased selected metadata color contrast and minimum text sizing |
| Dashboard | Repeated "application tracker" link and redundant navigation | Emphasis on active applications and next useful action |

## Automated verification

The repository's engineering workflow checks TypeScript, ESLint, Vitest, Next.js build, Python/backend/migrations, and full-stack browser auth. A separate Chrome workflow checks 14 frontend routes at 1440 px and 390 px, and exercises job selection, deeper analysis navigation, resume controls, candidate search, application status-saving, and persistence after reload. See the live Actions results rather than treating this document as proof of passing checks.

## Remaining verification before a defensible 90+ score

- Conduct representative usability tasks with at least several students unfamiliar with the app.
- Measure actual LCP, INP, and CLS on real devices; Vercel Web Analytics is currently not enabled.
- Run a full WCAG accessibility audit, including keyboard-only navigation, screen reader labels, zoom, and dynamic-state announcements.
- Test edge cases for resume upload/parse, account security, and data-source freshness using real backend records.
- Capture and review multiple sizes and interactive states beyond the screenshot set.

A high design score should not be inferred solely from automated green checks or polished screenshots.

## Follow-up polish

- Shortened repetitive project Edit/Delete buttons while retaining per-project accessible labels.
- Streamlined initial skill selection to keep saved skills in view while retaining search and an explicit full-catalog control.
- Removed overlapping generic choices from the fresh *showcase seed only*; existing browser-saved selections and all real user records remain unchanged.
- Expanded screenshot coverage to include role analysis and mobile Jobs/Applications.

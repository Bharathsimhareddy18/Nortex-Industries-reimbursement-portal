# Design — Nortex Travel Claims

A locked design system for this app. Every page reads this file before it changes.
Do not regenerate per page; amend this file when the system needs to grow.
Tokens live in `/tokens.css`; pages reference them by name, never raw values.

## Genre
playful (the soft end): tinted surfaces, low chroma, cards that lift a little on hover.

## Macrostructure family
- Marketing pages (`index.html`, `login.html`): Narrative Workflow. Numbered stages of the
  claim's life, each with a short explanation and a real product screenshot.
- App pages (`dashboard`, `claims`, `new-request`, `notifications`): Workbench-family app shell.
  Sidebar + top bar + content. Function carries the page; no decoration.
- Content pages: none yet.

## Theme
Custom: white does most of the work, blue in different shades carries actions, progress and a few
tinted cards. Light theme only. (Changed 2026-10-01 from the earlier sand/mocha palette at the user's request.)
- `--color-paper`     oklch(99.2% 0.003 250)  near-white
- `--color-paper-2`   oklch(97.2% 0.008 250)
- `--color-ink`       oklch(23% 0.03 262)     navy-black text
- `--color-ink-2`     oklch(48% 0.18 262)     brand blue: primary buttons
- `--color-rule`      oklch(92.5% 0.01 255)
- `--color-sky`       oklch(95.5% 0.025 250)  palest blue card
- `--color-blue-soft` oklch(89% 0.05 252)     light blue card
- `--color-navy`      oklch(33% 0.1 262)      deep navy card, white text
- `--color-accent`    oklch(55% 0.17 257)     progress, "you are here"
- `--color-focus`     oklch(55% 0.2 262)

Axes: light / geometric-sans / cool.

## Typography
- Display: Bricolage Grotesque, weight 600, roman only (no italic headings).
- Body: Geist, weight 400 / 500.
- Mono: Geist Mono, for claim numbers, amounts and stage labels.
- Display tracking: -0.02em to -0.04em.
- Scale anchor: `--text-display` = clamp(2.5rem, 5vw + 0.5rem, 4.5rem).
- Two-tone headings: second line in `--color-display-2`, large text only.

## Spacing
4-point named scale (`--space-3xs` 4px to `--space-3xl` 112px) in `tokens.css`.

## Motion
- Easings: `--ease-out` cubic-bezier(0.16, 1, 0.3, 1), `--ease-in`, `--ease-in-out`.
- Reveal: landing stages sweep in once (opacity + 16px translate). App pages: none.
- Hover: screenshots and template tiles lift 1-2px.
- Reduced motion: every animation and transition is switched off.

## Microinteractions stance
- Silent success: inline confirmation in place ("You approved this."), never celebratory toasts.
- Busy buttons change their label ("Sending…", "Reading the bill…") and disable.
- Focus ring shows instantly, never animated.
- Errors sit inline under the field or in the row they belong to.

## CTA voice
- Primary: blue pill (`--color-ink-2` fill, white text), verb first ("Sign in", "Submit request").
- Secondary: outlined pill on surface, or a typographic link with arrow and 1px underline.
- One primary per view.

## Mixed tones
Three blue shades fill cards side by side (`.tone-sky`, `.tone-blue`, `.tone-navy`); everything else is white.
Sky and blue take ink text (12:1+); navy takes white text (12:1). No two neighbouring cards share a tone.

## Per-page allowances
- Marketing pages MAY use real product screenshots on tinted bands. No fake browser chrome.
- App pages MUST NOT use enrichment.

## What pages MUST share
- The wordmark (ink square "N" + "Nortex").
- The fonts, the palette, the pill CTA voice, 12px card radius, 8px inputs.
- Status badges: Awaiting approval, Awaiting advance, Upload receipts, With Finance, Paid, Rejected.

## What pages MAY differ on
- Section layout within their family.
- Which tone a card takes.

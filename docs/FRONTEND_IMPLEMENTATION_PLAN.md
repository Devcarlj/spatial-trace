# Frontend implementation plan — SpatialTrace

## Purpose

SpatialTrace already proves that it can index a clip, answer a question, and
return grounded frames. This phase makes that capability feel like a finished
personal product: clear before the first click, reassuring while it works, and
convincing when it answers.

The interface should make one promise:

> **Your visual memory, searchable.**

This is a hackathon presentation layer, not a new product platform. Build the
flows below against the existing endpoints and response fields. Do not add a
dashboard, account system, background-job system, sharing system, or new
backend feature unless a selected demo clip exposes a concrete problem.

## Product story

The user has a short recording and cannot remember where an item was last
seen. They:

1. add the clip and give it a human-readable name;
2. see that SpatialTrace has prepared the clip;
3. ask a natural-language question such as “Where are my keys?”;
4. receive a plain-language answer, the strongest evidence frame, its timestamp,
   and an optional mask/box; and
5. browse earlier sightings when movement or history is relevant.

The UI must make uncertainty understandable. A low-confidence result is a
useful outcome when it says what was checked and why it cannot be certain.

## Visual direction

### Brand character

Use a calm, tactile visual identity inspired by a field notebook and a camera
viewfinder. The product should feel personal and observant rather than like a
developer console or a surveillance dashboard.

- **Name:** `SpatialTrace`
- **Tagline:** `Your visual memory, searchable.`
- **Voice:** concise, warm, evidence-first. Say “I found your keys at 00:18,”
  not “Object detection completed successfully.”
- **Motif:** a rounded focus ring / map-pin dot used for the favicon, loading
  state, selected frame, and answer status.

### Typography

Use `next/font/google` so font loading is managed by Next rather than a CSS
network import.

- **Headings and display:** `DM Sans` (600–700). Friendly, rounded, readable
  at large sizes.
- **Body and controls:** `Nunito Sans` (400–700). Soft letterforms and clear
  small text.
- **Timecodes and evidence metadata:** `IBM Plex Mono` (400–500) in small
  doses, so timestamps read like trustworthy records.

Define these as CSS variables in `layout.tsx` and use system fallbacks. Keep
text sizes generous: 16px body text, 44–56px desktop headline, 30–38px mobile
headline, and never use less than 12px for essential information.

### Colour system

Use a warm neutral base with one identifiable deep teal and a coral evidence
accent. Do not use every colour on every screen.

| Token | Value | Use |
| --- | --- | --- |
| `--ink` | `#14211F` | Primary text and dark surfaces |
| `--canvas` | `#F8F5EE` | Page background |
| `--paper` | `#FFFCF6` | Cards and forms |
| `--teal` | `#0F766E` | Primary action, links, selected state |
| `--teal-soft` | `#D9F0EC` | Successful / found status background |
| `--coral` | `#EE6C4D` | Mask, focus ring, key evidence accent |
| `--sun` | `#F2C14E` | Movement / attention state |
| `--mist` | `#E9E3D8` | Borders, inactive controls |
| `--muted` | `#64716E` | Supporting text |
| `--danger` | `#B9382E` | Errors only |

Use a coral mask at roughly 35–45% opacity with a 2px outline. Use teal for
buttons and selected evidence. Do not use red for an uncertain result; use a
soft neutral or sun tone and clear language.

### Shape, depth, and motion

- 18–24px card radius; pills only for compact tags and filters.
- One soft shadow family: `0 16px 40px rgb(20 33 31 / 10%)`.
- Buttons have 12px radius and a minimum 44px height.
- Transitions are 160–220ms and only communicate change: selected evidence,
  progress, and result arrival. Respect `prefers-reduced-motion`.
- Use simple inline SVG icons; do not add an icon package for this scope.

## Information architecture

The app remains a single focused workspace. It has three clear regions rather
than a generic sidebar dashboard.

```text
┌────────────────────────────────────────────────────────────────────┐
│ SpatialTrace        Your visual memory, searchable.      • Live    │
├────────────────────────────────────────────────────────────────────┤
│ “Where did I last see my keys?”                         [Ask]      │
│ Search this clip:  [Kitchen cleanup ▾]                             │
├───────────────────┬────────────────────────────────────────────────┤
│ CLIP LIBRARY      │ EVIDENCE                                         │
│ + Add a clip      │ [answer card: Found / Moved / Need more evidence]│
│                   │ [large frame with mask and timestamp]           │
│ Kitchen cleanup   │ [mask] [box] [fit] [zoom]                        │
│ 0:42 · Ready      │                                                  │
│                   │ SIGHTINGS                                        │
│ Desk reset        │ 00:18  strongest evidence                       │
│ 1:07 · Partial    │ 00:09  earlier sighting                          │
└───────────────────┴────────────────────────────────────────────────┘
```

On screens below 960px, place the query card first, evidence second, and make
the clip library a horizontally scrollable strip or a compact picker. Do not
hide the answer behind a drawer.

## Core screens and states

### 1. First visit / empty state

The empty state should sell the story in ten seconds, then give one obvious
next action.

- Large headline: **“Where did you last see it?”**
- Supporting sentence: “Add a short video, then ask SpatialTrace about the
  things inside it.”
- A visual empty evidence panel with an illustrated focus ring and three sample
  prompts: “Where are my keys?”, “When did I last see my glasses?”, “Did the
  mug move?”
- A prominent `Add your first clip` button that focuses the add-clip form.
- Add a small demo-chip row only when demo clips actually exist; never offer
  fake buttons.

### 2. Add clip / indexing

Replace the current raw form feeling with a compact, labelled card.

- Fields: `Video path` and `Clip name`.
- Explain the path in one sentence: “Choose a local video file on this machine.”
- Primary button: `Index clip`.
- During indexing, lock only the form being submitted and show a determinate
  stepper if the API provides progress later. Until then use a truthful
  indeterminate state: `Preparing frames… This can take a moment.`
- On success, add the clip to the library, select it, and place focus on the
  search input.
- For `partial` status, use a compact amber note: “Some frames could not be
  checked. Results may be incomplete.” Include `Retry missing frames` only if
  the existing index endpoint can safely be called again with the same clip.
- Give errors an action: “Couldn’t read this file. Check the path and try again.”

### 3. Ready-to-search state

Once a clip is selected, the query input becomes the visual centre of the page.

- Label: `Ask about this clip`.
- Placeholder: `Where are my keys?`
- Keep three query chips beneath it. A chip fills the input; it does not submit
  automatically.
- Put `Search` inside the input’s trailing action on desktop and full width
  beneath it on narrow screens.
- Show clip scope beside the input: `Searching: Kitchen cleanup`.

### 4. Answer card

Put the answer before technical metadata. The answer card uses one of three
status treatments:

| Result | Headline example | Treatment |
| --- | --- | --- |
| Found | `Found your keys` | Teal status dot and “Latest verified sighting” |
| Moved | `Your keys appear to have moved` | Sun status dot and an earlier → later summary |
| Unsure | `I need more evidence` | Neutral status dot, no false certainty |

Card content, in order:

1. State label and human answer.
2. A timestamp sentence: “Last verified at **00:18** in Kitchen cleanup.”
3. Evidence-strength phrase derived from existing score/search data: “Verified
   in 6 checked frames” or “Checked 32 frames before reaching the search limit.”
4. Optional compact disclosure: `Why this answer?` showing model calls, checked
   frames, and the existing complete/budget-exhausted information. Keep this
   out of the first-read path.

### 5. Evidence viewer

The frame deserves the largest portion of the screen. Retain the current
pixel-accurate mask support and improve its presentation.

- Use a dark ink viewer well with a checkerless image surface so the footage
  remains the focus.
- Put timecode in a high-contrast floating badge: `00:18.4`.
- Place result state as a small badge in the opposite corner.
- Controls: `Mask`, `Box`, `Fit`, `100%`, `200%`. Preserve independent Mask and
  Box toggles for truthful visual inspection.
- Default to `Fit`; make zoom available only when the source image is large
  enough to benefit from it.
- Add a concise caption under the frame: “Coral highlight marks the verified
  object.” If only a box is available, say so directly.
- Never stretch the image into a fixed-height crop that could conceal evidence.

### 6. Sightings timeline

Turn the existing list into a visual evidence timeline.

- Heading: `Evidence over time`.
- Each row has a thumbnail, timecode, relative label (`Latest`, `Earlier`), and
  confidence phrase. The selected row has a teal border/focus ring.
- A movement result shows two named endpoints first: `Earlier sighting` and
  `Latest sighting`, linked by a subtle arrow. Then show other sightings.
- An uncertain result labels rows as `Possible sighting`; it must not use
  `Confirmed` or `Found` language.
- Use buttons for rows, maintain keyboard arrow/tab navigation, and update the
  evidence viewer without scrolling the user back to the top.

## Component plan

Keep the page in the existing `frontend/app` directory. Extract visual units
only where it reduces complexity.

| Component | Responsibility | Existing data |
| --- | --- | --- |
| `app-shell.tsx` | Header, responsive grid, live/demo connection badge | health mode |
| `clip-library.tsx` | Clip list, selection, indexing status, add-clip trigger | `/api/clips` |
| `index-clip-card.tsx` | Video path/name input, submit and indexing status | `/api/index` |
| `query-bar.tsx` | Scoped natural-language search and example chips | selected `clip_id` |
| `answer-card.tsx` | Found/moved/unsure copy, strength and explanation disclosure | query result |
| `evidence-frame.tsx` | Frame, mask, box, timestamp, fit/zoom controls | existing component, extend only |
| `sightings-timeline.tsx` | Selectable evidence items / movement endpoints | `trail` |
| `empty-evidence.tsx` | First-visit and no-result presentation | app state |

Keep API calls and page-level state in `page.tsx` initially. Only introduce a
client-side context if prop drilling becomes genuinely hard. There is no need
for a global state library.

## Copy guide

Use product language that explains the result without pretending the system saw
more than it did.

| Avoid | Prefer |
| --- | --- |
| “FOUND_NOW” | “Found in this clip” |
| “Inference complete” | “Here’s the strongest evidence” |
| “Bounding box” | “Object outline” / “Detection box” |
| “No object detected” | “I couldn’t verify it in the checked frames” |
| “Model calls: 3” | “3 visual checks used” in the expanded explanation |

## Build order

### Phase A — visual foundations (half day)

1. Add `next/font/google` typography and semantic CSS tokens.
2. Replace the current generic Arial/green presentation with the brand palette,
   rounded components, focus states, and responsive grid.
3. Redesign header, empty state, connection badge, and form styling.
4. Verify keyboard focus, contrast, reduced motion, and 375px / 768px / 1440px
   layouts.

### Phase B — primary product flow (one day)

1. Build clip library and selected-clip scope indicator around existing
   `/api/clips` data.
2. Rework add-clip/indexing state with clear success, partial, and failure
   messages.
3. Make query bar the primary action after a clip is ready.
4. Add the answer card with plain-language state mapping and search completeness
   disclosure.

### Phase C — evidence experience (one day)

1. Upgrade `evidence-frame.tsx` with time badge, mask/box controls, fit/zoom,
   and caption.
2. Build evidence timeline with frame thumbnails, selected state, and movement
   endpoints.
3. Confirm masks remain aligned at every image size and zoom setting.
4. Validate Found, Moved, Unsure, partial clip, empty, and backend-error states
   using the existing synthetic demo fixtures.

### Phase D — demo polish (half day)

1. Apply copy guide consistently and remove developer terminology from the
   primary UI.
2. Curate three demo prompts and videos with reliable results.
3. Capture a short walkthrough: add clip → ask → evidence → earlier frame.
4. Run `npx tsc --noEmit`, `npm run lint`, and `npm run build`; manually test
   desktop and mobile widths in the browser.

## Acceptance criteria

The phase is complete when:

- A first-time viewer understands the product and first action without reading
  documentation.
- Indexing a clip clearly moves it through status and into the selected scope.
- Every answer names its clip, state, best timestamp, and strength of evidence.
- Evidence frames are large, legible, selectable, and retain accurate mask/box
  alignment at fit and zoomed views.
- The UI never presents uncertain or budget-limited searches as absence.
- Found, moved, unsure, partial-index, loading, and error states each have
  intentional copy and visuals.
- Keyboard navigation, visible focus, contrast, and reduced motion work.
- The frontend type-check, lint, build, and three chosen demo flows pass.

## Explicit scope boundaries

Do not spend hackathon time on user accounts, cloud uploads, video editing,
notifications, collaboration, multi-page analytics, or a generic component
library. The result page and the visual proof are the product.

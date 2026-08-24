# DESIGN — OiiOii.ai 100% Clone (UI/UX Specification)

> Companion to `PLAN.md` + `ARCHITECTURE.md`. Defines the visual language,
> component library, and interaction patterns for the Next.js frontend (`oioi/`).
> Target: a 100% functional clone of oiioii.ai's AI Animation Canvas.

## 1. Design Principles
1. **Canvas-first** — the infinite canvas is the hero; chrome recedes, content dominates.
2. **Dark, focused, pro-tool** — creators work long sessions; dark UI reduces eye strain and makes generated media pop.
3. **Concurrency visible** — multiple generations run at once; the UI always shows live queue + progress without blocking the canvas.
4. **Keyless-by-default** — the app must work with zero API keys (Pollinations image fallback); never dead-end a user on a missing-key modal.
5. **Accessible** — WCAG AA contrast, keyboard-navigable panels, focus rings, reduced-motion respected.
6. **Responsive** — desktop-first creative tool, but panels collapse to drawers ≤1024px and the canvas remains usable on tablet.

## 2. Design Tokens

### 2.1 Color — dark creative-tool palette
```
Background layers (z-axis depth)
  bg-base     #0a0a0b   app background (deepest)
  bg-surface  #131316   panels, cards
  bg-elevated #1c1c21   popovers, menus, active nodes
  bg-canvas   #0f0f12   the infinite canvas backdrop

Foreground
  fg-primary   #ededed   primary text
  fg-secondary #a1a1aa   secondary text / labels
  fg-muted     #71717a   placeholder / disabled
  fg-inverse   #0a0a0b   text on accent fills

Accent (brand — violet→fuchsia gradient, matches existing tailwind primary)
  accent-500  #8b5cf6   primary actions, selected state
  accent-600  #7c3aed   hover / pressed
  accent-400  #a78bfa   focus ring
  accent-glow #8b5cf633  soft glow for active generation nodes

Semantic
  success  #22c55e   completed generation / healthy provider
  warning  #f59e0b   degraded provider / queued
  danger   #ef4444   failed generation / unhealthy provider
  info     #3b82f6   streaming / processing

Borders / dividers
  border-subtle  #27272a   panel edges
  border-strong  #3f3f46   active panel edges
```

### 2.2 Typography
- **Font stack**: `Inter, system-ui, -apple-system, sans-serif` (UI) + `JetBrains Mono, monospace` (code/prompt fields).
- **Scale** (rem): 0.75 / 0.875 / 1 / 1.125 / 1.25 / 1.5 / 1.875 / 2.25 / 3.
- **Weights**: 400 body, 500 labels/buttons, 600 headings, 700 display.
- **Line-height**: 1.5 body, 1.2 headings, 1.15 mono.

### 2.3 Spacing & radius
- **Spacing scale** (4px base): 1→4px, 2→8px, 3→12px, 4→16px, 6→24px, 8→32px, 12→48px, 16→64px.
- **Radius**: sm 6px (inputs), md 8px (cards), lg 12px (panels), xl 16px (modals), full 9999px (pills/avatars).
- **Shadow**: layered `0 1px 2px #00000040, 0 8px 24px #00000060` for elevated panels.

### 2.4 Motion
- **Durations**: fast 120ms (hover), base 200ms (panel), slow 320ms (page).
- **Easing**: `cubic-bezier(0.4, 0, 0.2, 1)` standard, `cubic-bezier(0.16, 1, 0.3, 1)` for canvas pan/zoom.
- **Reduced motion**: all non-essential animation disabled via `prefers-reduced-motion`.

## 3. Layout — App Shell
```
┌─────────────────────────────────────────────────────────────────────┐
│ TopBar  [logo] [project name ▾] ............ [providers●] [avatar]    │ 56px
├──────────┬──────────────────────────────────────────────┬───────────┤
│          │                                              │           │
│ Left     │                                              │ Right     │
│ Sidebar  │            Infinite Canvas                   │ Inspector │
│ 280px    │            (pan/zoom, nodes)                 │  340px    │
│          │                                              │           │
│ • Models │   [image node] [video node] [chat node]      │ • Props   │
│ • Styles │   [character]  [scene]     [pipeline]        │ • Prompt  │
│ • Agents │                                              │ • Frames  │
│ • Queue  │                                              │ • History │
│          │                                              │           │
├──────────┴──────────────────────────────────────────────┴───────────┤
│ BottomBar  [+ generate] [model: ▾] [style: ▾] [queue: 3 running]      │ 48px
└─────────────────────────────────────────────────────────────────────┘
```
- **Left Sidebar** (collapsible → 64px icon rail): Models, Styles, Agents, Queue tabs.
- **Right Inspector** (collapsible → hidden): context-sensitive to selected node (image/video/chat/pipeline).
- **BottomBar**: primary generate action + quick model/style switcher + live queue count.
- **Canvas**: `react-flow-renderer` (already a dep) for nodes/edges; dark grid; zoom 25%–200%.
- **Responsive**: ≤1024px sidebars become slide-over drawers (Radix Dialog); canvas stays.

## 4. Component Library

### 4.1 Primitives (Radix-based, already installed)
`Button`, `Input`, `Textarea`, `Select`, `Slider`, `Switch`, `Tabs`, `Dialog`,
`DropdownMenu`, `Tooltip`, `Progress`, `ScrollArea`, `Separator`, `Label`,
`Avatar`, `Toast` (sonner), `AlertDialog`, `Checkbox`, `RadioGroup`, `Popover`.

### 4.2 Composite components (`oioi/src/components/`)
| Component | Path | Purpose |
|---|---|---|
| `AppShell` | `layout/AppShell.tsx` | top bar + sidebars + canvas slot |
| `TopBar` | `layout/TopBar.tsx` | logo, project switcher, provider health, avatar |
| `LeftSidebar` | `layout/LeftSidebar.tsx` | Models/Styles/Agents/Queue tabs |
| `RightInspector` | `layout/RightInspector.tsx` | node-context props |
| `BottomBar` | `layout/BottomBar.tsx` | generate button + quick switchers + queue count |
| `Canvas` | `canvas/Canvas.tsx` | react-flow infinite canvas |
| `ImageNode` | `canvas/ImageNode.tsx` | generated image node w/ progress |
| `VideoNode` | `canvas/VideoNode.tsx` | generated video node w/ first/last frame |
| `ChatNode` | `canvas/ChatNode.tsx` | streaming chat node (SSE) |
| `CharacterNode` | `canvas/CharacterNode.tsx` | character sheet node |
| `SceneNode` | `canvas/SceneNode.tsx` | scene background node |
| `PipelineNode` | `canvas/PipelineNode.tsx` | 7-agent pipeline status node |
| `ModelPicker` | `pickers/ModelPicker.tsx` | grouped Video/Image/LLM model select |
| `StylePicker` | `pickers/StylePicker.tsx` | 150+ style grid w/ search |
| `GeneratePanel` | `panels/GeneratePanel.tsx` | prompt + params → POST /images or /videos |
| `ChatPanel` | `panels/ChatPanel.tsx` | SSE streaming chat |
| `PipelinePanel` | `panels/PipelinePanel.tsx` | idea → run pipeline, per-agent status |
| `QueuePanel` | `panels/QueuePanel.tsx` | concurrent generation jobs w/ progress |
| `ProviderHealth` | `providers/ProviderHealth.tsx` | GET /providers/health badges |
| `FrameReference` | `canvas/FrameReference.tsx` | first/last-frame image dropzones |

### 4.3 Node visual spec (canvas)
- **Card**: `bg-surface`, `border-subtle`, `radius-lg`, 240×?px (auto height).
- **Header**: model id pill (mono, 12px) + status dot (success/warning/danger/info) + drag handle.
- **Body**: media preview (16:9 or 1:1) or streaming text; shimmer placeholder while pending.
- **Footer**: prompt excerpt (1 line, `fg-muted`, truncate) + action row (regenerate, use as frame, delete).
- **Selected**: `border-strong` + `accent-glow` ring; inspector populates from selected node.
- **Active generation**: pulsing `accent-glow` ring + `Progress` bar in footer.

## 5. Interaction Patterns

### 5.1 Generate (image/video)
1. User opens `GeneratePanel` (BottomBar `+ generate` or node `+`).
2. Picks model (grouped), style (searchable), writes prompt, optional first/last frame.
3. Submit → optimistic `ImageNode`/`VideoNode` appears on canvas (status=queued).
4. POST `/api/v1/images/generations` (or `/videos`); on response node updates with URL (status=completed).
5. Failure → node shows danger ring + retry button; queue decrements.

### 5.2 Streaming chat
1. `ChatNode` input → GET `/api/v1/chat/stream` (SSE).
2. Tokens append live (info dot → success dot on `[DONE]`).
3. Stop button cancels the stream (AbortController).

### 5.3 Pipeline run
1. `PipelinePanel`: idea + style + duration → POST `/api/v1/projects/{id}/pipeline/run`.
2. `PipelineNode` renders 7 agent sub-steps with live status (pending→running→completed).
3. Each completed agent spawns its asset node on the canvas (script, characters, scenes, clips, audio).
4. Final stitch → a `VideoNode` with the short film.

### 5.4 Provider failover (visible)
- `ProviderHealth` badges in TopBar: green/amber/red per provider from `/providers/health`.
- On generation failure, toast: "⚠️ {provider} unavailable — retrying on {fallback}" (sonner).

## 6. State Management
- **Zustand** store (`src/lib/stores/canvas-store.ts`): nodes, edges, selectedId, queue, project.
- **React Query** for server state: `/models`, `/styles`, `/providers/health`, `/projects`.
- **Prisma** persistence: `Project.canvasData` (JSON: nodes+edges) saved on debounce.
- **SSE** handled in a custom hook `useChatStream` (AbortController + EventSource-like fetch).

## 7. Accessibility
- All interactive elements keyboard reachable; visible focus ring (`accent-400`, 2px offset).
- Color contrast ≥4.5:1 for text (verified: `fg-secondary #a1a1aa` on `bg-surface #131316` = 7.4:1).
- `aria-live="polite"` on streaming chat + queue status.
- Icons (lucide-react) paired with `aria-label`.
- Reduced-motion: canvas pan/zoom easing → instant; shimmer → static.

## 8. Empty / Loading / Error States
- **Empty canvas**: centered illustration + "Describe your idea to begin" CTA → opens `PipelinePanel`.
- **Loading**: skeleton shimmer in node body; `Progress` bar in footer.
- **Error**: danger ring + inline retry; toast with provider failover message.
- **No keys**: banner (dismissible) — "Image generation running on free Pollinations fallback. Add keys in Settings for more models."

## 9. File Structure (to be created in IMPLEMENTATION)
```
oioi/src/
  app/
    layout.tsx          (root: AppShell wrap)
    page.tsx            (canvas route)
    globals.css         (design tokens)
  components/
    layout/             (AppShell, TopBar, LeftSidebar, RightInspector, BottomBar)
    canvas/             (Canvas, *Node, FrameReference)
    pickers/            (ModelPicker, StylePicker)
    panels/             (GeneratePanel, ChatPanel, PipelinePanel, QueuePanel)
    providers/          (ProviderHealth)
    ui/                 (Radix primitive wrappers)
  lib/
    stores/             (canvas-store.ts)
    hooks/              (useChatStream, useModels, useStyles, useProviders)
    api/                (axios client + endpoints)
    utils/              (cn, formatters)
  __tests__/            (component + store tests)
```

# Design System: Flashcard Library and Management — studIA
**Project ID:** 12596236935233664319

## 1. Visual Theme & Atmosphere

The studIA interface embodies a **dark, immersive, and technically sophisticated** aesthetic inspired by Material Design's dark theme principles. The atmosphere is **dense yet breathable** — a deep charcoal canvas punctuated by electric cyan and violet accents that evoke a sense of focused, high-tech studiousness. The overall vibe is "**Night-Mode Engineering Lab**" — utilitarian with a polished, modern edge. Subtle ambient glows (blurred gradient orbs of cyan and violet) float behind key content areas like the flashcard study mode, creating an atmospheric depth without distraction.

The design balances **information density** (dashboards, tables, statistics) with **generous whitespace** and clear visual hierarchy, ensuring the interface feels powerful but never overwhelming.

## 2. Color Palette & Roles

### Primary Colors
| Descriptive Name | Hex Code | Role |
|---|---|---|
| **Electric Cyan** | `#06b6d4` | Primary brand accent. Used for active navigation highlights, primary action buttons ("Registrar Estudo", "Criar Novo Baralho", "Ver Resposta"), progress bars, interactive element focus states, and data emphasis (e.g., streak days, review counts). Conveys energy and forward motion. |
| **Deep Violet** | `#8b5cf6` | Secondary accent. Used for notification pulses, secondary progress indicators (e.g., "Questões" goal bar), difficulty badges, avatar gradient endpoints, and ambient background glows. Adds a layer of sophistication and depth. |

### Background & Surface Colors
| Descriptive Name | Hex Code | Role |
|---|---|---|
| **Abyss Black** | `#121212` | The deepest background layer. Used as the page-level canvas, creating maximum contrast for content surfaces to float above. |
| **Charcoal Surface** | `#1e1e1e` | The primary surface color for cards, sidebar, header, modals, and all elevated content containers. Slightly lighter than the abyss to create subtle depth separation. |
| **Ember Border** | `#333333` | Subtle border color for all cards, dividers, and container edges. Provides structure without harshness — visible but whisper-quiet against dark surfaces. |

### Semantic / Feedback Colors
| Descriptive Name | Hex Code | Role |
|---|---|---|
| **Verdant Success** | `#10b981` | Success states, correct answers ("Acertos"), completed milestones, and positive percentages (≥80%). |
| **Signal Red** | `#ef4444` | Error states, incorrect answers ("Erros"), missed streak days, low percentages (<70%), and the "Errei" rating button. |
| **Caution Amber** | `amber-500` | Warning/pending states, such as "72 Pendentes" in the semester progress card. |

### Text Colors
| Descriptive Name | Hex Code | Role |
|---|---|---|
| **Pure White** | `#ffffff` | High-emphasis text: headings, bold numbers, card titles, logo text. |
| **Soft Cloud** | `#e5e7eb` | Default body text (gray-200). Used for paragraph content and general readable text. |
| **Muted Steel** | `#9ca3af` | Medium-emphasis text (gray-400). Used for labels, section headers, metadata, timestamps. |
| **Faded Ash** | `#6b7280` | Low-emphasis text (gray-500). Used for descriptions, secondary labels, and inactive states. |

### Accent Colors for Flashcard Decks
| Descriptive Name | Hex Code | Role |
|---|---|---|
| **Sapphire Blue** | `blue-500` | Cálculo III deck icon and progress ring. |
| **Tangerine Orange** | `orange-500` | Mecânica dos Sólidos deck icon and progress ring. |
| **Crimson Red** | `red-500` | Termodinâmica deck icon and progress ring. |
| **Emerald Green** | `green-500` | Algoritmos deck icon and progress ring. |
| **Amethyst Purple** | `purple-500` | Física II deck icon and progress ring. |

## 3. Typography Rules

**Font Family:** Inter — a clean, geometric sans-serif with excellent legibility on screens. Used universally across the interface.

| Element | Weight | Size | Character |
|---|---|---|---|
| **Logo ("studIA")** | Bold (700) | 2xl (1.5rem) | Tight tracking (`tracking-tight`). The "IA" portion is colored Electric Cyan for brand identity. |
| **Page Titles** | Bold (700) | 2xl–3xl | White. Commanding presence at top of content areas. |
| **Section Headers** | Semibold (600) | xs (0.75rem) | Uppercase, wider letter-spacing (`tracking-wider`), Muted Steel color. Creates a quiet structural rhythm. |
| **Card Titles** | Bold (700) | lg (1.125rem) | White. Clear identification of deck/card names. |
| **Body Text** | Regular (400) | sm–base | Soft Cloud. Comfortable reading weight. |
| **Data Numbers** | Bold (700) | xl–4xl | White or accent colors. Large, impactful statistics. |
| **Labels & Metadata** | Medium (500) / Semibold (600) | xs (0.75rem) | Uppercase, Muted Steel or Faded Ash. Structured identification. |
| **Flashcard Question** | Medium (500) | 2xl–3xl | White, relaxed line height (`leading-relaxed`). Centered, generous breathing room. |
| **Math Formulas** | MathJax rendered | Variable | Displayed in dedicated formula containers with dark backgrounds. |

## 4. Component Stylings

### Buttons
* **Primary Action** (e.g., "Registrar Estudo", "Criar Novo Baralho", "Ver Resposta"): Pill-shaped with generously rounded corners (`rounded-lg` or `rounded-full`). Solid Electric Cyan (`#06b6d4`) fill with a diffused cyan glow shadow (`shadow-lg shadow-cyan-500/30`). White text, medium font weight. Hover darkens slightly to `cyan-600`. The "Ver Resposta" button uses full-width `rounded-full` with an icon suffix.
* **Secondary Action** (e.g., "Meu Plano"): Same rounded shape but with a transparent fill, Charcoal Surface background, and a subtle gray border (`border-gray-600`). Gray-200 text. Hover lifts to `gray-700` background.
* **Rating Buttons** (Flashcard Study Mode): Four equal-width buttons in a grid. Each has a Charcoal Surface background with a colored 2px border matching its semantic meaning (red=Errei, orange=Difícil, green=Bom, blue=Fácil). On hover, the entire button fills with its border color and text turns white. Contains a Material icon, bold label, and small timing hint.
* **Deck "Estudar Agora"**: Full-width within card footer. Either Electric Cyan or deck-specific color (e.g., blue-600 for Cálculo III). Rounded-lg.
* **"Tudo em dia"**: Subdued style — Charcoal Surface with gray border and gray text. Indicates no action needed.

### Cards / Containers
* **Stat Cards** (Dashboard): Charcoal Surface background, Ember Border, subtly rounded corners (`rounded-xl` — approximately 12px, generously curved). A large, faded icon watermark floats in the top-right (10% opacity, increasing to 20% on hover). Contains a thin progress bar at the bottom.
* **Deck Cards** (Flashcard Library): Same surface and border treatment. Organized vertically: icon badge → title → description → stats with circular SVG progress ring → action footer. Footer has a slightly different background tint (`bg-white/[0.02]`) separated by a top border.
* **Flashcard (Study Mode)**: Large, centered card with `rounded-2xl` corners and elevated shadow (`shadow-xl`). Features a 3D flip animation (CSS `perspective: 1000px`, `transform-style: preserve-3d`, `backface-visibility: hidden`) to reveal the answer side. Front shows the question; back shows a step-by-step solution.
* **"New Deck" Card**: Dashed border (`border-dashed border-gray-700`), centered content with a large circular add icon. Hover transitions border to Electric Cyan.

### Inputs / Forms
* **Search Input**: Charcoal Surface background, Ember Border, rounded-lg. Left-aligned search icon inside. Placeholder text in Faded Ash. Focus ring uses Electric Cyan.
* **Filter Button**: Square icon-only button with same surface/border treatment as the search input.

### Navigation (Sidebar)
* **Active Item**: Electric Cyan text with a 10% opacity cyan background tint (`bg-primary/10`). Icon inherits the cyan color.
* **Inactive Item**: Muted Steel text (gray-400). Icon at 70% cyan opacity. On hover: white text, gray-800 background, full cyan icon.
* **Sidebar Footer**: User avatar with a gradient border ring (Electric Cyan → Deep Violet). Username in white, "Sair da conta" in Faded Ash.

### Progress Indicators
* **Linear Progress Bars**: Thin (1–2px height), rounded-full, gray-700 track. Fill color matches the semantic context (cyan for hours, violet for questions, green for completion).
* **Circular Progress Rings**: SVG-based, 16×16 unit viewBox. Gray-700 background ring, colored foreground stroke with `stroke-dasharray` controlling fill. Percentage text centered inside.
* **Streak Calendar**: Row of small (32×32px) rounded squares. Completed days show cyan tint with terminal icon; missed days show red tint with error icon; empty days are plain gray-700.

### Study Mode Header
* Contains a "Voltar" (back) button, a vertical divider (`h-6 w-px bg-gray-700`), the deck name with its icon, a timer display, a thin progress bar showing card position, and "Cartão X de Y" counter in Electric Cyan.

## 5. Layout Principles

* **Sidebar-first Layout**: Fixed 256px (w-64) sidebar on the left for desktop. Sticky, full-height. Content area fills remaining space (`flex-1 min-w-0`).
* **Responsive Breakpoints**: Sidebar hidden on mobile (`hidden md:flex`), replaced by a top mobile nav bar. Content adapts from single-column (mobile) to multi-column grids (desktop).
* **Grid System**: Dashboard uses `grid-cols-1 md:grid-cols-2 lg:grid-cols-4` for stat cards. Flashcard library uses `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`. Bottom dashboard section uses `lg:grid-cols-3` with a 2/3 + 1/3 split.
* **Spacing Rhythm**: Consistent 24px (p-6) internal card padding. 32px (gap-8) between major sections. 24px (gap-6) between grid items. 16px (gap-4) for tighter element groups.
* **Content Area Padding**: 32px horizontal padding on desktop (`px-8`), 16px on mobile (`px-4`). 32px vertical padding (`py-8`).
* **Whitespace Philosophy**: Generous but purposeful. Large margins between sections create clear visual groupings. Card interiors use ample padding to prevent content from feeling cramped. The flashcard study mode maximizes the central card area with ambient background effects.
* **Z-Layer Strategy**: Sidebar at z-50, header at z-30–40, main content at z-10, ambient background effects at z-0 with `pointer-events-none`.
* **Backdrop Blur**: Header uses `backdrop-blur-md` with a semi-transparent background (`bg-background-dark/80`) for a frosted glass effect when scrolling.

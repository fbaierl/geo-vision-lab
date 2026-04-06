# Palantir AIP Style Reference Guide

Based on research of Palantir Gotham/Foundry documentation and UI patterns, here are the key visual elements to target for the GeoVision Lab redesign.

## Key Visual Characteristics

### 1. Color Palette
- **Background**: Deep dark blues/blacks (#0a0a0f, #12121a, #1a1a24)
- **Panels**: Slightly lighter dark (#1e1e28, #242430)
- **Accents**: Cyan/teal (#00d4ff, #00b8d4), blue (#3daee9)
- **Text**: White (#ffffff) for headers, muted gray (#a0a0a0) for secondary
- **Borders**: Subtle dark (#2a2a35, #3a3a45)
- **Success/Active**: Green (#00e676)
- **Warning**: Amber (#ffab00)
- **Error**: Red (#ff5252)

### 2. Layout Structure (Split Panel)
```
┌─────────────────────────────────────────────────────────────┐
│  TOP COMMAND BAR (48px)                                      │
│  [Logo] [Search] [Actions] [Settings]                        │
├────────────┬────────────────────────────────┬───────────────┤
│            │                                │               │
│  LEFT      │     MAIN MAP AREA              │  RIGHT        │
│  SIDEBAR  │     (Full-screen focus)        │  DETAIL       │
│  (280px)  │                                │  PANEL        │
│            │     - Floating controls       │  (320px)      │
│  Entity   │     - Layer toggles            │               │
│  Browser  │     - Map search               │  Properties   │
│            │                                │  Timeline     │
│  Filter   │                                │  Relations    │
│  Controls │                                │               │
│            │                                │               │
├────────────┴────────────────────────────────┴───────────────┤
│  BOTTOM TIMELINE SCRUBBER (64px)                             │
│  [Play] [Date Range] [Events]                                │
└─────────────────────────────────────────────────────────────┘
```

### 3. Map Features
- **Tile Layer**: Dark mode (CartoDB Dark Matter or Mapbox Dark)
- **Markers**: Custom SVG icons, color-coded by entity type
- **Connections**: Lines/arcs between related locations
- **Floating Panel** (top-right): Layer toggles, base map selector
- **Mini-map**: Bottom-right corner inset for navigation

### 4. UI Component Style
- **Panels**: No rounded corners (sharp 0px), subtle 1px borders
- **Buttons**: Flat, icon-only with tooltips, subtle hover glow
- **Inputs**: Dark background (#1a1a24), subtle border on focus
- **Cards**: Flat background, left accent border (3px) for selection
- **Shadows**: Minimal, subtle glow for focus state only
- **Typography**: 
  - Headers: Sans-serif (Inter, Roboto)
  - Data/Coordinates: Monospace (JetBrains Mono, Fira Code)

### 5. Interaction Patterns
- **Selection**: Left accent bar + subtle background highlight
- **Hover**: Subtle background color shift + cyan border glow
- **Panels**: Slide in/out with 200ms ease-out animation
- **Map transitions**: Smooth flyTo animations (500ms)

## Reference URLs
- Palantir Map Overview: https://palantir.com/docs/foundry/map/map-overview/
- Palantir Styling: https://palantir.com/docs/foundry/map/styling/
- Dark Theme Discussion: https://community.palantir.com/t/dark-mode-across-the-whole-platform/5421

## Screenshots for Reference
- See `debug/palantir_aip.png` (user-provided reference)
- Geographic dashboard examples on Pinterest: https://nz.pinterest.com/pin/1196337404691627/

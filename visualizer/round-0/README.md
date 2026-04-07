# Prosperity 4 — Log Visualizer

<div align="center">

**A client-side web app for inspecting and comparing IMC Prosperity 4 official submission logs.**

No backend. No accounts. No data leaves your browser.

[Features](#features) · [Getting Started](#getting-started) · [Usage](#usage) · [Tech Stack](#tech-stack)

</div>

---

## Features

### Single Run Analysis
- **Run summary cards** — total PnL, max drawdown, per-product breakdown
- **Per-product stats** — fills, buy/sell volume, avg prices, avg edge vs mid, markouts, spread stats, passive/aggressive classification
- **Charts** — PnL over time, price + fill overlay, inventory reconstruction, spread, drawdown
- **Trade table** — sortable, filterable, with CSV export
- **Order book snapshot viewer** — inspect bid/ask depth at any fill timestamp
- **HTML report export** — self-contained report you can save or share

### Compare Mode
- Upload 2+ log files and compare side by side
- Overlaid PnL, inventory, and drawdown charts across runs
- Per-product or total comparison
- Side-by-side summary panels with key metrics

### Metrics (all derived from official logs only)
| Metric | Source | Label |
|---|---|---|
| PnL | `profit_and_loss` field in activitiesLog | Reported |
| Inventory | Reconstructed from `tradeHistory` | Derived |
| Edge vs Mid | Fill price vs mid price at fill time | Derived |
| Fill Classification | Fill price vs best bid/ask (PASSIVE / AGGRESSIVE / UNKNOWN) | Derived |
| Markouts | Mid price change after fill (next, +500, +1000 ticks) | Derived |
| Drawdown | Peak-to-trough from PnL series | Derived |
| Spread | Best ask − best bid from order book snapshots | Derived |

---

## Getting Started

### Prerequisites

You need **Node.js** (v18 or later) and **pnpm** installed.

<details>
<summary><strong>Windows</strong></summary>

1. **Install Node.js**
   - Download the **LTS** installer from [https://nodejs.org](https://nodejs.org)
   - Run the installer — accept defaults and make sure **"Add to PATH"** is checked
   - **Close and reopen** your terminal (Command Prompt or PowerShell) so it picks up the new PATH

2. **Install pnpm**
   ```
   npm install -g pnpm
   ```

3. **Verify installation**
   ```
   node --version
   pnpm --version
   ```
   Both should print a version number.

</details>

<details>
<summary><strong>macOS</strong></summary>

**Option A — Using Homebrew (recommended)**
```bash
brew install node
npm install -g pnpm
```

**Option B — Using the installer**
- Download the macOS **LTS** installer from [https://nodejs.org](https://nodejs.org)
- Run it, then open Terminal and install pnpm:
  ```bash
  npm install -g pnpm
  ```

**Verify installation:**
```bash
node --version
pnpm --version
```

</details>

<details>
<summary><strong>Linux (Ubuntu / Debian)</strong></summary>

```bash
# Install Node.js via NodeSource
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install pnpm
npm install -g pnpm

# Verify
node --version
pnpm --version
```

**Arch Linux:**
```bash
sudo pacman -S nodejs npm
npm install -g pnpm
```

**Fedora:**
```bash
sudo dnf install nodejs npm
npm install -g pnpm
```

</details>

---

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/prosperity4-visualizer.git
cd prosperity4-visualizer

# Install dependencies
pnpm install

# Start the dev server
pnpm dev
```

The terminal will print a local URL (usually `http://localhost:5173`). Open it in your browser.

### Building for Deployment

```bash
pnpm build
```

This produces a static `dist/` folder you can deploy to GitHub Pages, Vercel, Netlify, or serve locally:

```bash
npx serve dist
```

---

## Usage

### Single Run

1. Open the app in your browser
2. Drag and drop an official Prosperity 4 `.log` file onto the upload zone (or click to browse)
3. The app parses everything client-side — you'll immediately see run summary cards
4. Select a product to see detailed charts, trade table, and snapshot viewer
5. Use the **Report** button to export an HTML report, or export trades as CSV from the trade table

### Compare Mode

1. Upload two or more `.log` files
2. The app automatically switches to Compare mode (or toggle manually in the header)
3. Choose **Total** or a specific product to compare
4. Overlaid charts show PnL, inventory, and drawdown across runs
5. Side-by-side panels show key metrics for quick comparison

### Supported File Formats

| Format | Support |
|---|---|
| `.log` (Prosperity 4 official) | Full support — this is the primary input |
| `.json` | Parsed if valid Prosperity 4 format |

---

## Project Structure

```
prosperity4-visualizer/
├── index.html              # HTML entry point
├── package.json
├── tsconfig.json
├── vite.config.ts
├── README.md
└── src/
    ├── main.tsx             # React entry point
    ├── App.tsx              # Main app — all views and components
    ├── parsing/
    │   ├── types.ts         # TypeScript type definitions (data model)
    │   └── parser.ts        # Log parser + metric computation
    └── domain/
        ├── colors.ts        # Color constants
        └── utils.ts         # Formatting + CSV/HTML export utilities
```

---

## Tech Stack

- **React 18** + **TypeScript** — UI framework
- **Vite** — build tool and dev server
- **Recharts** — charts
- **Lucide React** — icons
- **Lodash** — utility functions

---

## Design Principles

1. **Client-side only** — no backend, no database, no authentication
2. **Official logs only** — does not depend on custom strategy loggers or bot internals
3. **Objective metrics** — no inference of strategy intent; only facts from the log
4. **Reported vs Derived** — metrics sourced directly from the log are labeled "Reported"; reconstructed metrics are labeled "Derived"
5. **Comparison-first** — multi-run comparison is a core feature, not a bolt-on

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `pnpm: command not found` | Run `npm install -g pnpm`, then reopen your terminal |
| `node: command not found` | Install Node.js from [nodejs.org](https://nodejs.org) and reopen your terminal |
| Port 5173 already in use | Kill the other process or run `pnpm dev -- --port 3000` |
| File won't parse | Make sure it's an official Prosperity 4 `.log` file (JSON with `activitiesLog` and `tradeHistory` keys) |
| Charts look empty | Check that the log contains trade data — some early tutorial logs may have zero fills |

---

## License

MIT

// One palette for HTML surfaces, technical drawings, ECharts and the terminal.
export const theme = {
  surface: "#FFFFFF",
  secondary: "#F3F4F6",
  nav: "#272B30",
  "nav-header": "#DDE1E5",
  "nav-secondary": "#42474D",
  text: "#171A1F",
  muted: "#5C626B",
  border: "#D6D9DE",
  accent: "#365A73",
  green: "#346E57",
  red: "#A04B44",
  amber: "#886025",
  unknown: "#BBC1C9",
  down: "#9299A2",
  disabled: "#5F6875",
  tx: "#9B6B2F",
  grid: "#EAECF0",
  selected: "#DEE7ED",
  "node-border": "#B6BDC6",
  terminal: "#202429",
  "terminal-text": "#E2E6EB",
} as const;

// Presentation-only tokens. Keep the shared chart/terminal palette above stable:
// refreshing a control or navigation surface must not recolor telemetry.
export const interfaceTokens = {
  "ui-font":
    'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  "ui-radius": "0px",
  "ui-soft": "#F7F8FA",
  "ui-hover": "#EDF0F3",
  "ui-nav-text": "#C5CCD5",
  "ui-nav-hover": "#343940",
  "ui-line": "#E3E7EC",
  "ui-control-line": "#C5CCD4",
  "ui-control-hover": "#8B99A8",
  "ui-accent-hover": "#29475D",
  "ui-type-small": "12px",
  "ui-type-caption": "11px",
} as const;

export const cssTokens = Object.fromEntries(
  Object.entries({ ...theme, ...interfaceTokens }).map(([key, value]) => [
    `--${key}`,
    value,
  ]),
);

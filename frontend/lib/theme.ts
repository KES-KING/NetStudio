// One palette for HTML surfaces, technical drawings, ECharts and the terminal.
export const theme = {
  surface: "#FFFFFF",
  secondary: "#F3F4F6",
  nav: "#272B30",
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
export const cssTokens = Object.fromEntries(
  Object.entries(theme).map(([key, value]) => [`--${key}`, value]),
);

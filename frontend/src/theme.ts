import { createTheme } from '@mui/material';

// Design tokens in one place: every page shares this palette, type scale
// and spacing instead of each component inventing its own. A fixed light
// theme — the sentence-highlight colours in bands.ts are calibrated for
// dark text on light backgrounds, so switching to a dark palette would
// desaturate or invert the WCAG-checked contrast those colours were tuned
// for (consistency over configurability for this tool).
export const tokens = {
  color: {
    primary: '#3b5bdb',
    primaryDark: '#2a46b8',
    background: '#fafafa',
    surface: '#ffffff',
    textPrimary: '#1a1a1a',
    textSecondary: '#5a5a5a',
    border: '#e0e0e0',
    success: '#2e7d32',
    warning: '#b28704',
    error: '#c0392b',
  },
  spacing: {
    unit: 8, // MUI's default spacing unit; named here so other tokens can reference it
  },
  radius: {
    sm: 4,
    md: 8,
  },
  // Minimum interactive target size (WCAG 2.5.5 / 2.5.8): every button,
  // chip-button and chart point people can click or tap honours this.
  minTouchTarget: 44,
};

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: tokens.color.primary, dark: tokens.color.primaryDark },
    background: { default: tokens.color.background, paper: tokens.color.surface },
    text: { primary: tokens.color.textPrimary, secondary: tokens.color.textSecondary },
    success: { main: tokens.color.success },
    warning: { main: tokens.color.warning },
    error: { main: tokens.color.error },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
  },
  shape: {
    borderRadius: tokens.radius.sm,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { minHeight: tokens.minTouchTarget },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: { minWidth: tokens.minTouchTarget, minHeight: tokens.minTouchTarget },
      },
    },
    // Visible focus outline on every focusable element, not just MUI's
    // default ripple — required for full keyboard operability (Part B.7).
    MuiCssBaseline: {
      styleOverrides: {
        ':focus-visible': {
          outline: `3px solid ${tokens.color.primary}`,
          outlineOffset: '2px',
        },
      },
    },
  },
});

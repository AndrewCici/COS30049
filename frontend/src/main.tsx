import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';

// Fixed light theme: sentence highlight colours are calibrated for dark
// text on light backgrounds, so the app deliberately does not switch to a
// dark palette (consistency over configurability for this tool).
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#3b5bdb' },
    background: { default: '#fafafa' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </StrictMode>,
);

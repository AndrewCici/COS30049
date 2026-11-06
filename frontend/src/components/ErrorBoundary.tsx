import { Button, Container, Stack, Typography } from '@mui/material';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Root error boundary: React requires a class component for this (no hook
 * equivalent exists). Catches any render-time error anywhere in the tree so
 * the user sees a plain-English fallback with a way back, never a blank
 * white screen (see docs/VIDEO_SCRIPT.md for the /?crash=1 dev-only demo
 * trigger in DetectorPage). */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('Unhandled render error:', error, info.componentStack);
  }

  handleReload = () => {
    this.setState({ error: null });
    window.location.assign('/');
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Stack spacing={2} role="alert">
          <Typography variant="h4" component="h1">
            Something went wrong
          </Typography>
          <Typography color="text.secondary">
            The page hit an unexpected error and could not continue. This has
            been logged; reloading usually resolves it.
          </Typography>
          <Button variant="contained" onClick={this.handleReload} sx={{ alignSelf: 'flex-start' }}>
            Reload
          </Button>
        </Stack>
      </Container>
    );
  }
}

import { AppBar, Box, Container, Link as MuiLink, Stack, Toolbar, Typography } from '@mui/material';
import ScienceOutlinedIcon from '@mui/icons-material/ScienceOutlined';
import { Link as RouterLink, NavLink, Outlet } from 'react-router-dom';

/** Shared header and page shell for every route, so navigation and branding
 * never drift between pages (Nielsen #4 — consistency). Includes a
 * skip-to-content link, visible only on keyboard focus, as the first
 * focusable element on every page (Part B.7). */
export default function Layout() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <MuiLink
        href="#main-content"
        sx={{
          position: 'absolute',
          left: 8,
          top: -48,
          zIndex: (t) => t.zIndex.tooltip + 1,
          px: 2,
          py: 1,
          bgcolor: 'background.paper',
          border: '2px solid',
          borderColor: 'primary.main',
          borderRadius: 1,
          transition: 'top 0.15s ease-in-out',
          '&:focus-visible': { top: 8 },
        }}
      >
        Skip to content
      </MuiLink>

      <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 3, flexWrap: 'wrap', py: 1 }}>
          <Stack
            component={RouterLink}
            to="/"
            direction="row"
            spacing={1}
            sx={{ alignItems: 'center', textDecoration: 'none', color: 'inherit' }}
          >
            <ScienceOutlinedIcon color="primary" fontSize="large" />
            <Typography variant="h6" component="span" sx={{ fontWeight: 700 }}>
              AI Content Detector
            </Typography>
          </Stack>
          <Box sx={{ flexGrow: 1 }} />
          <Stack component="nav" direction="row" spacing={1} aria-label="Primary">
            <NavLink to="/" end style={{ textDecoration: 'none', color: 'inherit' }}>
              {({ isActive }) => (
                <Typography
                  sx={{
                    px: 1.5, py: 1, borderRadius: 1, minHeight: 44, display: 'flex', alignItems: 'center',
                    fontWeight: isActive ? 700 : 400,
                    bgcolor: isActive ? 'action.selected' : 'transparent',
                  }}
                >
                  Detector
                </Typography>
              )}
            </NavLink>
            <NavLink to="/about" style={{ textDecoration: 'none', color: 'inherit' }}>
              {({ isActive }) => (
                <Typography
                  sx={{
                    px: 1.5, py: 1, borderRadius: 1, minHeight: 44, display: 'flex', alignItems: 'center',
                    fontWeight: isActive ? 700 : 400,
                    bgcolor: isActive ? 'action.selected' : 'transparent',
                  }}
                >
                  About
                </Typography>
              )}
            </NavLink>
          </Stack>
        </Toolbar>
      </AppBar>

      <Container component="main" id="main-content" maxWidth="lg" sx={{ py: 4, flexGrow: 1 }} tabIndex={-1}>
        <Outlet />
      </Container>
    </Box>
  );
}

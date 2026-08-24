import { Box, Paper, Stack, Typography } from '@mui/material';
import { BAND_STYLES } from '../bands';
import type { Band } from '../types';

const ORDER: Band[] = ['low', 'medium', 'high'];

/** Fixed legend: always rendered alongside results, never collapsed
 *  (Nielsen #6 — recognition over recall). Each colour swatch is paired
 *  with the band symbol, text label and numeric range (WCAG 1.4.1). */
export default function Legend() {
  return (
    <Paper variant="outlined" sx={{ p: 2 }} role="region" aria-label="Score legend">
      <Typography variant="subtitle2" component="h3" gutterBottom>
        Legend — sentence AI probability
      </Typography>
      <Stack spacing={1}>
        {ORDER.map((band) => {
          const s = BAND_STYLES[band];
          return (
            <Stack key={band} direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              <Box
                aria-hidden
                sx={{
                  width: 40, height: 22, flexShrink: 0, borderRadius: 0.5,
                  backgroundColor: s.background,
                  border: `1px solid ${s.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, color: '#1a1a1a',
                  textDecoration: s.textDecoration,
                  textDecorationColor: s.border,
                }}
              >
                {s.symbol}
              </Box>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {s.label}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {s.range}
                </Typography>
              </Box>
            </Stack>
          );
        })}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
        Hover or focus any sentence to see its exact score. Underline style
        also distinguishes bands, so colour is never the only cue.
      </Typography>
    </Paper>
  );
}

import { Box, FormControlLabel, Paper, Switch, Typography } from '@mui/material';
import { useId, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { BAND_STYLES } from '../bands';
import type { Meta, SentenceScore } from '../types';

interface Props {
  sentences: SentenceScore[];
  meta: Meta;
  activeIndex: number | null;
  onSelect: (index: number) => void;
  onHoverIndex: (index: number | null) => void;
}

interface Row {
  index: number;
  label: string;
  score: number;
  band: SentenceScore['band'];
  snippet: string;
}

/** "Which sentences drive this score?" — one bar per sentence. Clicking a
 * bar scrolls to and focuses that sentence in the highlighted passage
 * (Part B.5); hovering a sentence there highlights the matching bar via
 * `activeIndex`, passed back down from the page. A "high band only" filter
 * and a plain-text table alternative (always rendered, not only when
 * charts fail) satisfy the accessible-equivalent requirement without
 * relying on users being able to see or use the chart at all. */
export default function SentenceChart({ sentences, meta, activeIndex, onSelect, onHoverIndex }: Props) {
  const [highOnly, setHighOnly] = useState(false);
  const tableId = useId();

  const rows: Row[] = useMemo(
    () =>
      sentences.map((s, index) => ({
        index,
        label: `S${index + 1}`,
        score: s.score,
        band: s.band,
        snippet: s.text.length > 60 ? `${s.text.slice(0, 57)}…` : s.text,
      })),
    [sentences],
  );
  const visibleRows = highOnly ? rows.filter((r) => r.band === 'high') : rows;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Which sentences drive this score?
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        AI probability per sentence. Dashed lines mark the low/high band
        thresholds ({(meta.bands.low_below * 100).toFixed(0)}% /{' '}
        {(meta.bands.high_at_or_above * 100).toFixed(0)}%). Click a bar to
        jump to that sentence in the passage below; hovering a sentence
        there highlights its bar here.
      </Typography>

      <FormControlLabel
        control={<Switch checked={highOnly} onChange={(e) => setHighOnly(e.target.checked)} />}
        label="Show high-band sentences only"
        sx={{ mb: 1 }}
      />

      {visibleRows.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 2 }}>
          No sentences match this filter.
        </Typography>
      ) : (
        <Box
          sx={{ width: '100%', height: Math.max(160, visibleRows.length * 28) }}
          role="img"
          aria-describedby={tableId}
          aria-label="Bar chart of AI probability per sentence"
        >
          <ResponsiveContainer>
            <BarChart
              data={visibleRows}
              layout="vertical"
              margin={{ left: 8, right: 16, top: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                label={{ value: 'AI probability', position: 'insideBottom', offset: -4 }}
              />
              <YAxis type="category" dataKey="label" width={36} />
              <ReferenceLine x={meta.bands.low_below} stroke="#4c8c4a" strokeDasharray="4 4" />
              <ReferenceLine x={meta.bands.high_at_or_above} stroke="#c0392b" strokeDasharray="4 4" />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0].payload as Row;
                  return (
                    <Paper variant="outlined" sx={{ p: 1, maxWidth: 260 }}>
                      <Typography variant="body2">
                        {row.label}: {(row.score * 100).toFixed(0)}% AI probability
                      </Typography>
                      <Typography variant="caption" color="text.secondary">{row.snippet}</Typography>
                    </Paper>
                  );
                }}
              />
              <Bar
                dataKey="score"
                radius={[0, 3, 3, 0]}
                cursor="pointer"
                onClick={(data: unknown) => onSelect((data as { payload: Row }).payload.index)}
                onMouseEnter={(data: unknown) => onHoverIndex((data as { payload: Row }).payload.index)}
                onMouseLeave={() => onHoverIndex(null)}
              >
                {visibleRows.map((row) => (
                  <Cell
                    key={row.index}
                    fill={BAND_STYLES[row.band].border}
                    opacity={activeIndex === row.index ? 1 : 0.75}
                    stroke={activeIndex === row.index ? '#1a1a1a' : 'none'}
                    strokeWidth={activeIndex === row.index ? 2 : 0}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Accessible text/table equivalent of the chart above, always present. */}
      <Box id={tableId} component="details" sx={{ mt: 2 }}>
        <Typography component="summary" variant="body2" sx={{ cursor: 'pointer', fontWeight: 600 }}>
          Sentence scores as a table
        </Typography>
        <Box component="table" sx={{ width: '100%', mt: 1, borderCollapse: 'collapse' }}>
          <Box component="thead">
            <Box component="tr">
              <Box component="th" sx={{ textAlign: 'left', py: 0.5 }}>#</Box>
              <Box component="th" sx={{ textAlign: 'left', py: 0.5 }}>Sentence</Box>
              <Box component="th" sx={{ textAlign: 'right', py: 0.5 }}>AI probability</Box>
              <Box component="th" sx={{ textAlign: 'left', py: 0.5, pl: 1 }}>Band</Box>
            </Box>
          </Box>
          <Box component="tbody">
            {visibleRows.map((row) => (
              <Box
                component="tr"
                key={row.index}
                tabIndex={0}
                role="button"
                aria-label={`Jump to sentence ${row.index + 1} in the passage`}
                onClick={() => onSelect(row.index)}
                onKeyDown={(e: React.KeyboardEvent) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(row.index);
                  }
                }}
                sx={{
                  cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' },
                  '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 },
                }}
              >
                <Box component="td" sx={{ py: 0.5 }}>{row.index + 1}</Box>
                <Box component="td" sx={{ py: 0.5 }}>{row.snippet}</Box>
                <Box component="td" sx={{ py: 0.5, textAlign: 'right' }}>{(row.score * 100).toFixed(0)}%</Box>
                <Box component="td" sx={{ py: 0.5, pl: 1 }}>{BAND_STYLES[row.band].shortLabel}</Box>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Paper>
  );
}

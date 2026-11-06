import { Box, Button, Paper, Stack, Typography } from '@mui/material';
import { useId, useMemo } from 'react';
import {
  CartesianGrid, ErrorBar, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts';
import { VERDICT_STYLES } from '../bands';
import type { SessionCheck } from '../types';

interface Props {
  history: SessionCheck[];
  onReopen: (id: string) => void;
  onClear: () => void;
}

interface Row {
  id: string;
  index: number;
  score: number;
  ciError: [number, number];
  verdict: SessionCheck['result']['document']['verdict'];
  at: string;
  wordCount: number;
}

/** "How does this text compare with others checked this session?" — every
 * check made since the page loaded, as a point with a 95% CI error bar,
 * coloured by verdict. Clicking a point re-displays that check's full
 * result (Part B.5); history lives only in React state for this tab (see
 * sessionHistory.ts), so it is empty again on reload — that is deliberate,
 * not a bug: nothing here is persisted server-side. */
export default function SessionHistoryChart({ history, onReopen, onClear }: Props) {
  const tableId = useId();

  const rows: Row[] = useMemo(
    () =>
      history.map((check, index) => ({
        id: check.id,
        index: index + 1,
        score: check.result.document.score,
        ciError: [
          check.result.document.score - check.result.document.ci_low,
          check.result.document.ci_high - check.result.document.score,
        ],
        verdict: check.result.document.verdict,
        at: new Date(check.at).toLocaleTimeString(),
        wordCount: check.wordCount,
      })),
    [history],
  );

  if (history.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" component="h2" gutterBottom>
          Session history
        </Typography>
        <Typography color="text.secondary">
          No checks yet this session. Results appear here as you analyse text,
          so you can compare them.
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="h6" component="h2">
          How does this text compare with others checked this session?
        </Typography>
        <Button size="small" onClick={onClear}>
          Clear history
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Each point is one check this session, with its 95% confidence
        interval. Click a point to reopen that result.
      </Typography>

      <Box
        sx={{ width: '100%', height: 220 }}
        role="img"
        aria-describedby={tableId}
        aria-label="Scatter plot of document AI-probability scores across this session's checks"
      >
        <ResponsiveContainer>
          <ScatterChart margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="index"
              name="Check"
              domain={[0.5, Math.max(history.length, 1) + 0.5]}
              allowDecimals={false}
              label={{ value: 'Check number (this session)', position: 'insideBottom', offset: -4 }}
            />
            <YAxis
              type="number"
              dataKey="score"
              name="AI probability"
              domain={[0, 1]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as Row;
                return (
                  <Paper variant="outlined" sx={{ p: 1 }}>
                    <Typography variant="caption" sx={{ display: 'block' }}>{row.at}</Typography>
                    <Typography variant="body2">{(row.score * 100).toFixed(0)}% AI probability</Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>{VERDICT_STYLES[row.verdict].label}</Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>{row.wordCount} words</Typography>
                  </Paper>
                );
              }}
            />
            <Scatter
              data={rows}
              cursor="pointer"
              onClick={(point: unknown) => onReopen((point as Row).id)}
              fill="#3b5bdb"
            >
              {rows.map((row) => (
                <ErrorBar
                  key={row.id}
                  dataKey="ciError"
                  stroke={VERDICT_STYLES[row.verdict].color}
                  direction="y"
                  width={4}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </Box>

      <Box id={tableId} component="details" sx={{ mt: 2 }}>
        <Typography component="summary" variant="body2" sx={{ cursor: 'pointer', fontWeight: 600 }}>
          Session history as a table
        </Typography>
        <Box component="table" sx={{ width: '100%', mt: 1, borderCollapse: 'collapse' }}>
          <Box component="thead">
            <Box component="tr">
              <Box component="th" sx={{ textAlign: 'left', py: 0.5 }}>#</Box>
              <Box component="th" sx={{ textAlign: 'left', py: 0.5 }}>Time</Box>
              <Box component="th" sx={{ textAlign: 'right', py: 0.5 }}>Score</Box>
              <Box component="th" sx={{ textAlign: 'right', py: 0.5 }}>95% CI</Box>
              <Box component="th" sx={{ textAlign: 'left', py: 0.5, pl: 1 }}>Verdict</Box>
              <Box component="th" sx={{ textAlign: 'right', py: 0.5 }}>Words</Box>
            </Box>
          </Box>
          <Box component="tbody">
            {rows.map((row, i) => {
              const check = history[i];
              return (
                <Box
                  component="tr"
                  key={row.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`Reopen check ${row.index} from ${row.at}`}
                  onClick={() => onReopen(row.id)}
                  onKeyDown={(e: React.KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onReopen(row.id);
                    }
                  }}
                  sx={{
                    cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' },
                    '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 },
                  }}
                >
                  <Box component="td" sx={{ py: 0.5 }}>{row.index}</Box>
                  <Box component="td" sx={{ py: 0.5 }}>{row.at}</Box>
                  <Box component="td" sx={{ py: 0.5, textAlign: 'right' }}>{(row.score * 100).toFixed(0)}%</Box>
                  <Box component="td" sx={{ py: 0.5, textAlign: 'right' }}>
                    {(check.result.document.ci_low * 100).toFixed(0)}–{(check.result.document.ci_high * 100).toFixed(0)}%
                  </Box>
                  <Box component="td" sx={{ py: 0.5, pl: 1 }}>{VERDICT_STYLES[row.verdict].label}</Box>
                  <Box component="td" sx={{ py: 0.5, textAlign: 'right' }}>{row.wordCount}</Box>
                </Box>
              );
            })}
          </Box>
        </Box>
      </Box>
    </Paper>
  );
}

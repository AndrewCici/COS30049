import {
  Alert, Box, CircularProgress, Divider, Grid, Paper, Stack, Table, TableBody,
  TableCell, TableRow, Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { describeApiError, getModelInfo } from '../api';
import type { ModelInfoResponse } from '../types';

const FALLBACK_LIMITS = { min_text_chars: 20, max_text_chars: 12_000, max_sentences: 300 };

function MetricRow({ label, value }: { label: string; value: number | undefined }) {
  if (value === undefined) return null;
  return (
    <TableRow>
      <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>{label}</TableCell>
      <TableCell align="right" sx={{ border: 0, pr: 0 }}>{value.toFixed(4)}</TableCell>
    </TableRow>
  );
}

export default function AboutPage() {
  const [info, setInfo] = useState<ModelInfoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getModelInfo()
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch((err) => {
        if (!cancelled) setError(describeApiError(err).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const limits = info?.input_limits ?? FALLBACK_LIMITS;

  return (
    <Stack spacing={3} sx={{ py: 1 }}>
      <Box>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          About this tool
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 760 }}>
          This detector estimates how likely a passage of English text is to
          be AI-generated, sentence by sentence and as a whole document. It
          is a screening aid, not proof: no detector of this kind is reliable
          evidence of misconduct, and its output should never be the sole
          basis for accusing anyone of using AI to write their work.
        </Typography>
      </Box>

      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" component="h2" gutterBottom>
          How it works
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          Each sentence is scored by a classifier trained to distinguish
          human-written from AI-generated English text: TF-IDF word and
          character n-grams combined with stylometric and discourse features
          (sentence length variation, punctuation, hedging language, passive
          voice and more), fed into a logistic regression model. The
          document score is the word-count-weighted average of sentence
          scores, reported with a 95% confidence interval estimated by
          bootstrap resampling, plus a binary verdict at a 0.5 threshold.
        </Typography>
        <Typography variant="body2">
          This is the default and only detector in a standard deployment — it
          needs no network access and loads once when the server starts,
          behind an integrity check against its recorded file hash. A
          pretrained transformer model is available as an opt-in alternative
          on the server; it is not used unless explicitly enabled.
        </Typography>
      </Paper>

      {loading && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <CircularProgress size={20} />
          <Typography color="text.secondary">Loading model details…</Typography>
        </Stack>
      )}
      {error && (
        <Alert severity="warning">
          Could not load live model details from the server ({error}). Figures
          below are the values the front end falls back to.
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: '100%' }}>
            <Typography variant="h6" component="h2" gutterBottom>
              Model
            </Typography>
            <Table size="small" aria-label="Model identity">
              <TableBody>
                <TableRow>
                  <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>Name</TableCell>
                  <TableCell align="right" sx={{ border: 0, pr: 0 }}>{info?.model_name ?? '—'}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>Version</TableCell>
                  <TableCell align="right" sx={{ border: 0, pr: 0 }}>{info?.version ?? '—'}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {info?.dataset ?? 'Dataset summary unavailable.'}
            </Typography>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: '100%' }}>
            <Typography variant="h6" component="h2" gutterBottom>
              Input limits
            </Typography>
            <Table size="small" aria-label="Input limits">
              <TableBody>
                <TableRow>
                  <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>Minimum length</TableCell>
                  <TableCell align="right" sx={{ border: 0, pr: 0 }}>{limits.min_text_chars} characters</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>Maximum length</TableCell>
                  <TableCell align="right" sx={{ border: 0, pr: 0 }}>{limits.max_text_chars.toLocaleString()} characters</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th" scope="row" sx={{ border: 0, pl: 0 }}>Maximum sentences</TableCell>
                  <TableCell align="right" sx={{ border: 0, pr: 0 }}>{limits.max_sentences}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Paper>
        </Grid>

        {info && (
          <>
            <Grid size={{ xs: 12, md: 6 }}>
              <Paper variant="outlined" sx={{ p: 2.5, height: '100%' }}>
                <Typography variant="h6" component="h2" gutterBottom>
                  Sentence-level evaluation
                </Typography>
                <Table size="small" aria-label="Sentence-level evaluation metrics">
                  <TableBody>
                    <MetricRow label="Accuracy" value={info.metrics.accuracy} />
                    <MetricRow label="Precision (AI)" value={info.metrics.precision_ai} />
                    <MetricRow label="Recall (AI)" value={info.metrics.recall_ai} />
                    <MetricRow label="F1 (AI)" value={info.metrics.f1_ai} />
                    <MetricRow label="ROC AUC" value={info.metrics.roc_auc} />
                    <MetricRow label="False positive rate" value={info.metrics.false_positive_rate} />
                  </TableBody>
                </Table>
                <Typography variant="caption" color="text.secondary">
                  n = {info.metrics.n_test.toLocaleString()} held-out sentences.
                </Typography>
              </Paper>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <Paper variant="outlined" sx={{ p: 2.5, height: '100%' }}>
                <Typography variant="h6" component="h2" gutterBottom>
                  Essay-level evaluation
                </Typography>
                <Table size="small" aria-label="Essay-level evaluation metrics">
                  <TableBody>
                    <MetricRow label="Accuracy" value={info.essay_level_metrics.accuracy} />
                    <MetricRow label="F1 (AI)" value={info.essay_level_metrics.f1_ai} />
                    <MetricRow label="ROC AUC" value={info.essay_level_metrics.roc_auc} />
                    <MetricRow label="False positive rate" value={info.essay_level_metrics.false_positive_rate} />
                  </TableBody>
                </Table>
                {info.essay_level_metrics.n_test !== undefined && (
                  <Typography variant="caption" color="text.secondary">
                    n = {info.essay_level_metrics.n_test.toLocaleString()} held-out documents.
                  </Typography>
                )}
              </Paper>
            </Grid>
          </>
        )}
      </Grid>

      <Divider />

      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" component="h2" gutterBottom>
          Limitations
        </Typography>
        <Typography component="ul" variant="body2" sx={{ pl: 2, m: 0 }}>
          <li>No detector is reliable evidence of misconduct. Never use these scores alone to accuse anyone.</li>
          <li>English only; other languages give meaningless scores.</li>
          <li>Short texts (under ~3 sentences) are scored very unreliably.</li>
          <li>Human-edited AI text and AI-paraphrased human text often defeat detection.</li>
          <li>Text written by non-native speakers can be falsely flagged as AI-like.</li>
          <li>Deliberately disguised input (look-alike characters, invisible characters) can reduce accuracy; see the evasion report in <code>security/evasion/</code> for measured limits.</li>
        </Typography>
      </Paper>
    </Stack>
  );
}

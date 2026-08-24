import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button,
  Chip, CircularProgress, Container, Grid, Stack, TextField, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ScienceOutlinedIcon from '@mui/icons-material/ScienceOutlined';
import { useEffect, useMemo, useRef, useState } from 'react';
import { describeApiError, getHealth, scoreText } from './api';
import DocumentSummary from './components/DocumentSummary';
import HighlightedText from './components/HighlightedText';
import Legend from './components/Legend';
import type { ScoreResponse } from './types';

const MAX_CHARS = 50_000;
const SAMPLE_TEXT =
  "Artificial intelligence has fundamentally transformed numerous industries by enabling unprecedented levels of automation and efficiency. Moreover, it is important to note that these technologies continue to evolve at a remarkable pace. Honestly though, my first try at using one of these chatbots was a mess — it kept apologising for stuff it hadn't even done wrong. My cat walked across the keyboard and somehow the reply still made more sense than mine. In conclusion, the integration of AI into everyday workflows represents a significant paradigm shift that organisations must carefully navigate.";

export default function App() {
  const [text, setText] = useState('');
  const [analysedText, setAnalysedText] = useState('');
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverMethod, setServerMethod] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getHealth()
      .then((h) => setServerMethod(h.active_method))
      .catch(() => setServerMethod(null));
  }, []);

  const wordCount = useMemo(
    () => (text.trim() ? text.trim().split(/\s+/).length : 0),
    [text],
  );
  const canAnalyse = text.trim().length > 0 && text.length <= MAX_CHARS && !loading;
  // Nielsen #5 — prevent the error instead of reporting it: explain why the
  // button is disabled before the user hits it.
  const inputHint =
    text.length > MAX_CHARS
      ? `Text is too long (${text.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()} characters). Shorten it to analyse.`
      : `${wordCount.toLocaleString()} words · ${text.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()} characters` +
        (wordCount > 0 && wordCount < 30 ? ' — short texts give unreliable scores' : '');

  async function analyse() {
    if (!canAnalyse) return;
    setLoading(true);
    setError(null);
    try {
      const res = await scoreText(text);
      setResult(res);
      setAnalysedText(text);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  function clearAll() {
    setText('');
    setResult(null);
    setError(null);
    inputRef.current?.focus();
  }

  const staleResult = result !== null && text !== analysedText;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 0.5 }}>
        <ScienceOutlinedIcon color="primary" fontSize="large" />
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          AI Content Detector
        </Typography>
        {serverMethod && (
          <Chip size="small" variant="outlined" label={`model: ${serverMethod}`} />
        )}
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Paste an English passage to estimate, sentence by sentence, how likely
        it is to be AI-generated. Scores are estimates with uncertainty — not
        proof of authorship.
      </Typography>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Stack spacing={2}>
            <TextField
              inputRef={inputRef}
              multiline
              minRows={8}
              maxRows={16}
              fullWidth
              label="Text to analyse"
              placeholder="Paste your English text here (a paragraph or more works best)…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                // Shneiderman #2 — shortcut for frequent users.
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') analyse();
              }}
              error={text.length > MAX_CHARS}
              helperText={inputHint}
            />
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                size="large"
                onClick={analyse}
                disabled={!canAnalyse}
              >
                {loading ? 'Analysing…' : 'Analyse text'}
              </Button>
              <Button onClick={() => setText(SAMPLE_TEXT)} disabled={loading}>
                Use sample text
              </Button>
              <Button onClick={clearAll} disabled={loading || (!text && !result)}>
                Clear
              </Button>
              {loading && <CircularProgress size={22} aria-label="Analysing" />}
              <Box sx={{ flexGrow: 1 }} />
              <Typography variant="caption" color="text.secondary">
                Ctrl/⌘ + Enter to analyse
              </Typography>
            </Stack>

            {error && (
              <Alert severity="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            )}
            {staleResult && (
              <Alert severity="info">
                The text has changed since the last analysis — the results
                below refer to the previous text. Press “Analyse text” to
                refresh them.
              </Alert>
            )}
            {result?.meta.warnings.map((w, i) => (
              <Alert key={i} severity="warning">{w}</Alert>
            ))}

            {result && (
              <>
                <DocumentSummary document={result.document} meta={result.meta} />
                <HighlightedText
                  originalText={analysedText}
                  sentences={result.sentences}
                />
              </>
            )}
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Stack spacing={2}>
            <Legend />
            <Accordion variant="outlined" disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">How it works & limitations</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" sx={{ mb: 2 }}>
                  Each sentence is scored by a classifier trained to
                  distinguish human-written from AI-generated English text.
                  The document score is the average of sentence scores,
                  weighted by sentence length, and is reported with a 95%
                  confidence interval estimated by resampling.
                </Typography>
                <Typography variant="body2" sx={{ mb: 2 }}>
                  The primary model is a RoBERTa transformer fine-tuned on
                  human vs. ChatGPT answers (HC3). If it is unavailable, an
                  offline statistical model answers instead and a notice is
                  shown.
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                  Limitations
                </Typography>
                <Typography variant="body2" component="ul" sx={{ pl: 2, m: 0 }}>
                  <li>No detector is reliable evidence of misconduct. Never use these scores alone to accuse anyone.</li>
                  <li>English only; other languages give meaningless scores.</li>
                  <li>Short texts (under ~3 sentences) are scored very unreliably.</li>
                  <li>Human-edited AI text and AI-paraphrased human text often defeat detection.</li>
                  <li>Text written by non-native speakers can be falsely flagged as AI-like.</li>
                </Typography>
              </AccordionDetails>
            </Accordion>
          </Stack>
        </Grid>
      </Grid>
    </Container>
  );
}

import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button,
  Chip, CircularProgress, Grid, Skeleton, Stack, TextField, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { describeApiError, getHealth, getModelInfo, scoreText } from '../api';
import type { ApiErrorInfo } from '../api';
import HighlightedText from '../components/HighlightedText';
import Legend from '../components/Legend';
import SentenceChart from '../components/SentenceChart';
import SessionHistoryChart from '../components/SessionHistoryChart';
import VerdictCard from '../components/VerdictCard';
import { useSessionHistory } from '../sessionHistory';
import type { InputLimits, ScoreResponse } from '../types';

const FALLBACK_LIMITS: InputLimits = { min_text_chars: 20, max_text_chars: 12_000, max_sentences: 300 };

const SAMPLE_TEXT =
  "Artificial intelligence has fundamentally transformed numerous industries by enabling unprecedented levels of automation and efficiency. Moreover, it is important to note that these technologies continue to evolve at a remarkable pace. Honestly though, my first try at using one of these chatbots was a mess — it kept apologising for stuff it hadn't even done wrong. My cat walked across the keyboard and somehow the reply still made more sense than mine. In conclusion, the integration of AI into everyday workflows represents a significant paradigm shift that organisations must carefully navigate.";

interface FocusRequest {
  index: number;
  nonce: number;
}

/** Inline validation, checked on every keystroke and before submit; the
 * reason is shown directly under the field and the button is disabled
 * while it is non-null (Part B.3). Order matters: more specific problems
 * (empty, whitespace-only) are reported before the generic length check. */
function validate(text: string, limits: InputLimits): string | null {
  if (text.length === 0) return 'Enter some text to analyse.';
  if (text.trim().length === 0) return 'Text cannot be only whitespace.';
  if (text.length < limits.min_text_chars) {
    return `Text is too short: enter at least ${limits.min_text_chars} characters (currently ${text.length}).`;
  }
  if (text.length > limits.max_text_chars) {
    return `Text is too long: the limit is ${limits.max_text_chars.toLocaleString()} characters (currently ${text.length.toLocaleString()}).`;
  }
  return null;
}

export default function DetectorPage() {
  const [searchParams] = useSearchParams();
  // Dev-only demo trigger for the ErrorBoundary fallback (docs/VIDEO_SCRIPT.md);
  // inert in a production build, where import.meta.env.DEV is false.
  if (import.meta.env.DEV && searchParams.get('crash') === '1') {
    throw new Error('Development crash trigger (/?crash=1): demonstrates the root ErrorBoundary.');
  }

  const [text, setText] = useState('');
  const [analysedText, setAnalysedText] = useState('');
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorInfo, setErrorInfo] = useState<ApiErrorInfo | null>(null);
  const [serverMethod, setServerMethod] = useState<string | null>(null);
  const [limits, setLimits] = useState<InputLimits>(FALLBACK_LIMITS);
  const [liveMessage, setLiveMessage] = useState('');

  const [activeSentenceIndex, setActiveSentenceIndex] = useState<number | null>(null);
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const verdictRef = useRef<HTMLDivElement>(null);

  const { history, addCheck, clear: clearHistory } = useSessionHistory();

  useEffect(() => {
    getHealth()
      .then((h) => setServerMethod(h.active_method))
      .catch(() => setServerMethod(null));
    getModelInfo()
      .then((info) => setLimits(info.input_limits))
      .catch(() => setLimits(FALLBACK_LIMITS));
  }, []);

  // Move focus to the verdict card and announce it as soon as a result
  // (fresh or reopened from history) is available (Part B.4).
  // Moves focus to the verdict card whenever a result appears (fresh or
  // reopened from history) — a DOM side effect, which is what useEffect is
  // for; the aria-live announcement itself is set at the point the result
  // is produced (see announceResult below), not derived here, so this
  // effect never calls setState.
  useEffect(() => {
    if (!result) return;
    verdictRef.current?.focus();
  }, [result]);

  const validationMessage = useMemo(() => validate(text, limits), [text, limits]);
  const canAnalyse = validationMessage === null && !loading;
  const staleResult = result !== null && text !== analysedText;

  function announceResult(res: ScoreResponse) {
    const v = res.document.verdict === 'ai-generated' ? 'Likely AI-generated' : 'Likely human-made';
    setLiveMessage(`Analysis complete. ${v}, ${(res.document.confidence * 100).toFixed(0)}% confidence.`);
  }

  async function analyse() {
    if (!canAnalyse) return;
    setLoading(true);
    setErrorInfo(null);
    try {
      const res = await scoreText(text);
      setResult(res);
      setAnalysedText(text);
      addCheck(text, res);
      announceResult(res);
    } catch (err) {
      setErrorInfo(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  function clearAll() {
    setText('');
    setResult(null);
    setErrorInfo(null);
    setActiveSentenceIndex(null);
    setFocusRequest(null);
    inputRef.current?.focus();
  }

  function reopenCheck(id: string) {
    const entry = history.find((h) => h.id === id);
    if (!entry) return;
    setText(entry.text);
    setAnalysedText(entry.text);
    setResult(entry.result);
    setErrorInfo(null);
    setActiveSentenceIndex(null);
    setFocusRequest(null);
    announceResult(entry.result);
  }

  function handleChartSelect(index: number) {
    setActiveSentenceIndex(index);
    setFocusRequest({ index, nonce: Date.now() });
  }

  const wordCount = useMemo(
    () => (text.trim() ? text.trim().split(/\s+/).length : 0),
    [text],
  );

  return (
    <Stack spacing={1}>
      {/* Screen-reader-only live region: announces the verdict once, rather
          than relying on sighted users noticing the new card (Part B.4).
          Width/height are literal pixel strings, not the bare numbers MUI's
          sx prop would otherwise read as fractions of 100% -- that
          misreading previously left an invisible but viewport-width box
          behind, which was the actual cause of a phone-width horizontal
          scroll report (a MuiBox-root the size of the layout, clipped to
          nothing visually but still counted for scrollWidth). */}
      <Box role="status" aria-live="polite" sx={{
        position: 'absolute', width: '1px', height: '1px', overflow: 'hidden',
        clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap',
      }}>
        {liveMessage}
      </Box>

      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', flexWrap: 'wrap', mb: 1 }}>
        <Typography color="text.secondary">
          Paste an English passage to estimate, sentence by sentence, how
          likely it is to be AI-generated. Scores are estimates with
          uncertainty — not proof of authorship.
        </Typography>
        {serverMethod && (
          <Chip size="small" variant="outlined" label={`model: ${serverMethod}`} />
        )}
      </Stack>

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
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') analyse();
              }}
              error={validationMessage !== null && text.length > 0}
              helperText={
                validationMessage && text.length > 0
                  ? validationMessage
                  : `${wordCount.toLocaleString()} words · ${text.length.toLocaleString()} / ${limits.max_text_chars.toLocaleString()} characters` +
                    (wordCount > 0 && wordCount < 30 ? ' — short texts give unreliable scores' : '')
              }
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

            {errorInfo && <ErrorAlert info={errorInfo} onDismiss={() => setErrorInfo(null)} />}
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

            {loading && !result && (
              <Stack spacing={1}>
                <Skeleton variant="rounded" height={160} />
                <Skeleton variant="rounded" height={80} />
              </Stack>
            )}

            {result && (
              <>
                <VerdictCard ref={verdictRef} document={result.document} meta={result.meta} />
                <SentenceChart
                  sentences={result.sentences}
                  meta={result.meta}
                  activeIndex={activeSentenceIndex}
                  onSelect={handleChartSelect}
                  onHoverIndex={setActiveSentenceIndex}
                />
                <HighlightedText
                  originalText={analysedText}
                  sentences={result.sentences}
                  activeIndex={activeSentenceIndex}
                  onHoverIndex={setActiveSentenceIndex}
                  focusRequest={focusRequest}
                />
              </>
            )}

            <SessionHistoryChart history={history} onReopen={reopenCheck} onClear={clearHistory} />
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
                  By default, scoring uses a locally trained statistical
                  model (TF-IDF and stylometric features with a logistic
                  regression classifier), which needs no network access. A
                  pretrained RoBERTa transformer is available as an opt-in
                  alternative on the server; when it is enabled but
                  unavailable, the statistical model answers instead and a
                  notice is shown. See the <code>About</code> page for
                  measured accuracy figures.
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
    </Stack>
  );
}

function ErrorAlert({ info, onDismiss }: { info: ApiErrorInfo; onDismiss: () => void }) {
  const severity = info.kind === 'validation' ? 'warning' : 'error';
  return (
    <Alert severity={severity} onClose={onDismiss}>
      {info.message}
      {info.requestId && (
        <Typography variant="caption" sx={{ display: 'block' }} color="text.secondary">
          Reference: {info.requestId}
        </Typography>
      )}
    </Alert>
  );
}

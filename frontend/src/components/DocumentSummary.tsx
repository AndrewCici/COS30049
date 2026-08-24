import { Box, Chip, Paper, Stack, Tooltip, Typography } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { DOC_BAND_LABEL } from '../bands';
import type { DocumentScore, Meta } from '../types';

interface Props {
  document: DocumentScore;
  meta: Meta;
}

/** Document-level result: the length-weighted score is always shown as a
 *  range (95% CI) in both the visual bar and the text, never as a lone
 *  point estimate. */
export default function DocumentSummary({ document: doc, meta }: Props) {
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="subtitle2" component="h3">
            Overall document score
          </Typography>
          <Typography variant="h4" component="p" sx={{ fontWeight: 700, my: 0.5 }}>
            {pct(doc.score)}{' '}
            <Typography component="span" variant="h6" color="text.secondary">
              AI probability
            </Typography>
          </Typography>
          <Typography variant="body1" sx={{ fontWeight: 600 }}>
            {DOC_BAND_LABEL[doc.band]}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            95% confidence interval: {pct(doc.ci_low)} – {pct(doc.ci_high)}{' '}
            <Tooltip
              arrow
              title="The true document-level score plausibly lies anywhere in this range. It is estimated by resampling the sentence scores (bootstrap), weighted by sentence length. A wide interval means the result should not be trusted as precise."
            >
              <InfoOutlinedIcon
                fontSize="inherit"
                tabIndex={0}
                aria-label="What does the confidence interval mean?"
                sx={{ verticalAlign: 'text-bottom', cursor: 'help' }}
              />
            </Tooltip>
          </Typography>
        </Box>
        <Stack spacing={0.5} sx={{ alignItems: 'flex-end' }}>
          <Chip
            size="small"
            label={`Method: ${meta.fallback_used ? 'statistical fallback' : meta.method}`}
            color={meta.fallback_used ? 'warning' : 'default'}
            variant="outlined"
          />
          <Typography variant="caption" color="text.secondary">
            {doc.sentence_count} sentences · {doc.word_count} words
          </Typography>
        </Stack>
      </Stack>

      {/* Score bar: point estimate marker + CI band. Numbers above are the
          primary channel; this is a redundant visual aid (WCAG 1.4.1). */}
      <Box sx={{ mt: 2 }} aria-hidden>
        <Box sx={{ position: 'relative', height: 14, borderRadius: 7, bgcolor: '#e8e8e8', overflow: 'hidden' }}>
          <Box
            sx={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${doc.ci_low * 100}%`,
              width: `${Math.max((doc.ci_high - doc.ci_low) * 100, 1)}%`,
              bgcolor: 'rgba(96, 96, 96, 0.35)',
            }}
          />
          <Box
            sx={{
              position: 'absolute', top: -1, bottom: -1,
              left: `calc(${doc.score * 100}% - 2px)`,
              width: 4, bgcolor: '#1a1a1a', borderRadius: 1,
            }}
          />
        </Box>
        <Stack direction="row" sx={{ justifyContent: 'space-between', mt: 0.25 }}>
          <Typography variant="caption" color="text.secondary">0% — human</Typography>
          <Typography variant="caption" color="text.secondary">100% — AI</Typography>
        </Stack>
      </Box>
    </Paper>
  );
}

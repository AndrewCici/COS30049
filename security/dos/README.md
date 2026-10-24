# Denial of Service (Advanced)

**Goal:** one expensive request must not slow everyone else; a flood must be
rejected with 503 instead of freezing the server.

**Threat:** section 2.7's Denial of Service, applied to `POST /api/v1/score`
specifically, because it is the one endpoint that does real CPU work (TF-IDF
feature extraction, logistic-regression inference, a 2,000-sample bootstrap)
per request. `GET /api/v1/health` is a trivial async function and is kept
deliberately uninvolved in every defence below, so it can be used as a
witness: if it stays fast while `/score` is under attack, the service as a
whole hasn't gone down, even if one endpoint is degraded or shedding load.

**Running the scripts in this directory:** `backend/requirements.txt` (the
app itself) plus `backend/requirements-dev.txt` (`httpx`, used by the
attack scripts). `matplotlib` (`backend/requirements-train.txt`) is
optional — each script still runs and writes its CSV without it, just
skips the PNG plot.

## Measure first

`measure_cost.py` times each stage of `/score` (body parse+validate,
sentence split, model inference, weighted-mean + bootstrap CI) against
input size, well past the limits the app actually enforces, so the numbers
show the *uncapped* cost curve the defences below exist to cut off. Run it
yourself:

```bash
python security/dos/measure_cost.py
```

Measured on this machine (`security/dos/results/cost_by_chars.csv`,
`cost_by_sentences.csv`, `cost_by_chars.png`):

| Input | Sentences | Total time | Peak memory | Dominant stage |
|---|---|---|---|---|
| 12,000 chars (= MAX_TEXT_CHARS) | 101 | 130ms | 6.2MB | inference (124ms) |
| 25,000 chars | 211 | 269ms | 13.0MB | inference |
| 100,000 chars | 841 | 1,055ms | 51.7MB | inference |
| 250,000 chars | 2,101 | 2,624ms | 129.1MB | inference |
| 300 short sentences (= MAX_SENTENCES) | 300 | 87ms | 18.4MB | inference (77ms) |
| 2,400 short sentences | 2,400 | 690ms | 147.2MB | inference |

**Findings, honestly:**

- **A normal request is not free, but it is not the problem either.** At
  the limits the app actually enforces (12,000 chars / 300 sentences), one
  request costs ~90-130ms, almost all of it model inference. That's a real
  but manageable cost for *one* request.
- **Nothing here scales sub-linearly, let alone is bounded, once input
  size is uncapped.** Cost at 250,000 characters (2,101 sentences) is
  ~2.6 seconds and 129MB for a *single* request — comfortably inside what
  an undefended server would accept and fully process. This is exactly
  the gap the brief means by "what the undefended server accepts": the
  attack isn't a trick, it's just not stopping the input at the limit the
  product already claims to have.
- **Inference dominates, not the bootstrap CI.** ~1.2ms/sentence for
  inference across the whole range measured; the CI's cost scales the same
  way (fixed `n_boot=2000`) with a much smaller constant. So MAX_SENTENCES
  bounds the CI's cost as a side effect of bounding inference — no separate
  cap on `n_boot` was needed.
- **Parsing and validating the JSON body is cheap even at 250,000
  characters (<1ms).** So the case for a *body-size* limit (separate from
  the *character-count* limit Pydantic already enforces) isn't CPU — it's
  that an unbounded body is fully read into memory before Pydantic's
  `max_length` ever gets a chance to reject it, and that a byte count is
  checkable before any JSON decoding or app logic runs at all.
- **The real attack surface is concurrency and shape, not raw size.** A
  request can stay *inside* MAX_TEXT_CHARS (12,000 chars) while packing
  thousands of one-word "sentences" — normal-looking by the one limit a
  naive reader would check, expensive by the one that actually bounds the
  work (MAX_SENTENCES). And because CPython's GIL means concurrently
  running CPU-bound inference threads contend rather than run in parallel,
  many simultaneous *legitimate-sized* requests degrade every client's
  latency together rather than failing distinctly for some.

## Defences

All in `backend/app/security/`:

| Defence | File | What it bounds |
|---|---|---|
| Body-size limit | `body_limit.py` | Request body, rejected (413) as soon as it's provably too large — by `Content-Length` alone if declared, or by running total while streaming otherwise. Never reads past the limit, regardless of a missing/false `Content-Length` or chunked transfer. |
| Sentence-count cap | `app/main.py` (`score()`) | `MAX_SENTENCES` (300); rejected (422) right after splitting, before any inference runs. |
| Concurrency limiter | `limiter.py` | At most `MAX_CONCURRENT_INFERENCES` (2) inferences run at once; up to `MAX_QUEUED_INFERENCES` (8) more wait briefly (`QUEUE_TIMEOUT_S`, 2s) for a slot; beyond that capacity, or past the timeout, immediate 503 with `Retry-After`. |
| Off-loop inference + timeout backstop | `app/main.py` (`_run_inference`) | Inference runs via `anyio.to_thread.run_sync`, never on the event loop, so `/health` (a plain `async def`) is never stuck behind it. `INFERENCE_TIMEOUT_S` (10s) is a backstop that bounds how long a *caller* waits — not how long the worker thread runs, since Python cannot forcibly kill a thread; see the comment in `app/main.py` for why `abandon_on_cancel=True` still matters. |
| Regex safety | `app/sentences.py` | The sentence-boundary regex's punctuation quantifier is possessive and bounded (`{1,20}+`, not `+`); see `test_regex_safety.py` and the comment in `sentences.py` for the two quadratic-backtracking inputs this was measured to fix (340ms and 1.3s on 12,000 adversarial characters, down to under 4ms both). |

All of these except the regex fix (which has no "off" state — it's just
correct) are gated by `SECURITY_DEFENCES` (default on); see below.

### Demo toggle

```bash
SECURITY_DEFENCES=off uvicorn app.main:app --port 8000
```

Disables the body-size middleware, the sentence-count cap, and the
concurrency limiter. Logs a loud warning on startup. **Only for recording
"attack succeeds without defence" — never deploy this.**

## Attack scripts

Both need a running backend (`uvicorn app.main:app --port 8000`, see
reproduction commands below).

**`expensive_request.py`** — one request, two shapes, while polling
`/health` every 100ms:
- `sentence-flood`: `"Hi. " * 3000` — 12,000 characters (at the char limit)
  but 3,000 sentences (10x the sentence cap).
- `oversized-body`: `"word " * 4,000,000` — a 20MB body.

**`flood.py`** — N (default 200) concurrent `/score` requests, all a
realistic legitimate size (~12,000 chars, ~96 real sentences, the same
shape measured at ~130ms solo in `measure_cost.py`). Records every status
code and latency percentiles.

## Results

All results and raw data in `security/dos/results/`. Every number below
was produced by the commands in [Reproduction](#reproduction); none is
estimated.

### `expensive_request.py`

| Scenario | Defences | Result | Latency | `/health` while in flight |
|---|---|---|---|---|
| sentence-flood (12,000 chars, 3,000 sentences) | on | `422 TOO_MANY_SENTENCES` | 21.5ms | 1.9–4.6ms |
| sentence-flood | off | `200 OK` (fully processed) | 188.3ms | 2.1–72.6ms |
| oversized-body (20MB) | on | `413 PAYLOAD_TOO_LARGE`, body never read (see `test_body_size_limit.py`) | 81.6ms¹ | 1.8–4.5ms |
| oversized-body | off | `422 VALIDATION_ERROR` (body fully read & parsed first, *then* rejected by `MAX_TEXT_CHARS`) | 116.9ms¹ | 1.6–5.4ms |

¹ Most of this time is unavoidable client-side cost (serialising and
transmitting a 20MB request); on localhost the two conditions' wall-clock
times are close despite the structural difference (confirmed by
`test_body_size_limit.py::test_declared_content_length_too_large_rejected_without_reading`,
which asserts `receive()` is never called). The gap would widen on a real
network, where the server with the limit never has to receive the bytes at
all; the gap would also widen under *concurrent* oversized bodies, where
the "off" server holds multiple full 20MB strings in memory at once and
the "on" server holds none.

`/health` stayed fast and 200 in every case here because a single request,
even an expensive one, isn't enough to saturate a 2-worker-thread pool —
that's what `flood.py` is for.

### `flood.py` (N=200 concurrent, legitimate-sized requests)

| Defences | Status codes | Latency (all) p50/p95/p99 | Latency (200s only) p50/p95/p99 | Mean / max |
|---|---|---|---|---|
| on | 32× `200`, 168× `503` | 503 / 826 / 855ms | 737 / 855 / 862ms | 484 / 862ms |
| off | 200× `200` | 2,155 / 3,867 / 3,970ms | same | 2,150 / 3,972ms |

**Reading this honestly:** with the limiter, most clients (168/200) get an
immediate, cheap, actionable `503` with `Retry-After` instead of waiting;
the ones that do get served finish in under a second. Without it, *every*
client eventually succeeds — but waits over two seconds on average and
almost four seconds at the tail, for a request that costs ~130ms in
isolation. The limiter doesn't make the server handle more total work; it
decides *who* pays the cost of overload — a fast, explicit "no" to most
callers, rather than a slow "yes" to all of them.

## Reproduction

From the repository root, with `backend/requirements.txt` and
`backend/requirements-dev.txt` installed:

```bash
# Defended (default)
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
# in another terminal, from the repository root:
python security/dos/measure_cost.py
python security/dos/expensive_request.py --scenario sentence-flood --label defences_on
python security/dos/expensive_request.py --scenario oversized-body --label defences_on
python security/dos/flood.py -n 200 --label defences_on

# Undefended (demo only)
cd backend && SECURITY_DEFENCES=off ../.venv/bin/uvicorn app.main:app --port 8000
python security/dos/expensive_request.py --scenario sentence-flood --label defences_off
python security/dos/expensive_request.py --scenario oversized-body --label defences_off
python security/dos/flood.py -n 200 --label defences_off
```

Plain `curl` equivalents of the two `expensive_request.py` scenarios:

```bash
# sentence-flood: 422 TOO_MANY_SENTENCES when defended, 200 OK when not
curl -s -X POST http://localhost:8000/api/v1/score \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$(python3 -c "print('Hi. '*3000, end='')")\"}"

# oversized-body: 413 PAYLOAD_TOO_LARGE when defended, 422 when not
# (rejected either way -- the difference is whether the body was ever read)
python3 -c "import json; print(json.dumps({'text': 'word '*4_000_000}))" > /tmp/big_body.json
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/score \
  -H "Content-Type: application/json" --data-binary @/tmp/big_body.json

# /health during either attack (run in a separate terminal while the above runs)
watch -n 0.1 'curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://localhost:8000/api/v1/health'
```

Automated regression coverage (no live server needed):
`backend/tests/test_body_size_limit.py`,
`backend/tests/test_inference_limiter.py`,
`backend/tests/test_offload_and_timeout.py`,
`backend/tests/test_security_toggle.py`,
`backend/tests/test_regex_safety.py`.

## Cost of these defences

- **Legitimate users can receive 503 under genuine load.** The flood
  results above are the honest trade-off: capacity is
  `MAX_CONCURRENT_INFERENCES + MAX_QUEUED_INFERENCES` (10) in-flight
  requests at a time; the 11th simultaneous legitimate user gets a 503,
  not a slow success. This is deliberate (fail fast and let the client
  retry, per `Retry-After`) rather than accidental, but it is a real limit
  on peak throughput: roughly 2 requests ≈130ms apart ≈ 15 req/s sustained
  before queuing, lower under bursts.
- **The queue timeout (2s) is a trade-off, not a free parameter.** Shorter
  wastes less of a queued client's time before failing them; longer gives
  more queued requests a chance to be served during a brief spike at the
  cost of everyone in the queue waiting longer first. 2s was chosen as
  "longer than one solo request's worst normal-size latency (~130ms) by a
  wide margin, short enough that a human isn't left staring at a spinner."
- **The inference timeout (10s) cannot reclaim CPU, only the caller's
  wait.** A timed-out inference's worker thread keeps running (Python
  cannot forcibly kill a thread); `abandon_on_cancel=True` at least frees
  its concurrency slot immediately instead of holding it hostage, but the
  CPU cost is only avoided in the first place by MAX_SENTENCES bounding
  how expensive any single inference call can be.
- **Possessive/bounded regex quantifiers change behaviour only in cases
  that were already impossible to usefully match** (see the comment in
  `app/sentences.py` for the proof); `test_sentences.py`'s full pre-existing
  suite still passes unchanged, so this cost is effectively zero.

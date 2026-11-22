# End-to-end recording tests

These tests are opt-in because they visit live adult streaming sites and
download a short sample. A normal `pytest` run collects them but skips them.

Each test:

1. discovers a currently live model for its site,
2. creates the real bot and confirms its status is `PUBLIC`,
3. asks the bot for its recording URL and records for a few seconds,
4. stops the downloader through `stopDownload()`,
5. verifies the recorded file with `ffprobe` (one video stream and one audio
   stream) and decodes a few frames from each stream with `ffmpeg`.

## Requirements

`ffmpeg` and `ffprobe` must be installed. If they are not on `PATH`, point
`STRMNTR_FFMPEG_PATH` at `ffmpeg`; the sibling `ffprobe` is found
automatically, or set `STRMNTR_FFPROBE_PATH` explicitly.

ManyVids recordings use the Python Agora WebRTC worker.  Install the normal
requirements (or run the tests inside the Docker image); the ManyVids test
skips with a clear reason when `aiortc`, `av`, `numpy` or `websockets` is
missing.

Install the application and test dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

## Run

```bash
STRMNTR_E2E=1 .venv/bin/pytest tests/e2e -v
```

Useful environment variables:

- `STRMNTR_E2E_SITES` – comma-separated site slugs to run, for example
  `CB,SC,SCVR`.
- `STRMNTR_E2E_RECORD_SECONDS` – recording duration per site (default `20`,
  minimum `5`).
- `STRMNTR_E2E_MODEL_<SLUG>` – pin a model instead of discovering one, for
  example `STRMNTR_E2E_MODEL_CB=some_model`.
- `STRMNTR_E2E_ROOM_ID_<SLUG>` – optional room ID for sites such as `FL`
  (Fansly) and `SC` (StripChat) when pinning a model.
- `STRMNTR_FFMPEG_PATH` / `STRMNTR_FFPROBE_PATH` – binary locations.

Examples:

```bash
STRMNTR_E2E=1 STRMNTR_E2E_SITES=SC STRMNTR_E2E_RECORD_SECONDS=15 \
  .venv/bin/pytest tests/e2e -v

STRMNTR_E2E=1 STRMNTR_E2E_MODEL_FL=some_model \
  STRMNTR_E2E_ROOM_ID_FL=123456789012345678 \
  .venv/bin/pytest tests/e2e -k FL -v
```

## Discovery coverage

Live-model discovery is implemented for AmateurTV, BongaCams, Cam4, Cams.com,
CamSoda, Chaturbate, DreamCam, DreamCam VR, FanslyLive, ManyVids, MyFreeCams,
StreaMate, StripChat, and StripChat VR.

Flirt4Free, SexChat.hu, and XLoveCam do not have discovery helpers
(officially unsupported, or their public directories are not usable from this
test harness). They are skipped with a reason unless a model is pinned through
`STRMNTR_E2E_MODEL_<SLUG>`.

A site is also skipped when it is unreachable, when its discovery endpoint
returns no live candidates, or when no candidate reports `PUBLIC` during the
test run. Recording or media-verification failures are test failures.

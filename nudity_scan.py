#!/usr/bin/env python3
"""Scan a video collection for nudity and prune videos that contain none.

Detection is done with NudeNet (ONNX), which reports separate classes for
exposed body parts and covered ones, so underwear-only footage is NOT
counted as nudity.

Workflow (per folder):
  1. Every video is sampled at a fixed interval (default 2s) using only
     keyframes for fast decoding, and frames go through the detector.
  2. Results are written to a `<video>.nudity.json` sidecar (used as a cache
     on re-runs) and a heatmap PNG the StreaMonitor web player displays.
     Heatmap colors: red = breasts, pink = pussy, blue = dick,
     orange = ass/anus, yellow = covered/underwear. Old (v2) sidecars only
     stored a single aggregated score, so their heatmaps stay all-red until
     the video is rescanned with --upgrade-sidecars; --redraw-heatmaps
     re-renders every PNG from the sidecar JSON without rescanning.
  3. Only after the whole folder is scanned, non-nude videos are deleted --
     except a deterministic ~10% random sample that is kept.

A folder containing a `.keep` or `.nodelete` file is protected: its videos
(and those of its subfolders) are scanned but never deleted.

Nothing is deleted unless --delete is passed; the default is a dry run that
prints and logs what would happen.

Requires: pip install nudenet   (pulls in onnxruntime + opencv + numpy)

Examples:
    python nudity_scan.py downloads                 # dry run, full report
    python nudity_scan.py downloads --delete        # actually delete
    python nudity_scan.py downloads --heatmaps-only # never delete anything
    python nudity_scan.py downloads --heatmaps-only --redraw-heatmaps
                                                    # re-render PNGs after a color change
    python nudity_scan.py downloads --heatmaps-only --upgrade-sidecars
                                                    # rescan old sidecars for per-part colors
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import queue as queue_module
import shutil
import subprocess
import sys
import time

VIDEO_EXTENSIONS = ('mp4', 'mkv', 'webm', 'mov', 'avi', 'wmv')
SIDECAR_SUFFIX = '.nudity.json'
SIDECAR_VERSION = 3
# v2 sidecars store one aggregated nude score per sample; v3 stores one score
# per category below. v2 stays a valid cache (heatmaps keep the old 2-color
# look) until the video is rescanned with --upgrade-sidecars.
COMPATIBLE_SIDECAR_VERSIONS = (2, 3)
MODEL_SIZE = 320  # NudeNet 320n input resolution

# Nudity categories: (key, NudeNet classes, heatmap BGR color). *_COVERED
# classes (underwear, lingerie) intentionally count as non-nude.
# A sidecar sample row is [time, <one score per category>, covered_score].
NUDE_CATEGORIES = (
    ('breast', {'FEMALE_BREAST_EXPOSED'}, (48, 48, 235)),                  # red
    ('pussy', {'FEMALE_GENITALIA_EXPOSED'}, (180, 105, 255)),              # pink
    ('dick', {'MALE_GENITALIA_EXPOSED'}, (235, 130, 48)),                  # blue
    ('ass', {'ANUS_EXPOSED', 'BUTTOCKS_EXPOSED'}, (48, 165, 255)),         # orange
)
LEGACY_NUDE_COLOR = (48, 48, 235)   # v2 sidecars: any nudity, red
COVERED_COLOR = (16, 200, 235)      # underwear/covered, yellow
COVERED_CLASSES = {
    'FEMALE_BREAST_COVERED',
    'FEMALE_GENITALIA_COVERED',
    'ANUS_COVERED',
    'BUTTOCKS_COVERED',
}

try:
    from parameters import FFMPEG_PATH
except Exception:
    FFMPEG_PATH = 'ffmpeg'
FFPROBE_PATH = os.path.join(os.path.dirname(FFMPEG_PATH), 'ffprobe') if os.sep in FFMPEG_PATH else 'ffprobe'

try:
    from streamonitor.thumbnail import THUMBNAILS_DIR
except Exception:
    THUMBNAILS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.thumbnails')

_detector = None
_detector_takes_ndarray = True


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _get_detector():
    global _detector
    if _detector is None:
        from nudenet import NudeDetector
        _detector = NudeDetector()
    return _detector


def _detect_frame(frame):
    """Run NudeNet on one BGR ndarray.

    Returns [<max score per NUDE_CATEGORIES entry>, covered_score]."""
    global _detector_takes_ndarray
    detector = _get_detector()
    if _detector_takes_ndarray:
        try:
            detections = detector.detect(frame)
        except Exception:
            _detector_takes_ndarray = False
            detections = None
    if not _detector_takes_ndarray:
        # Older nudenet versions only accept file paths
        import cv2
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            cv2.imwrite(tmp_path, frame)
            detections = detector.detect(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    scores = [float(max((d['score'] for d in detections if d['class'] in classes), default=0.0))
              for _key, classes, _color in NUDE_CATEGORIES]
    scores.append(float(max((d['score'] for d in detections if d['class'] in COVERED_CLASSES), default=0.0)))
    return scores


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def probe_duration(path):
    try:
        out = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', path],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip())
    except Exception:
        return None


def iter_frames(path, interval, keyframes_only=True):
    """Yield BGR ndarrays sampled every `interval` seconds.

    With keyframes_only, non-key packets are dropped before decoding which is
    an order of magnitude faster; HLS recordings have keyframes every few
    seconds so temporal accuracy stays close to `interval`.
    """
    import numpy as np
    vf = (f'fps=1/{interval},'
          f'scale={MODEL_SIZE}:{MODEL_SIZE}:force_original_aspect_ratio=decrease:flags=area,'
          f'pad={MODEL_SIZE}:{MODEL_SIZE}:(ow-iw)/2:(oh-ih)/2')
    cmd = [FFMPEG_PATH, '-nostdin', '-hide_banner', '-loglevel', 'error']
    if keyframes_only:
        cmd += ['-discard', 'nokey']
    cmd += ['-i', path, '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1']

    frame_bytes = MODEL_SIZE * MODEL_SIZE * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(MODEL_SIZE, MODEL_SIZE, 3)
    finally:
        proc.stdout.close()
        proc.wait()


# ---------------------------------------------------------------------------
# Per-file scan
# ---------------------------------------------------------------------------

def sidecar_path(video_path):
    return video_path + SIDECAR_SUFFIX


def heatmap_path(video_path):
    """Heatmap PNG lives next to the video, like the JSON sidecar."""
    return video_path + '.heatmap.png'


def thumbnail_jpg_path(video_path):
    name_hash = hashlib.md5(os.path.basename(video_path).encode()).hexdigest()
    return os.path.join(THUMBNAILS_DIR, f'{name_hash}.jpg')


def load_cached(video_path, versions=COMPATIBLE_SIDECAR_VERSIONS):
    try:
        with open(sidecar_path(video_path)) as f:
            data = json.load(f)
        stat = os.stat(video_path)
        if (data.get('version') in versions
                and data.get('filesize') == stat.st_size
                and abs(data.get('mtime', 0) - stat.st_mtime) < 2):
            return data
    except (OSError, ValueError):
        pass
    return None


def scan_video(video_path, interval, dedupe_threshold=2.0, progress=None):
    """Sample and classify one video. Returns the sidecar dict (not written).

    `progress` is an optional callable(frames_done, frames_expected).
    """
    import cv2

    duration = probe_duration(video_path)
    expected_frames = int(duration / interval) + 1 if duration else 0
    if progress:
        progress(0, expected_frames)
    samples = []
    prev_frame = None
    prev_scores = [0.0] * (len(NUDE_CATEGORIES) + 1)
    inferences = 0
    frames = 0
    start = time.monotonic()

    for use_keyframes in (True, False):
        for frame in iter_frames(video_path, interval, keyframes_only=use_keyframes):
            # Static scenes and duplicated keyframes: reuse the last scores
            if prev_frame is not None and float(cv2.absdiff(frame, prev_frame).mean()) < dedupe_threshold:
                scores = prev_scores
            else:
                scores = _detect_frame(frame)
                inferences += 1
            prev_frame = frame
            prev_scores = scores
            samples.append([round(frames * interval, 2)] + [round(s, 3) for s in scores])
            frames += 1
            if progress:
                progress(frames, expected_frames)
        if frames > 0:
            break
        # -discard nokey produced nothing (unusual container) -> full decode

    stat = os.stat(video_path)
    return {
        'version': SIDECAR_VERSION,
        'file': os.path.basename(video_path),
        'filesize': stat.st_size,
        'mtime': stat.st_mtime,
        'duration': duration if duration else (frames * interval),
        'interval': interval,
        'samples': samples,
        'frames': frames,
        'inferences': inferences,
        'scan_seconds': round(time.monotonic() - start, 1),
        'error': None if frames > 0 else 'no frames decoded',
    }


def decide(data, nude_threshold, strong_threshold, min_nude_seconds):
    """Return (is_nude, max_score, nude_seconds) from sidecar sample data.

    Sample rows are [time, <nude score(s)>, covered]; v2 has one aggregated
    nude column, v3 one per NUDE_CATEGORIES entry. Both handled here."""
    interval = data.get('interval', 2.0)
    scores = [max(s[1:-1]) for s in data.get('samples', [])]
    max_score = max(scores, default=0.0)
    nude_seconds = sum(interval for s in scores if s >= nude_threshold)
    is_nude = nude_seconds >= min_nude_seconds or max_score >= strong_threshold
    return is_nude, max_score, nude_seconds


# ---------------------------------------------------------------------------
# Heatmap rendering (PNG strip, funscript/Stash style, served by the web UI)
# ---------------------------------------------------------------------------

def render_heatmap(data, out_path, width=1000, height=40):
    """Bar height is the score; per-category colors from NUDE_CATEGORIES.

    Where several categories fire at once, the taller bar is drawn first and
    shorter ones over its base, so each visible segment is the category whose
    score reaches that height. v2 sidecars have a single aggregated nude
    column and render in the legacy red."""
    import numpy as np
    import cv2

    img = np.full((height, width, 3), 24, dtype=np.uint8)  # dark background
    samples = data.get('samples') or []
    duration = data.get('duration') or 0
    if samples and duration > 0:
        arr = np.array(samples, dtype=np.float32)
        times = arr[:, 0]
        nude = arr[:, 1:-1]
        cov = arr[:, -1]
        if nude.shape[1] == len(NUDE_CATEGORIES):
            colors = [color for _key, _classes, color in NUDE_CATEGORIES]
        else:
            colors = [LEGACY_NUDE_COLOR] * nude.shape[1]
        col_t = (np.arange(width, dtype=np.float32) + 0.5) * (duration / width)
        idx = np.searchsorted(times, col_t).clip(0, len(samples) - 1)
        for x in range(width):
            i = idx[x]
            c = cov[i]
            if c > 0.2:  # underwear/covered: yellow bar
                img[height - max(1, int(c * height)):, x] = COVERED_COLOR
            bars = sorted(
                ((float(nude[i, k]), colors[k]) for k in range(nude.shape[1]) if nude[i, k] > 0.2),
                key=lambda b: b[0], reverse=True)
            for score, color in bars:  # nudity drawn on top of covered
                img[height - max(1, int(score * height)):, x] = color
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)


# ---------------------------------------------------------------------------
# Worker process
# ---------------------------------------------------------------------------

def is_open_for_writing(path):
    """True if any visible local process has `path` open with write access.

    Read-only opens (e.g. the web player streaming the file) don't count.
    Uses /proc, so it only sees processes of the same user (which is where
    the StreaMonitor recorder runs anyway); returns False on non-Linux.
    """
    real = os.path.realpath(path)
    if not os.path.isdir('/proc'):
        return False
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        fd_dir = os.path.join('/proc', pid, 'fd')
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                if os.readlink(os.path.join(fd_dir, fd)) != real:
                    continue
                with open(os.path.join('/proc', pid, 'fdinfo', fd)) as f:
                    for line in f:
                        if line.startswith('flags:'):
                            access_mode = int(line.split()[1], 8) & 0o3
                            if access_mode in (os.O_WRONLY, os.O_RDWR):
                                return True
                            break
            except OSError:
                continue
    return False


_progress_queue = None


def _worker_init(threads, progress_queue=None):
    global _progress_queue
    _progress_queue = progress_queue
    os.environ.setdefault('OMP_NUM_THREADS', str(threads))
    os.environ.setdefault('ORT_NUM_THREADS', str(threads))


def _report_progress(video_path):
    """Progress callable that forwards to the parent, throttled to ~4 Hz."""
    last_sent = [0.0]

    def progress(done, total):
        if _progress_queue is None:
            return
        now = time.monotonic()
        if done == 0 or done == total or now - last_sent[0] >= 0.25:
            last_sent[0] = now
            try:
                _progress_queue.put_nowait((video_path, done, total))
            except Exception:
                pass
    return progress


def _worker_scan(args):
    """Returns (video_path, data, error, skipped_reason)."""
    video_path, interval, upgrade, redraw = args
    try:
        # With --upgrade-sidecars only the current version counts as cached,
        # so older sidecars get rescanned with per-category scores.
        versions = (SIDECAR_VERSION,) if upgrade else COMPATIBLE_SIDECAR_VERSIONS
        cached = load_cached(video_path, versions)
        if cached is not None:
            data = cached
            data['from_cache'] = True
        else:
            if is_open_for_writing(video_path):
                return video_path, None, None, 'open for writing, still downloading?'
            data = scan_video(video_path, interval, progress=_report_progress(video_path))
            data['from_cache'] = False
            with open(sidecar_path(video_path), 'w') as f:
                json.dump(data, f)
        hm = heatmap_path(video_path)
        if redraw or not data.get('from_cache') or not os.path.exists(hm):
            render_heatmap(data, hm)
        return video_path, data, None, None
    except Exception as e:
        return video_path, None, repr(e), None


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

class ProgressDisplay:
    """Overall + per-file progress bars pinned to the bottom of the terminal.

    Log lines are printed above the bars via log(). Falls back to plain
    printing when stdout is not a TTY (e.g. piped to a file).
    """

    def __init__(self, total_files):
        self.total_files = total_files
        self.done_files = 0
        self.active = {}  # video_path -> (frames_done, frames_expected)
        self._lines = 0
        self.enabled = sys.stdout.isatty() or bool(os.environ.get('FORCE_PROGRESS'))

    @staticmethod
    def _bar(frac, width=28):
        frac = min(max(frac, 0.0), 1.0)
        filled = int(round(frac * width))
        return '[' + '#' * filled + '-' * (width - filled) + ']'

    def _erase(self):
        if self._lines:
            sys.stdout.write(f'\x1b[{self._lines}F\x1b[J')
            self._lines = 0

    def log(self, msg):
        self._erase()
        print(msg, flush=True)
        self.render()

    def file_progress(self, path, done, expected):
        self.active[path] = (done, expected)

    def file_done(self, path):
        self.active.pop(path, None)
        self.done_files += 1

    def render(self):
        if not self.enabled:
            return
        self._erase()
        cols = shutil.get_terminal_size().columns
        # Overall bar gets fractional credit for files currently in flight
        in_flight = sum(min(d / e, 1.0) for d, e in self.active.values() if e)
        frac = (self.done_files + in_flight) / self.total_files if self.total_files else 1.0
        lines = [f'Overall {self._bar(frac)} {self.done_files}/{self.total_files} files ({frac:.0%})']
        for path, (done, expected) in sorted(self.active.items()):
            name = os.path.basename(path)
            if expected:
                line = f'  {self._bar(done / expected, 20)} {done:>4}/{expected} frames  {name}'
            else:
                line = f'  {self._bar(0, 20)} {done:>4} frames       {name}'
            lines.append(line[:cols - 1])
        sys.stdout.write('\n'.join(lines) + '\n')
        sys.stdout.flush()
        self._lines = len(lines)

    def close(self):
        self._erase()
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Collection walk / deletion
# ---------------------------------------------------------------------------

KEEP_MARKERS = ('.keep', '.nodelete')


def find_keep_marker(folder, root):
    """Return the path of a .keep/.nodelete file protecting `folder`, looking
    in the folder itself and every parent up to (and including) `root`."""
    folder = os.path.abspath(folder)
    root = os.path.abspath(root)
    while True:
        for marker in KEEP_MARKERS:
            path = os.path.join(folder, marker)
            if os.path.exists(path):
                return path
        if folder == root:
            return None
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def keep_lottery(video_path, keep_fraction):
    """Deterministic pseudo-random keep decision, stable across re-runs so a
    dry run shows exactly what a later --delete run will do."""
    digest = hashlib.md5(('keep-lottery:' + os.path.basename(video_path)).encode()).hexdigest()
    return (int(digest[:8], 16) / 0xFFFFFFFF) < keep_fraction


def collect_folders(root, min_age_minutes):
    """Map folder -> list of video files, skipping files that are too new
    (possibly still being recorded)."""
    folders = {}
    cutoff = time.time() - min_age_minutes * 60
    for dirpath, _dirnames, filenames in os.walk(root):
        videos = []
        for name in sorted(filenames):
            if not name.lower().endswith(tuple('.' + e for e in VIDEO_EXTENSIONS)):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.stat(path).st_mtime > cutoff:
                    print(f'  skipping (modified recently, maybe recording): {path}')
                    continue
            except OSError:
                continue
            videos.append(path)
        if videos:
            folders[dirpath] = videos
    return folders


def delete_video_and_sidecars(video_path):
    for path in (
        video_path,
        sidecar_path(video_path),
        heatmap_path(video_path),
        thumbnail_jpg_path(video_path),
    ):
        try:
            os.remove(path)
        except OSError:
            pass


def human_size(n):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if n < 1024 or unit == 'TiB':
            return f'{n:.1f} {unit}'
        n /= 1024


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('root', nargs='?', default='downloads',
                        help='collection root; each subfolder is scanned then pruned (default: downloads)')
    parser.add_argument('--delete', action='store_true',
                        help='actually delete files (default is a dry run)')
    parser.add_argument('--trash-dir', default=None,
                        help='move deleted files here instead of removing them')
    parser.add_argument('--heatmaps-only', action='store_true',
                        help='only scan and generate heatmaps, never delete')
    parser.add_argument('--interval', type=float, default=2.0,
                        help='seconds between sampled frames (default 2.0)')
    parser.add_argument('--nude-threshold', type=float, default=0.5,
                        help='per-frame score needed to count as nude (default 0.5)')
    parser.add_argument('--strong-threshold', type=float, default=0.7,
                        help='a single frame above this keeps the file, catching very brief nudity (default 0.7)')
    parser.add_argument('--min-nude-seconds', type=float, default=3.0,
                        help='total nude time to keep a file (default 3.0)')
    parser.add_argument('--keep-fraction', type=float, default=0.10,
                        help='fraction of non-nude videos to keep anyway (default 0.10)')
    parser.add_argument('--min-age-minutes', type=float, default=30,
                        help='skip files modified more recently than this (default 30)')
    parser.add_argument('--redraw-heatmaps', action='store_true',
                        help='re-render every heatmap PNG from the cached sidecar JSON (no rescan); '
                             'use after changing the color scheme')
    parser.add_argument('--upgrade-sidecars', action='store_true',
                        help='rescan videos whose sidecar is an older version to get '
                             'per-category scores (and the colored heatmap)')
    parser.add_argument('--workers', type=int,
                        default=max(1, (os.cpu_count() or 2) // 2),
                        help='parallel scanner processes')
    parser.add_argument('--report', default='nudity_scan_report.jsonl',
                        help='JSONL report of every decision (default nudity_scan_report.jsonl)')
    args = parser.parse_args()

    try:
        import nudenet  # noqa: F401
    except ImportError:
        sys.exit('nudenet is not installed. Run:  pip install nudenet')

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f'Not a directory: {root}')

    folders = collect_folders(root, args.min_age_minutes)
    total_files = sum(len(v) for v in folders.values())
    print(f'Found {total_files} videos in {len(folders)} folders under {root}')
    if args.delete and not args.heatmaps_only:
        print('DELETION IS ENABLED - non-nude videos will be removed at the end of each folder.')
    else:
        print('Dry run: no files will be deleted (pass --delete to prune).')

    report = open(args.report, 'a')
    threads_per_worker = max(1, (os.cpu_count() or 2) // args.workers)
    manager = multiprocessing.Manager()
    progress_queue = manager.Queue()
    pool = multiprocessing.Pool(args.workers, initializer=_worker_init,
                                initargs=(threads_per_worker, progress_queue))
    display = ProgressDisplay(total_files)

    totals = {'nude': 0, 'clean_kept': 0, 'protected': 0, 'deleted': 0, 'errors': 0, 'freed': 0, 'skipped': 0}
    done = 0
    try:
        for folder, videos in sorted(folders.items()):
            display.log(f'\n=== {folder} ({len(videos)} videos) ===')
            pending = {v: pool.apply_async(
                _worker_scan, ((v, args.interval, args.upgrade_sidecars, args.redraw_heatmaps),))
                       for v in videos}
            decisions = []  # (path, verdict, data)
            while pending:
                try:
                    while True:
                        path, frames_done, frames_expected = progress_queue.get_nowait()
                        display.file_progress(path, frames_done, frames_expected)
                except queue_module.Empty:
                    pass
                finished = [p for p, r in pending.items() if r.ready()]
                for p in finished:
                    video_path, data, error, skipped = pending.pop(p).get()
                    display.file_done(video_path)  # also advances the overall bar
                    done += 1
                    name = os.path.basename(video_path)
                    if skipped:
                        totals['skipped'] += 1
                        display.log(f'[{done}/{total_files}] {name}: skipped ({skipped})')
                        continue  # not in decisions -> never deleted
                    if error or data.get('error'):
                        totals['errors'] += 1
                        display.log(f'[{done}/{total_files}] {name}: ERROR {error or data["error"]} (kept)')
                        decisions.append((video_path, 'error', data))
                        continue
                    is_nude, max_score, nude_seconds = decide(
                        data, args.nude_threshold, args.strong_threshold, args.min_nude_seconds)
                    verdict = 'nude' if is_nude else 'clean'
                    cache_note = ' (cached)' if data.get('from_cache') else f' [{data["scan_seconds"]}s, {data["inferences"]}/{data["frames"]} inferred]'
                    display.log(f'[{done}/{total_files}] {name}: {verdict} '
                                f'(max {max_score:.2f}, {nude_seconds:.0f}s nude){cache_note}')
                    decisions.append((video_path, verdict, data))
                display.render()
                if pending and not finished:
                    time.sleep(0.15)

            # Folder fully scanned -> now prune
            keep_marker = find_keep_marker(folder, root)
            if keep_marker and any(v == 'clean' for _, v, _ in decisions):
                display.log(f'  folder protected by {keep_marker}, keeping all videos')
            for video_path, verdict, data in decisions:
                entry = {
                    'time': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'file': video_path,
                    'verdict': verdict,
                    'action': 'kept',
                }
                if verdict == 'nude' or verdict == 'error':
                    totals['nude'] += verdict == 'nude'
                elif keep_marker:
                    totals['protected'] += 1
                    entry['action'] = 'kept-protected'
                elif keep_lottery(video_path, args.keep_fraction):
                    totals['clean_kept'] += 1
                    entry['action'] = 'kept-lottery'
                    display.log(f'  keeping (random {args.keep_fraction:.0%} sample): {os.path.basename(video_path)}')
                elif args.heatmaps_only or not args.delete:
                    entry['action'] = 'would-delete'
                    totals['deleted'] += 1
                    totals['freed'] += data.get('filesize', 0) if data else 0
                    display.log(f'  would delete: {os.path.basename(video_path)}')
                else:
                    size = data.get('filesize', 0) if data else 0
                    if args.trash_dir:
                        os.makedirs(args.trash_dir, exist_ok=True)
                        for path in (video_path, sidecar_path(video_path), heatmap_path(video_path)):
                            try:
                                os.rename(path, os.path.join(args.trash_dir, os.path.basename(path)))
                            except OSError:
                                pass
                        entry['action'] = 'trashed'
                    else:
                        delete_video_and_sidecars(video_path)
                        entry['action'] = 'deleted'
                    totals['deleted'] += 1
                    totals['freed'] += size
                    display.log(f'  deleted: {os.path.basename(video_path)} ({human_size(size)})')
                report.write(json.dumps(entry) + '\n')
            report.flush()
    finally:
        display.close()
        pool.terminate()
        pool.join()
        report.close()

    action = 'deleted' if (args.delete and not args.heatmaps_only) else 'would delete'
    print(f'\nDone. nude: {totals["nude"]}, kept clean (lottery): {totals["clean_kept"]}, '
          f'kept (protected folder): {totals["protected"]}, '
          f'{action}: {totals["deleted"]} ({human_size(totals["freed"])}), '
          f'skipped (in use): {totals["skipped"]}, errors: {totals["errors"]}')
    print(f'Report appended to {args.report}')


if __name__ == '__main__':
    main()

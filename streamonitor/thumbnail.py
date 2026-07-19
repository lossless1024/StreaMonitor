import hashlib
import os
import subprocess
from multiprocessing import Process, Queue
import logging

from parameters import THUMBNAIL_WIDTH, FFMPEG_PATH

THUMBNAILS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.thumbnails')

logger = logging.getLogger(__name__)

_thumbnail_queue = None
_thumbnail_process = None


def get_thumbnail_path(video_path):
    """Get the expected thumbnail path for a video file based on hash of its filename."""
    filename = os.path.basename(video_path)
    name_hash = hashlib.md5(filename.encode()).hexdigest()
    return os.path.join(THUMBNAILS_DIR, f"{name_hash}.jpg")


def get_thumbnail_error_path(video_path):
    return os.path.splitext(get_thumbnail_path(video_path))[0] + '.err'


def thumbnail_exists(video_path):
    return os.path.exists(get_thumbnail_path(video_path))


def thumbnail_failed(video_path):
    return os.path.exists(get_thumbnail_error_path(video_path))


def generate_thumbnail(video_path, width=None):
    """Generate a thumbnail from a video file. Returns the thumbnail path or None on failure."""
    if width is None:
        width = THUMBNAIL_WIDTH

    thumb_path = get_thumbnail_path(video_path)
    err_path = get_thumbnail_error_path(video_path)
    if os.path.exists(thumb_path):
        return thumb_path

    os.makedirs(THUMBNAILS_DIR, exist_ok=True)

    def _success():
        if os.path.exists(err_path):
            try:
                os.remove(err_path)
            except OSError:
                pass

    def _failure():
        try:
            with open(err_path, 'w'):
                pass
        except OSError:
            pass

    try:
        subprocess.run(
            [
                FFMPEG_PATH,
                '-i', video_path,
                '-ss', '00:00:05',
                '-vframes', '1',
                '-vf', f'scale={width}:-1',
                '-y',
                thumb_path
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30
        )
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            _success()
            return thumb_path
        # If 5s seek failed (short video), try without seek
        subprocess.run(
            [
                FFMPEG_PATH,
                '-i', video_path,
                '-vframes', '1',
                '-vf', f'scale={width}:-1',
                '-y',
                thumb_path
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30
        )
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            _success()
            return thumb_path
    except Exception as e:
        logger.warning(f"Failed to generate thumbnail for {video_path}: {e}")

    _failure()
    return None


def _thumbnail_worker(queue, width):
    """Worker process that consumes video paths from the queue and generates thumbnails."""
    while True:
        try:
            video_path = queue.get()
            if video_path is None:  # Poison pill
                break
            generate_thumbnail(video_path, width)
        except Exception:
            pass


def start_thumbnail_worker():
    """Start the background thumbnail worker process."""
    global _thumbnail_queue, _thumbnail_process
    _thumbnail_queue = Queue()
    _thumbnail_process = Process(target=_thumbnail_worker, args=(_thumbnail_queue, THUMBNAIL_WIDTH), daemon=True)
    _thumbnail_process.start()


def enqueue_thumbnail(video_path):
    """Add a video to the thumbnail generation queue."""
    if _thumbnail_queue is None:
        return
    if not thumbnail_exists(video_path):
        _thumbnail_queue.put(video_path)


def enqueue_thumbnails_for_files(video_files):
    """Queue thumbnail generation for a list of VideoData objects that don't have thumbnails yet."""
    if _thumbnail_queue is None:
        return
    for video in video_files:
        if not thumbnail_exists(video.abs_path):
            _thumbnail_queue.put(video.abs_path)

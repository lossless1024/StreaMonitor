// Nudity heatmap strip under the video player: click/drag to seek,
// with a playhead cursor that follows playback.
// Uses event delegation so it keeps working across htmx content swaps.
(function () {
    'use strict';

    function findVideo(heatmapEl) {
        var container = heatmapEl.closest('.card, #content, body') || document;
        return container.querySelector('video');
    }

    function seekTo(heatmapEl, clientX) {
        var video = findVideo(heatmapEl);
        if (!video || !isFinite(video.duration) || video.duration <= 0) return;
        var rect = heatmapEl.getBoundingClientRect();
        var frac = (clientX - rect.left) / rect.width;
        video.currentTime = Math.min(Math.max(frac, 0), 1) * video.duration;
    }

    var dragging = null;

    document.addEventListener('pointerdown', function (e) {
        var el = e.target.closest('.nudity-heatmap');
        if (!el) return;
        dragging = el;
        seekTo(el, e.clientX);
        e.preventDefault();
    });

    document.addEventListener('pointermove', function (e) {
        if (dragging) seekTo(dragging, e.clientX);
    });

    document.addEventListener('pointerup', function () {
        dragging = null;
    });

    // timeupdate does not bubble; capture phase catches it from any <video>
    document.addEventListener('timeupdate', function (e) {
        if (!(e.target instanceof HTMLVideoElement)) return;
        var heatmap = document.querySelector('.nudity-heatmap');
        if (!heatmap) return;
        var cursor = heatmap.querySelector('.heatmap-cursor');
        if (!cursor || !isFinite(e.target.duration) || e.target.duration <= 0) return;
        cursor.style.left = (e.target.currentTime / e.target.duration * 100) + '%';
    }, true);
})();

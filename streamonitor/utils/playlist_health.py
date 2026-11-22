from __future__ import annotations

from dataclasses import asdict, dataclass

import m3u8


@dataclass(frozen=True)
class PlaylistHealth:
    is_variant: bool
    variant_count: int
    audio_rendition_count: int
    segment_count: int
    has_mouflon_marker: bool


def inspect_playlist(content: str, source_url: str) -> PlaylistHealth:
    if not content or not content.lstrip().startswith("#EXTM3U"):
        raise ValueError("response is not an HLS playlist")

    playlist = m3u8.loads(content)
    health = PlaylistHealth(
        is_variant=bool(playlist.is_variant),
        variant_count=len(playlist.playlists),
        audio_rendition_count=sum(
            1 for media in playlist.media
            if media.type == "AUDIO" and media.uri
        ),
        segment_count=len(playlist.segments),
        has_mouflon_marker="#EXT-X-MOUFLON:" in content,
    )

    if health.is_variant and health.variant_count == 0:
        raise ValueError("HLS master playlist has no video variants")
    lowered_url = source_url.lower()
    if (
        health.is_variant
        and health.audio_rendition_count == 0
        and any(marker in lowered_url for marker in ("llhls", "cmaf", "playlist_cmaf"))
    ):
        raise ValueError("CMAF master playlist has no usable audio rendition")
    if not health.is_variant and health.segment_count == 0:
        raise ValueError("HLS media playlist has no media segments")

    return health


def inspect_and_report(
    logger,
    siteslug: str,
    source_url: str,
    content: str,
) -> PlaylistHealth | None:
    try:
        health = inspect_playlist(content, source_url)
    except Exception as error:
        logger.warning(
            "Playlist health check failed for %s (%s): %s",
            siteslug,
            source_url,
            error,
        )
        return None

    if health.is_variant:
        logger.debug(
            "Playlist health for %s: %s",
            siteslug,
            asdict(health),
        )
    if health.has_mouflon_marker:
        logger.debug(
            "StripChat Mouflon playlist marker detected for %s",
            source_url,
        )
    return health

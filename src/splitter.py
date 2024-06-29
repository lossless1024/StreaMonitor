import os
import sys
import colorama as col
from . import ffmpeg_split as ffs


def main_split(filename: str, tqdm_opt: bool = True, split_filesize: int = None,
               filesize_factor: float = 0.95, chunk_strategy: str = 'eager',
               split_chunks: int = None, split_length: int = None,
               vcodec: str = 'copy', acodec: str = 'copy',
               extra: str = '-hide_banner -loglevel quiet -y'):
    """
    Split video based on a set of options.

    Parameters
    ----------
        filename (str): Path to the video file.
        tqdm_opt (bool): Show progress bar. Default is True.
        split_filesize (int): Split video based on a target filesize in bytes.
        filesize_factor (float): Factor to apply to the filesize. \
Default is 1.0.
        chunk_strategy (str): Strategy to use when splitting by filesize. \
Default is 'even'.
        split_chunks (int): Split video into a set number of chunks.
        split_length (int): Split video into chunks of a set length in seconds.
        vcodec (str): Video codec to use. Default is 'copy'.
        acodec (str): Audio codec to use. Default is 'copy'.
        extra (str): Extra options for ffmpeg, e.g. '-e -threads 8'. \
Default is ''.
    """
    video_length = ffs.get_video_length(filename)
    file_size = os.stat(filename).st_size
    split_filesize = int(split_filesize * filesize_factor)
    if file_size < split_filesize * 1.2:
        return
    if split_filesize and chunk_strategy == 'even':
        split_chunks = ffs.ceildiv(file_size, split_filesize)
    if split_chunks != None:
        split_length = ffs.ceildiv(video_length, split_chunks)
    if not split_length and split_filesize:
        split_length = int(
            split_filesize / float(file_size) * video_length)
    try:
        ffs.split_by_seconds(
            video_length=video_length, tqdm_opt=tqdm_opt,
            **craft_options(filename, split_filesize, filesize_factor,
                            chunk_strategy, split_chunks, split_length,
                            vcodec, acodec, extra))
        os.remove(filename)
    except KeyboardInterrupt:
        print(col.Fore.RED + 'Aborted by user.' + col.Style.RESET_ALL)
        sys.exit(1)


def craft_options(filename: str, split_filesize: int = None,
                  filesize_factor: float = 1.0, chunk_strategy: str = '',
                  split_chunks: int = None, split_length: int = None,
                  vcodec: str = 'copy', acodec: str = 'copy', extra: str = '',
                  manifest: str = None):
    """
    Craft options for ffmpeg_split.split_by_seconds().

    Parameters
    ----------
        filename (str): Path to the video file.
        split_filesize (int): Split video based on a target filesize in bytes.
        filesize_factor (float): Factor to apply to the filesize. \
Default is 1.0.
        chunk_strategy (str): Strategy to use when splitting by filesize. \
Default is 'even'.
        split_chunks (int): Split video into a set number of chunks.
        split_length (int): Split video into chunks of a set length in seconds.
        vcodec (str): Video codec to use. Default is 'copy'.
        acodec (str): Audio codec to use. Default is 'copy'.
        extra (str): Extra options for ffmpeg, e.g. '-e -threads 8'. \
Default is ''.
        manifest (str): Split video based on a json manifest file.

    Returns
    -------
        options (dict): Options for ffmpeg_split.split_by_seconds().
    """
    options = {
        'filename': filename,
        'split_filesize': split_filesize,
        'filesize_factor': filesize_factor,
        'chunk_strategy': chunk_strategy,
        'split_chunks': split_chunks,
        'split_length': split_length,
        'vcodec': vcodec,
        'acodec': acodec,
        'extra': extra,
        'manifest': manifest
    }
    return options


if __name__ == '__main__':
    main_split('./videos/2023-05-22 08-14-39.mp4',
               split_filesize=500000000)

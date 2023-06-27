import os
import sys
import colorama as col
import threading as th
from tqdm import tqdm
import make_vcsis

from src import move_all as ma
from src import splitter as sp
from src import delete_less as dl


def move_and_split(src: str, dst: str, file_size: int = None, log: bool = True,
                   tqdm_opt: bool = True):
    """
    Move all files from subdirectories of src into dst.
    Then split all video files in dst into file_size chunks
    and delete all original files.

    Parameters
    ----------
        src (str): source directory
        dst (str): destination directory
        file_size (int): size of chunks in Bytes, default is None
    """
    ma.move_all_subs(src, dst, log=True)
    ma.delete_empty_dirs(src, log=True)
    # find all video files in dst
    files = []
    for root, dirs, filenames in os.walk(dst):
        for filename in tqdm(filenames, desc=f'{col.Style.RESET_ALL}\
[MAC]: Finding video files')\
                if tqdm_opt else filenames:
            if filename.endswith(('.mp4', '.mkv', '.avi', '.mov')):
                files.append(os.path.join(root, filename))
    # split all video files in dst

    def call_function(filename):
        try:
            sp.main_split(filename, split_filesize=file_size, tqdm_opt=False)
        except Exception as e:
            print(
                f'{col.Style.RESET_ALL}[MAC]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} {e}')
        except KeyboardInterrupt:
            print(f'{col.Style.RESET_ALL}[MAC]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} Keyboard interrupt')

    threads = []
    for f in tqdm(files, desc=f'{col.Style.RESET_ALL}[MAC]: Starting threads')\
            if tqdm_opt else files:
        t = th.Thread(target=call_function, args=(f,))
        threads.append(t)
        t.start()

    for t in tqdm(threads, desc=f'{col.Style.RESET_ALL}[MAC]: Splitting videos')\
            if tqdm_opt else threads:
        t.join()
    if log:
        print(f'{col.Style.RESET_ALL}[MAC]: {col.Fore.GREEN}\
DONE!{col.Style.RESET_ALL}')


def vcsis(foldername: str = 'videos', overwrite: bool = False):
    """
    Create a video contact sheet image for each video file in foldername.

    Parameters
    ----------
        foldername (str): name of folder containing video files
        overwrite (bool): overwrite existing vcsi files, default is False
    """
    for root, dirs, filenames in os.walk(foldername):
        for filename in tqdm(filenames, desc=f'{col.Style.RESET_ALL}\
[VCSI]: Making thumbnails'):
            if filename.endswith(('.mp4', '.mkv', '.avi', '.mov')):
                try:
                    make_vcsis.main(foldername + '/' +
                                    filename, overwrite=overwrite)
                except Exception as e:
                    print(
                        f'{col.Style.RESET_ALL}[VCSI]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} {e}')
                except KeyboardInterrupt:
                    print(f'{col.Style.RESET_ALL}[VCSI]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} Keyboard interrupt')
    print(f'{col.Style.RESET_ALL}[VCSI]: {col.Fore.GREEN}\
DONE!{col.Style.RESET_ALL}')


if __name__ == '__main__':
    move_and_split('downloads', 'videos', file_size=2000000000)
    dl.delete_less('videos', 200000000, log=True)
    vcsis('videos', overwrite=False)
    input()

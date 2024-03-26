import os
import sys
import colorama as col


def move_all_subs(src: str, dst: str, ext: str = None, log: bool = False):
    """
    Move all files from subdirectories of src into dst.

    Parameters
    ----------
        src (str): source directory
        dst (str): destination directory
        ext (str): extension of files to move, default is None
        log (bool): if True, print all moved files
    """
    if not os.path.isdir(src):
        print(
            f'{col.Style.RESET_ALL}[MOVER]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} \
\"{src}\" is not a directory')
    if not os.path.isdir(dst):
        os.mkdir(dst)

    for root, dirs, files in os.walk(src):
        for f in files:
            if ext is None or f.endswith(ext):
                src_path = os.path.join(root, f)
                dst_path = os.path.join(dst, f)
                try:
                    # check if file occupied by another process
                    if os.access(src_path, os.W_OK):
                        os.rename(src_path, dst_path)
                        if log:
                            print(f'{col.Style.RESET_ALL}[MOVER]: \
\"{src_path}\" -> \"{dst_path}\"')
                except PermissionError:
                    print(
                        f'{col.Style.RESET_ALL}[MOVER]: {col.Fore.RED}\
ERROR{col.Style.RESET_ALL}: \"{src_path}\" is occupied by another process')
                except FileExistsError:
                    print(
                        f'{col.Style.RESET_ALL}[MOVER]: \
{col.Fore.RED}ERROR{col.Style.RESET_ALL}: \
\"{dst_path}\" already exists')
                    continue
    print(f'{col.Style.RESET_ALL}[MOVER]: \
{col.Fore.GREEN}DONE!{col.Style.RESET_ALL}')


def delete_empty_dirs(src: str, log: bool = False):
    """
    Delete all empty subdirectories of src.

    Parameters
    ----------
        src (str): source directory
        log (bool): if True, print all deleted directories
    """
    if not os.path.isdir(src):
        print(
            f'{col.Style.RESET_ALL}[MOVER]: {col.Fore.RED}\
ERROR:{col.Style.RESET_ALL} \
\"{src}\" is not a directory')
        sys.exit(1)

    for root, dirs, files in os.walk(src, topdown=False):
        for d in dirs:
            d_path = os.path.join(root, d)
            if not os.listdir(d_path):
                try:
                    os.rmdir(d_path)
                    if log:
                        print(f'{col.Style.RESET_ALL}[DELETER]: \"{d_path}\" \
deleted')
                except OSError:
                    print(
                        f'{col.Style.RESET_ALL}[DELETER]: {col.Fore.RED}\
ERROR{col.Style.RESET_ALL}: \
\"{d_path}\" is not empty')
                    continue
    print(f'{col.Style.RESET_ALL}[DELETER]: \
{col.Fore.GREEN}DONE!{col.Style.RESET_ALL}')


if __name__ == '__main__':
    move_all_subs('downloads', 'videos', ext='.mp4', log=True)
    delete_empty_dirs('downloads', log=True)

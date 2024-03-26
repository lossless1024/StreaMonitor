import sys
import argparse as arg
import os
import colorama as col


def delete_less(directory_path: str, size: int = 200000000, ext: str = ".mp4",
                log: bool = True):
    """
    Delete all files in directory_path that are less than size in bytes.

    Parameters
    ----------
        directory_path (str): path to directory
        size (int): size in bytes, default is 200000000
        ext (str): extension of files to delete, default is ".mp4"
        log (bool): if True, print all deleted files
    """
    counter = 0
    # Get the list of files in the directory
    files = os.listdir(directory_path)
    # get absolute path
    directory_path = os.path.abspath(directory_path)
    # Iterate over all the files
    for file in files:
        # Get the path of the file
        file_path = os.path.join(directory_path, file)
        # only mp4
        if file_path.endswith(ext):
            # Get the size of the file in bytes
            size_ = os.path.getsize(file_path)
            # If size is less than 200 MB
            if size_ < size:
                # Delete the file
                os.remove(file_path)
                if log:
                    print(
                        f'{col.Style.RESET_ALL}[DELETER]: \"{file_path}\" \
deleted')
                counter += 1
    if log:
        print(f'{col.Style.RESET_ALL}[DELETER]: \
{col.Fore.GREEN}DONE!{col.Style.RESET_ALL}')


if __name__ == "__main__":
    parser = arg.ArgumentParser(description="Delete files less than 200 MB")
    parser.add_argument("-p", "--path", help="Path of the directory")
    parser.add_argument("-s", "--size", help="Size of the file")
    parser.add_argument("-e", "--ext", help="Extension of the file")
    args = parser.parse_args()
    # can be only path or path and size or path and size and ext
    if args.path and args.size and args.ext:
        delete_less(args.path, args.size, args.ext)
    elif args.path and args.size:
        delete_less(args.path, args.size)
    elif args.path:
        delete_less(args.path)
    else:
        print(f"{red}Please provide path of the directory{reset}")
        sys.exit(1)
    print(f'delete_less :: {green}[SUCCESS]{reset} Done!')

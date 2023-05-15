import sys
import argparse as arg
import os


black = '\x1b[30m'
red = '\x1b[31m'
green = '\x1b[32m'
yellow = '\x1b[33m'
blue = '\x1b[34m'
magenta = '\x1b[35m'
cyan = '\x1b[36m'
white = '\x1b[37m'
background_black = '\x1b[40m'
background_red = '\x1b[41m'
background_green = '\x1b[42m'
background_yellow = '\x1b[43m'
background_blue = '\x1b[44m'
background_magenta = '\x1b[45m'
background_cyan = '\x1b[46m'
background_white = '\x1b[47m'
reset = '\x1b[0m'


def delete_less(directory_path, size=200000000, ext="mp4"):
    ext = "." + ext
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
                print(f"Deleted {file_path}")
                counter += 1
    if counter != 0:
        print(
            f"delete_less :: {green}[SUCCESS]{reset} Deleted {counter} files less than {size} bytes.")

# python delete_less200mb.py -p /home/username/Videos -s 200000000


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

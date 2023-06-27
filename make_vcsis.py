import os
import sys
import subprocess as sub
import vcsi


def main(filename: str = 'videos', overwrite: bool = False):
    args = ["vcsi", "-t", "-w 7680", "-g 8x8"]
    if not overwrite:
        args.append("--no-overwrite")
    args.append(filename)
    cp = sub.run(args)


if __name__ == '__main__':
    main('videos/AbsintheGirl-20230609-121937.mp4')

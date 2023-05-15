#!/usr/bin/env python

from __future__ import print_function

import csv
import json
import math
import os
import shlex
import subprocess
from optparse import OptionParser


def split_by_manifest(filename, manifest, vcodec="copy", acodec="copy",
                      extra="", **kwargs):
    """ Split video into segments based on the given manifest file.

    Arguments:
        filename (str)      - Location of the video.
        manifest (str)      - Location of the manifest file.
        vcodec (str)        - Controls the video codec for the ffmpeg video
                            output.
        acodec (str)        - Controls the audio codec for the ffmpeg video
                            output.
        extra (str)         - Extra options for ffmpeg.
    """
    if not os.path.exists(manifest):
        print("File does not exist: %s" % manifest)
        raise SystemExit

    with open(manifest) as manifest_file:
        manifest_type = manifest.split(".")[-1]
        if manifest_type == "json":
            config = json.load(manifest_file)
        elif manifest_type == "csv":
            config = csv.DictReader(manifest_file)
        else:
            print("Format not supported. File must be a csv or json file")
            raise SystemExit

        split_cmd = ["ffmpeg", "-i", filename, "-vcodec", vcodec,
                     "-acodec", acodec, "-y"] + shlex.split(extra)
        try:
            fileext = filename.split(".")[-1]
        except IndexError as e:
            raise IndexError("No . in filename. Error: " + str(e))
        for video_config in config:
            split_args = []
            try:
                split_start = video_config["start_time"]
                split_length = video_config.get("end_time", None)
                if not split_length:
                    split_length = video_config["length"]
                filebase = video_config["rename_to"]
                if fileext in filebase:
                    filebase = ".".join(filebase.split(".")[:-1])

                split_args += ["-ss", str(split_start), "-t",
                               str(split_length), filebase + "." + fileext]
                print("########################################################")
                print("About to run: " + " ".join(split_cmd + split_args))
                print("########################################################")
                subprocess.check_output(split_cmd + split_args)
            except KeyError as e:
                print("############# Incorrect format ##############")
                if manifest_type == "json":
                    print("The format of each json array should be:")
                    print("{start_time: <int>, length: <int>, rename_to: <string>}")
                elif manifest_type == "csv":
                    print("start_time,length,rename_to should be the first line ")
                    print("in the csv file.")
                print("#############################################")
                print(e)
                raise SystemExit


def get_video_length(filename):
    output = subprocess.check_output(("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                      "default=noprint_wrappers=1:nokey=1", filename)).strip()
    video_length = int(float(output))
    print("Video length in seconds: " + str(video_length))

    return video_length


def ceildiv(a, b):
    return int(math.ceil(a / float(b)))


def split_by_seconds(filename, split_length, vcodec="copy", acodec="copy",
                     extra="", video_length=None, **kwargs):
    if split_length and split_length <= 0:
        print("Split length can't be 0")
        raise SystemExit

    if not video_length:
        video_length = get_video_length(filename)
    split_count = ceildiv(video_length, split_length)
    if split_count == 1:
        print("Video length is less then the target split length.")
        raise SystemExit

    split_cmd = ["ffmpeg", "-i", filename, "-vcodec", vcodec, "-acodec", acodec] + shlex.split(extra)
    try:
        filebase = ".".join(filename.split(".")[:-1])
        fileext = filename.split(".")[-1]
    except IndexError as e:
        raise IndexError("No . in filename. Error: " + str(e))
    for n in range(0, split_count):
        split_args = []
        if n == 0:
            split_start = 0
        else:
            split_start = split_length * n

        split_args += ["-ss", str(split_start), "-t", str(split_length),
                       filebase + "-" + str(n + 1) + "-of-" +
                       str(split_count) + "." + fileext]
        print("About to run: " + " ".join(split_cmd + split_args))
        subprocess.check_output(split_cmd + split_args)


def main():
    parser = OptionParser()

    parser.add_option("-f", "--file",
                      dest="filename",
                      help="File to split, for example sample.avi",
                      type="string",
                      action="store"
                      )
    parser.add_option("-s", "--split-size",
                      dest="split_length",
                      help="Split or chunk size in seconds, for example 10",
                      type="int",
                      action="store"
                      )
    parser.add_option("-c", "--split-chunks",
                      dest="split_chunks",
                      help="Number of chunks to split to",
                      type="int",
                      action="store"
                      )
    parser.add_option("-S", "--split-filesize",
                      dest="split_filesize",
                      help="Split or chunk size in bytes (approximate)",
                      type="int",
                      action="store"
                      )
    parser.add_option("--filesize-factor",
                      dest="filesize_factor",
                      help="with --split-filesize, use this factor in time to"
                           " size heuristics [default: %default]",
                      type="float",
                      action="store",
                      default=0.95
                      )
    parser.add_option("--chunk-strategy",
                      dest="chunk_strategy",
                      help="with --split-filesize, allocate chunks according to"
                           " given strategy (eager or even)",
                      type="choice",
                      action="store",
                      choices=['eager', 'even'],
                      default='eager'
                      )
    parser.add_option("-m", "--manifest",
                      dest="manifest",
                      help="Split video based on a json manifest file. ",
                      type="string",
                      action="store"
                      )
    parser.add_option("-v", "--vcodec",
                      dest="vcodec",
                      help="Video codec to use. ",
                      type="string",
                      default="copy",
                      action="store"
                      )
    parser.add_option("-a", "--acodec",
                      dest="acodec",
                      help="Audio codec to use. ",
                      type="string",
                      default="copy",
                      action="store"
                      )
    parser.add_option("-e", "--extra",
                      dest="extra",
                      help="Extra options for ffmpeg, e.g. '-e -threads 8'. ",
                      type="string",
                      default="",
                      action="store"
                      )
    (options, args) = parser.parse_args()

    def bailout():
        parser.print_help()
        raise SystemExit

    if not options.filename:
        bailout()

    if options.manifest:
        split_by_manifest(**options.__dict__)
    else:
        video_length = None
        if not options.split_length:
            video_length = get_video_length(options.filename)
            file_size = os.stat(options.filename).st_size
            split_filesize = None
            if options.split_filesize:
                split_filesize = int(options.split_filesize * options.filesize_factor)
            if split_filesize and options.chunk_strategy == 'even':
                options.split_chunks = ceildiv(file_size, split_filesize)
            if options.split_chunks:
                options.split_length = ceildiv(video_length, options.split_chunks)
            if not options.split_length and split_filesize:
                options.split_length = int(split_filesize / float(file_size) * video_length)
        if not options.split_length:
            bailout()
        split_by_seconds(video_length=video_length, **options.__dict__)


if __name__ == '__main__':
    main()

import os
import sys
import threading
import time
import subprocess
import json


json_file = open('chopper_config.json', 'r')
json_data = json.load(json_file)
basepath = json_data['directory_path']
size = json_data['max_size']

i = 0
orders = []
to_delete = []

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

# get full path
basepath = os.path.abspath(basepath)

for entry in os.listdir(basepath):
    if entry.endswith('.mp4'):
        if not entry.startswith('.') and \
                os.path.isfile(os.path.join(basepath, entry)) and \
                os.path.getsize(os.path.join(basepath, entry)) > int(size*1.1):
            i += 1
            orders.append(
                f'python ./src/ffmpeg-split.py -f \"{os.path.join(basepath, entry)}\" -S {size}')
            to_delete.append(os.path.join(basepath, entry))


def run_command(command):
    subprocess.call(command, shell=True)


for order in orders:
    t = threading.Thread(target=run_command, args=(order,))
    t.start()
    time.sleep(1)

# if all threads are done, then exit
while True:
    if len(threading.enumerate()) == 1:
        break
    else:
        time.sleep(1)

# delete original files
if len(to_delete) != 0:
    print(f"chopper :: {yellow}[WARNING]{reset} Deleting original files...")
    time.sleep(10)
    for item in to_delete:
        os.remove(item)

print(f"chopper :: {green}[SUCCESS]{reset} Done!")
os.system("pause")

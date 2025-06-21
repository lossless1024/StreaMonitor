import math


def human_file_size(size):
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]
    size = abs(size)
    exponent = 0
    if size > 0:
        exponent = min(math.floor(math.log(size, 1024)), len(units) - 1)
    humansize = size / (1024 ** exponent)
    if humansize >= 1000:
        return f"{humansize:.4g}{units[exponent]}"
    else:
        return f"{humansize:.3g}{units[exponent]}"

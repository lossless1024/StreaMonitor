import math


def human_file_size(size):
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]
    size = abs(size)
    exponent = math.floor(math.log(size, 1024))
    if exponent > len(units) - 1:
        return f"{size:.1f}YiB"
    humansize = size / (1024 ** exponent)
    if humansize >= 1000:
        return f"{humansize:.4g}{units[exponent]}"
    else:
        return f"{humansize:.3g}{units[exponent]}"
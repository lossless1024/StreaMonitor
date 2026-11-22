import math


def human_file_size(size, si=False, suffix="B", space=' ', fix_decimals=None):
    if si:
        units = ["", "K", "M", "G", "T", "P", "E", "Z"]
        base = 1000
    else:
        units = ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]
        base = 1024

    size = abs(size)
    exponent = 0
    if size > 0:
        exponent = min(math.floor(math.log(size, base)), len(units) - 1)
    humansize = size / (base ** exponent)
    if fix_decimals:
        return f"{humansize:.{fix_decimals}f}{space}{units[exponent]}{suffix}"
    if humansize >= 1000:
        return f"{humansize:.4g}{space}{units[exponent]}{suffix}"
    else:
        return f"{humansize:.3g}{space}{units[exponent]}{suffix}"

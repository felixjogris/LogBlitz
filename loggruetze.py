#!/usr/bin/env python3

LOGDIR = "/var/log"

import os, re, datetime

archived_log_re = re.compile("\.(\d+)(\.(bz2|gz|xz))?$", re.IGNORECASE)

def bytes_pretty(filesize):
    for suffix in ("B", "kB", "MB", "GB", "TB"):
        if filesize < 1024:
            break
        filesize /= 1024
    return "%.2f %s" % (filesize, suffix)

def logfile_sorter(entry):
    match = archived_log_re.search(entry.name)
    return -1 if match is None else int(match.group(1))

def traverse_logdir(logdir, subdir="", indent=0):
    logfiles = []

    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return logfiles

    entries = filter(lambda entry: not entry.name.startswith("."), entries)
    entries = sorted(entries, key=logfile_sorter)
    entries = sorted(entries, key=lambda entry: entry.name)

    oldfile = None

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            print("%s&#128193;%s/" % (" " * indent, entry.name))
            logfiles += traverse_logdir(logdir, relname, indent + 1)
        elif entry.is_file(follow_symlinks=False):
            if oldfile is None or oldfile != archived_log_re.sub("", entry.name):
                oldfile = entry.name
                i = indent
                icon = "&#128196;"
            else:
                i = indent + 1
                icon = "&#128195;"

            stat = entry.stat(follow_symlinks=False)
            print("%s%s%s %s %s" % (" " * i, icon, entry.name, bytes_pretty(stat.st_size), datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%c")))
            logfiles.append(entry.path)

    return logfiles


print("""Content-Type: text/html; charset=utf-8

<html>
<head>
<title>Loggrütze</title>
</head>
<body>
<pre>""")
logfiles = traverse_logdir(LOGDIR)
print("</pre></body></html")

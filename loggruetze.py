#!/usr/bin/env python3

LOGDIR = "/var/log"

import os, re

def traverse_logdir(logdir, subdir):
    loggroups = {}

    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return loggroups

    for entry in filter(lambda entry: not entry.name.startswith("."), entries):
        relentry = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            loggroups = { **loggroups, **traverse_logdir(logdir, relentry) }
        elif entry.is_file(follow_symlinks=False):
            key_name = re.sub("(\.\d+)?(\.(bz2|gz|xz))$", "", relentry.lower())
            logfiles = loggroups.setdefault(key_name, {})
            stat = entry.stat(follow_symlinks=False)
            logfiles[entry.path] = { "size"  : stat.st_size,
                                     "mtime" : stat.st_mtime }

    return loggroups

print(traverse_logdir(LOGDIR, ""))

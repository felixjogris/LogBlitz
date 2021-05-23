#!/usr/bin/env python3

LOGDIRS = ("/var/log",)

import sys, os, re, datetime, html, cgi

def bytes_pretty(filesize):
    for suffix in ("B", "k", "M", "G", "T"):
        if filesize < 1024:
            break
        filesize /= 1024
    return f"{filesize:.2f}{suffix}"

def logfile_sorter(entry):
    match = re.search("\.(\d+)(\.(bz2|gz|xz))?$", entry.name, re.IGNORECASE)
    return -1 if match is None else int(match.group(1))

def traverse_logdir(logdir, max_name_indent_len=0, logfilefilter="", subdir="", indent=0):
    logfiles = []

    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return max_name_indent_len, logfiles

    entries = filter(lambda entry: not entry.name.startswith("."), entries)
    entries = sorted(entries, key=logfile_sorter)
    entries = sorted(entries, key=lambda entry: entry.name)

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            max_name_indent_len, childs = traverse_logdir(logdir,
                                                          max_name_indent_len,
                                                          logfilefilter,
                                                          relname, indent + 1)

            if len(childs) > 0:
                logfiles.append({ "name"   : entry.name + "/",
                                  "indent" : indent })

                if len(entry.name) + 1 + 2 * indent > max_name_indent_len:
                    max_name_indent_len = len(entry.name) + 1 + 2 * indent

                logfiles += childs
        elif (entry.is_file(follow_symlinks=False) and
              (logfilefilter == "" or
               re.search(logfilefilter, entry.name, re.IGNORECASE))):
            stat = entry.stat(follow_symlinks=False)
            size_human = bytes_pretty(stat.st_size)

            mtime_human = datetime.datetime.fromtimestamp(
                                  stat.st_mtime).strftime("%Y/%m/%d %H:%M:%S")

            logfiles.append({ "name"        : entry.name,
                              "indent"      : indent,
                              "path"        : entry.path,
                              "mtime"       : stat.st_mtime,
                              "mtime_human" : mtime_human,
                              "size"        : stat.st_size,
                              "size_human"  : size_human })

            if len(entry.name) + 2 * indent > max_name_indent_len:
                max_name_indent_len = len(entry.name) + 2 * indent

    return max_name_indent_len, logfiles


logfilefilter = ""

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    cgi = cgi.FieldStorage()
    logfilefilter = cgi.getvalue("logfilefilter", "")

logfiles = {}
max_name_indent_len = 0

for logdir in LOGDIRS:
    max_name_indent_len, childs = traverse_logdir(logdir, max_name_indent_len,
                                                  re.escape(logfilefilter))
    logfiles[logdir] = childs

content_type = "text/html; charset=utf-8"
result = (f"""<html>
<head>
<title>Loggrütze</title>
</head>
<body>
<form method="POST">
<div>
Display filter: <input type="text" name="logfilefilter" value="{(html.escape(logfilefilter))}">
<input type="submit">
</div>
<div>
<select id="logfiles" size="30" multiple style="font-family:monospace">""")

for logdir in sorted(logfiles):
    result += (f'<optgroup label="{html.escape(logdir)}/" ' +
               'style="font-family:monospace">\n')

    for logfile in logfiles[logdir]:
        filler = (max_name_indent_len - 2 * logfile["indent"] -
                  len(logfile["name"]) + 1)

        result += (f'<option>{"&nbsp;" * 2 * logfile["indent"]}' +
                   f'{logfile["name"]}{"&nbsp;" * filler}')

        if "size_human" in logfile and "mtime_human" in logfile:
            result += (f' {"&nbsp;" * (8 - len(logfile["size_human"]))}' +
                       f'{logfile["size_human"]}&nbsp;&nbsp;' +
                       f'{logfile["mtime_human"]}&nbsp;')

        result += "</option>\n"

    result += "</optgroup>\n"

result += """</select>
</div>
</body>
</html>"""

print(f"Content-Type: {content_type}\nContent-Length: {len(result)}\n")
print(result,)

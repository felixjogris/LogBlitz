#!/usr/bin/env python3

LOGDIRS = ("/var/log",)
DATETIME_FMT = "%Y/%m/%d %H:%M:%S"

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

def traverse_logdir(logdir, max_name_indent_len, shown_files, total_files,
                    shown_bytes, total_bytes, shown_dirs, total_dirs,
                    filefilter, subdir="", indent=0):
    logfiles = []

    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return (max_name_indent_len, shown_files, total_files, shown_bytes,
                total_bytes, shown_dirs, total_dirs, logfiles)

    entries = filter(lambda entry: not entry.name.startswith("."), entries)
    entries = sorted(entries, key=logfile_sorter)
    entries = sorted(entries, key=lambda entry: entry.name)

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            total_dirs += 1

            (max_name_indent_len, shown_files, total_files, shown_bytes,
             total_bytes, shown_dirs, total_dirs, childs) = traverse_logdir(
                 logdir, max_name_indent_len, shown_files, total_files,
                 shown_bytes, total_bytes, shown_dirs, total_dirs, filefilter,
                 relname, indent + 1)

            if len(childs) > 0:
                shown_dirs += 1
                logfiles.append({ "name"   : entry.name + "/",
                                  "indent" : indent })

                if len(entry.name) + 1 + 2 * indent > max_name_indent_len:
                    max_name_indent_len = len(entry.name) + 1 + 2 * indent

                logfiles += childs
        elif entry.is_file(follow_symlinks=False):
            stat = entry.stat(follow_symlinks=False)
            total_files += 1
            total_bytes += stat.st_size

            if (filefilter == "" or
                re.search(filefilter, entry.name, re.IGNORECASE)):
                shown_files += 1
                shown_bytes += stat.st_size
                size_human = bytes_pretty(stat.st_size)

                mtime_human = datetime.datetime.fromtimestamp(
                                  stat.st_mtime).strftime(DATETIME_FMT)

                logfiles.append({ "name"        : entry.name,
                                  "indent"      : indent,
                                  "path"        : entry.path,
                                  "mtime"       : stat.st_mtime,
                                  "mtime_human" : mtime_human,
                                  "size"        : stat.st_size,
                                  "size_human"  : size_human })

                if len(entry.name) + 2 * indent > max_name_indent_len:
                    max_name_indent_len = len(entry.name) + 2 * indent

    return (max_name_indent_len, shown_files, total_files, shown_bytes,
            total_bytes, shown_dirs, total_dirs, logfiles)


filefilter = ""
query = ""
limitlines = 1000
limitmemory = 1

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    cgi = cgi.FieldStorage()
    filefilter = cgi.getvalue("filefilter", filefilter)
    query = cgi.getvalue("query", query)
    if cgi.getvalue("clear", "") == "Clear":
        filefilter = ""
    tmp = cgi.getvalue("limitlines", str(limitlines))
    if tmp.isnumeric():
        limitlines = int(tmp)
    tmp = cgi.getvalue("limitmemory", str(limitmemory))
    if tmp.isnumeric():
        limitmemory = int(tmp)
    

logfiles = {}
max_name_indent_len = 0
shown_files = 0
total_files = 0
shown_bytes = 0
total_bytes = 0
shown_dirs = 0
total_dirs = 0

for logdir in LOGDIRS:
    shown_dirs += 1
    total_dirs += 1

    (max_name_indent_len, shown_files, total_files, shown_bytes, total_bytes,
     shown_dirs, total_dirs, childs) = traverse_logdir(
        logdir, max_name_indent_len, shown_files, total_files, shown_bytes,
        total_bytes, shown_dirs, total_dirs, re.escape(filefilter))

    logfiles[logdir] = childs

result = ("""<html>
<head>
<title>LogGrütze</title>
<style type="text/css">
* {
  margin: 0;
}
html, body, form {
  height: 100%;
  width: 100%;
  font-family: sans-serif;
  display: table;
}
optgroup {
  font-family: monospace;
}
#result {
  display: table-cell;
  vertical-align: top;
  border-top: 1px solid black;
  border-bottom: 1px solid black;
}
</style>
</head>""" +
          f"""<body>
<form method="POST">
<div style="display:table-row; background-color:lightgray">
<div style="display:table-cell">
<input type="submit" name="apply" value="Apply" style="float:right">
<input type="submit" name="clear" value="Clear" style="float:right">
<span style="overflow:hidden; display:block">
<input type="text" name="filefilter" value="{(html.escape(filefilter))}"
placeholder="Filter filenames..." style="width:100%"
title="Use a regular expression to filter shown filenames">
</span>
</div>
<div style="display:table-cell; width:100%; text-align:center">
<input type="text" name="query" value="{(html.escape(query))}"
placeholder="Search log entries..."
title="Use a regular expression to search log entries">
<input type="checkbox" name="ignorecase" style="margin-left:10px"> Ignore case
<input type="text" name="limitlines" value="{str(limitlines)}" size="4"
title="Limit search results to this number of lines"
style="margin-left:10px; text-align:right"> line limit
<input type="text" name="limitmemory" value="{str(limitmemory)}" size="4"
title="Limit search results to this amount of memory"
style="margin-left:10px; text-align:right"> MByte memory limit
<span style="float:right; font-size:small">
<a href="https://ogris.de/loggruetze/" target="_blank">About LogGrütze...</a>
</span>
</div>
</div>

<div style="display:table-row; height:100%; background-color:red">
<div style="display:table-cell">
<select name="fileselect" multiple
style="font-family:monospace; height:100%">""")

for logdir in sorted(logfiles):
    result += f'<optgroup label="{html.escape(logdir)}/">\n'

    for i, logfile in enumerate(logfiles[logdir]):
        filler = (max_name_indent_len - 2 * logfile["indent"] -
                  len(logfile["name"]) + 1)

        result += (f'<option style="background-color:#{"eee" if i%2==0 else "fff"}">{"&nbsp;" * 2 * logfile["indent"]}' +
                   f'{logfile["name"]}{"&nbsp;" * filler}')

        if "size_human" in logfile and "mtime_human" in logfile:
            result += (f' {"&nbsp;" * (8 - len(logfile["size_human"]))}' +
                       f'{logfile["size_human"]}&nbsp;&nbsp;' +
                       f'{logfile["mtime_human"]}&nbsp;')

        result += "</option>\n"

    result += "</optgroup>\n"

result += f"""</select>
</div>
<div id="result">
</div>
</div>

<div style="display:table-row; background-color:lightgray">
<div style="display:table-cell">
{shown_files}/{total_files} files
({bytes_pretty(shown_bytes)}/{bytes_pretty(total_bytes)}),
{shown_dirs}/{total_dirs} folders shown
</div>
<div style="display:table-cell">
0 (0B) shown, 0 (0B) matching, 0 (0B) total entries in 0 selected log files
<span style="float:right">
Server local time: {datetime.datetime.now().strftime(DATETIME_FMT)}
</span>
</div>
</div>

</body>
</html>"""

print("Content-Type: text/html; charset=utf-8\n" +
      f"Content-Length: {len(result)}\n")
print(result,)

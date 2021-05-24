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

def traverse_logdir(logdir, max_name_indent_len=0, filefilter="", subdir="", indent=0):
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
                                                          filefilter,
                                                          relname, indent + 1)

            if len(childs) > 0:
                logfiles.append({ "name"   : entry.name + "/",
                                  "indent" : indent })

                if len(entry.name) + 1 + 2 * indent > max_name_indent_len:
                    max_name_indent_len = len(entry.name) + 1 + 2 * indent

                logfiles += childs
        elif (entry.is_file(follow_symlinks=False) and
              (filefilter == "" or
               re.search(filefilter, entry.name, re.IGNORECASE))):
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


filefilter = ""
query = ""

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    cgi = cgi.FieldStorage()
    filefilter = cgi.getvalue("filefilter", "")
    query = cgi.getvalue("query", "")

logfiles = {}
max_name_indent_len = 0

for logdir in LOGDIRS:
    max_name_indent_len, childs = traverse_logdir(logdir, max_name_indent_len,
                                                  re.escape(filefilter))
    logfiles[logdir] = childs

content_type = "text/html; charset=utf-8"
result = ("""<html>
<head>
<title>Loggrütze</title>
<style type="text/css">
* {
  margin:0;
}
html, body, form {
  height:100%;
  width:100%;
  font-family:sans-serif;
  display:table;
}
optgroup {
  font-family:monospace;
}
</style>
</head>""" +
          f"""<body>
<form method="POST">
<div style="display:table-row">
<div style="display:table-cell">
<input type="submit" value="Apply" style="float:right">
<span style="overflow:hidden; display:block">
<input type="text" name="filefilter" value="{(html.escape(filefilter))}"
placeholder="Filter filenames..." style="width:100%"
title="Use a regular expression to filter shown filenames">
</span>
</div>
<div style="display:table-cell;width:100%;text-align:center">
<input type="text" name="query" value="{(html.escape(query))}"
placeholder="any regex">
</div>
</div>

<div style="display:table-row;height:100%;background-color:red">
<div style="display:table-cell">
<select name="fileselect" multiple style="font-family:monospace;height:100%">""")

for logdir in sorted(logfiles):
    result += f'<optgroup label="{html.escape(logdir)}/">\n'

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
<div style="display:table-cell;vertical-align:top">
bla
</div>
</div>

<div style="display:table-row">
<div style="display:table-cell">
</div>
<div style="display:table-cell">
bla
</div>
</div>

</body>
</html>"""

print(f"Content-Type: {content_type}\nContent-Length: {len(result)}\n")
print(result,)

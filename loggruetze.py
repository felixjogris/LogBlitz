#!/usr/bin/env python3

LOGDIRS = ("/var/log",)
XZ = "/usr/bin/xz"
DATETIME_FMT = "%Y/%m/%d %H:%M:%S"

import sys, os, re, datetime, html, cgi, gzip, bz2

class LogFiles:
    dir2files = {}
    max_name_indent_len = 0
    shown_files = 0
    total_files = 0
    shown_bytes = 0
    total_bytes = 0
    shown_dirs = 0
    total_dirs = 0

def bytes_pretty(filesize):
    for suffix in ("B", "k", "M", "G", "T"):
        if filesize < 1024:
            break
        filesize /= 1024
    return f"{filesize:.2f}{suffix}"

def logfile_sorter(entry):
    match = re.search("\.(\d+)(\.(bz2|gz|xz))?$", entry.name, re.IGNORECASE)
    return -1 if match is None else int(match.group(1))

def traverse_logdir(logdir, filefilter, logfiles, subdir="", indent=0):
    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return False

    entries = filter(lambda entry: not entry.name.startswith("."), entries)
    entries = sorted(entries, key=logfile_sorter)
    entries = sorted(entries, key=lambda entry: entry.name)

    dir2files = logfiles.dir2files.setdefault(logdir, [])
    found_files = False

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            logfiles.total_dirs += 1
            cnt = len(dir2files)
            if (traverse_logdir(logdir, filefilter, logfiles, relname,
                                indent + 1)):
                logfiles.shown_dirs += 1
                dir2files.insert(cnt, {
                    "name"   : entry.name + "/",
                    "indent" : indent })

                candid_name_indent_len = len(entry.name) + 1 + 2 * indent
                if candid_name_indent_len > logfiles.max_name_indent_len:
                    logfiles.max_name_indent_len = candid_name_indent_len

        elif entry.is_file(follow_symlinks=False):
            stat = entry.stat(follow_symlinks=False)
            logfiles.total_files += 1
            logfiles.total_bytes += stat.st_size

            if (filefilter == "" or
                re.search(filefilter, entry.name, re.IGNORECASE)):
                found_files = True
                logfiles.shown_files += 1
                logfiles.shown_bytes += stat.st_size
                size_human = bytes_pretty(stat.st_size)

                mtime_human = datetime.datetime.fromtimestamp(
                                  stat.st_mtime).strftime(DATETIME_FMT)

                dir2files.append({
                    "name"        : entry.name,
                    "indent"      : indent,
                    "path"        : entry.path,
                    "mtime"       : stat.st_mtime,
                    "mtime_human" : mtime_human,
                    "size"        : stat.st_size,
                    "size_human"  : size_human })

                candid_name_indent_len = len(entry.name) + 2 * indent
                if candid_name_indent_len > logfiles.max_name_indent_len:
                    logfiles.max_name_indent_len = candid_name_indent_len

    return found_files

def search(logfiles, fileselect, query, regex, ignorecase, limitlines,
           limitmemory):
    retval=[]
    for logfile in filter(lambda logfile: "path" in logfile and
                          logfile["path"] in fileselect,
                          [logfile for logfile in logfiles.dir2files[logdir]
                           for logdir in LOGDIRS]):
        retval.append(logfile["path"])
        if logfile["path"].lower().endswith(".gz"):
            pass
        elif logfile["path"].lower().endswith(".bz2"):
            pass
        elif logfile["path"].lower().endswith(".xz"):
            pass
        else:
            with open(logfile["path"]) as fp:
                for line in fp:
                    if query in line:
                        retval.append("<nobr>"+html.escape(line)+"</nobr>")

    return retval


query = ""
regex = False
ignorecase = False
filefilter = ""
fileselect = []
limitlines = 1000
limitmemory = 1
dosearch = False

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    form = cgi.FieldStorage()
    query = form.getvalue("query", query)
    regex = "regex" in form
    ignorecase = "ignorecase" in form
    filefilter = form.getvalue("filefilter", filefilter)
    fileselect = form.getlist("fileselect")
    tmp = form.getvalue("limitlines", str(limitlines))
    if tmp.isnumeric():
        limitlines = int(tmp)
    tmp = form.getvalue("limitmemory", str(limitmemory))
    if tmp.isnumeric():
        limitmemory = int(tmp)
    if form.getvalue("clear", "") == "Clear":
        filefilter = ""
    dosearch = form.getvalue("search", "") == "Search"

logfiles = LogFiles()

for logdir in LOGDIRS:
    logfiles.total_dirs += 1

    if logdir.endswith(os.path.sep):
        logdir = logdir[:-1]

    if traverse_logdir(logdir, re.escape(filefilter), logfiles):
        logfiles.shown_dirs += 1

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
 title="Enter an expression to search log entries">
<input type="submit" name="search" value="Search" style="margin-left:10px">
<input type="checkbox" name="ignorecase" style="margin-left:10px"
 {('checked="checked"' if ignorecase else "")}> Ignore case
<input type="checkbox" name="regex" style="margin-left:10px"
 {('checked="checked"' if regex else "")}> Regular expression
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

<div style="display:table-row; height:100%">
<div style="display:table-cell">
<select name="fileselect" multiple
 style="font-family:monospace; height:100%">""")

for logdir in sorted(logfiles.dir2files):
    result += f'<optgroup label="{html.escape(logdir)}/">\n'

    for logfile in logfiles.dir2files[logdir]:
        filler = (logfiles.max_name_indent_len - 2 * logfile["indent"] -
                  len(logfile["name"]) + 1)

        if "path" in logfile:
            selected = (' selected="selected"' if logfile["path"] in fileselect
                        else "")
            result += (f'<option value="{html.escape(logfile["path"])}"' +
                       f'{selected}>{"&nbsp;" * 2 * logfile["indent"]}' +
                       f'{html.escape(logfile["name"])}{"&nbsp;" * filler}' +
                       f' {"&nbsp;" * (8 - len(logfile["size_human"]))}' +
                       f'{logfile["size_human"]}&nbsp;&nbsp;' +
                       f'{logfile["mtime_human"]}&nbsp;</option>\n')
        else:
            result += (f'<option>{"&nbsp;" * 2 * logfile["indent"]}' +
                       f'{html.escape(logfile["name"])}</option>\n')

    result += "</optgroup>\n"

result += f"""</select>
</div>
<div id="result">
{"<br>".join(search(logfiles, fileselect, query, regex, ignorecase, limitlines,
                    limitmemory)) if dosearch else ""}
</div>
</div>

<div style="display:table-row; background-color:lightgray">
<div style="display:table-cell">
{logfiles.shown_files}/{logfiles.total_files} files
({bytes_pretty(logfiles.shown_bytes)}/{bytes_pretty(logfiles.total_bytes)}),
{logfiles.shown_dirs}/{logfiles.total_dirs} folders shown
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
      f'Content-Length: {len(result.encode("utf-8"))}\n')
print(result, end="")

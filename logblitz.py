#!/usr/bin/env python3

LOGDIRS = ("/var/log",)
XZ = "/usr/bin/xz"
DATETIME_FMT = "%Y/%m/%d %H:%M:%S"

import sys, os, re, datetime, html, cgi, gzip, bz2, subprocess

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
    if filesize < 1024:
        return f"{filesize}B"
    for suffix in ("K", "M", "G", "T"):
        filesize /= 1024
        if filesize < 1024:
            break
    return f"{filesize:.2f}{suffix}"

def logfile_sorter(entry):
    match = re.search("\.(\d+)(\.(bz2|gz|xz))?$", entry.name, re.IGNORECASE)
    return -1 if match is None else int(match.group(1))

def traverse_logdir(logdir, filefilter, logfiles, subdir="", indent=0):
    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as _:
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

def search_in_file(fp, query_re, display):
    for line in fp:
        try:
            decoded_line = line.decode("utf-8")
        except Exception as _:
            decoded_line = line.decode("ascii")

        display(query_re.search(decoded_line), decoded_line, line)

def search(logfiles, fileselect, query, ignorecase, invert, regex,
           limitlines, limitmemory):
    html_lines = []
    shown_lines = [0]
    shown_bytes = [0]
    matching_lines = [0]
    matching_bytes = [0]
    total_lines = [0]
    total_bytes = [0]
    num_logfiles = [0]

    limit_lines = None if limitlines == "" else int(limitlines)
    limit_bytes = None if limitmemory == "" else int(limitmemory) * 1024**2

    try:
        query_re = re.compile(query if regex else re.escape(query),
                              re.IGNORECASE if ignorecase else 0)
    except Exception as e:
        return "", (f"Error: Invalid regex: {html.escape(str(e))}",)

    if invert:
        def display(match, line, raw_line):
            total_lines[0] += 1
            total_bytes[0] += len(raw_line)
            if match is None:
                matching_lines[0] += 1
                matching_bytes[0] += len(raw_line)
                if ((limit_lines is None or limit_lines > shown_lines[0]) and
                    (limit_bytes is None or limit_bytes > shown_bytes[0])):
                    shown_lines[0] += 1
                    shown_bytes[0] += len(raw_line)
                    html_lines.append(f"<nobr>{html.escape(line)}</nobr>")
    else:
        def display(match, line, raw_line):
            total_lines[0] += 1
            total_bytes[0] += len(raw_line)
            if not match is None:
                matching_lines[0] += 1
                matching_bytes[0] += len(raw_line)
                if ((limit_lines is None or limit_lines > shown_lines[0]) and
                    (limit_bytes is None or limit_bytes > shown_bytes[0])):
                    shown_lines[0] += 1
                    shown_bytes[0] += len(raw_line)
                    s, e = match.start(), match.end()
                    html_lines.append(
                        f"<nobr>{html.escape(line[:s])}"
                        f'<b class="sr">{html.escape(line[s:e])}</b>'
                        f"{html.escape(line[e:])}</nobr>")

    for logfile in filter(lambda logfile: "path" in logfile and
                          logfile["path"] in fileselect,
                          [logfile for logfile in logfiles.dir2files[logdir]
                           for logdir in LOGDIRS]):
        num_logfiles[0] += 1
        html_lines.append(f'<b>{logfile["path"]}</b>\n')

        try:
            if logfile["path"].lower().endswith(".gz"):
                with gzip.open(logfile["path"], "rb") as fp:
                    search_in_file(fp, query_re, display)
            elif logfile["path"].lower().endswith(".bz2"):
                with bz2.open(logfile["path"], "rb") as fp:
                    search_in_file(fp, query_re, display)
            elif logfile["path"].lower().endswith(".xz"):
                with subprocess.Popen([XZ, "-cd", logfile["path"]],
                                      stdout=subprocess.PIPE) as proc:
                    search_in_file(proc.stdout, query_re, display)
            else:
                with open(logfile["path"], "rb") as fp:
                    search_in_file(fp, query_re, display)
        except Exception as e:
            return "", (f"Error: {html.escape(str(e))}",)

    html_status = ("<span"
        f"""{' class="red"' if not limit_lines is None and
                               shown_lines[0] >= limit_lines else ""}>"""
        f"{shown_lines[0]}</span> (<span"
        f"""{' class="red"' if not limit_bytes is None and
                               shown_bytes[0] >= limit_bytes else ""}>"""
        f"{bytes_pretty(shown_bytes[0])}</span>) lines shown, "
        f"{matching_lines[0]} ({bytes_pretty(matching_bytes[0])}) matching, "
        f"{total_lines[0]} ({bytes_pretty(total_bytes[0])}) total entries in "
        f"{num_logfiles[0]} selected log file"
        f'{"" if num_logfiles[0] == 1 else "s"}')

    return html_status, html_lines


query = ""
regex = False
ignorecase = False
invert = False
filefilter = ""
fileselect = []
limitlines = "1000"
limitmemory = "1"

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    form = cgi.FieldStorage()
    query = form.getvalue("query", query)
    regex = "regex" in form
    ignorecase = "ignorecase" in form
    invert = "invert" in form
    filefilter = form.getvalue("filefilter", "")
    fileselect = form.getlist("fileselect")
    tmp = form.getvalue("limitlines", "")
    if tmp == "" or tmp.isnumeric():
        limitlines = tmp
    tmp = form.getvalue("limitmemory", "")
    if tmp == "" or tmp.isnumeric():
        limitmemory = tmp

logfiles = LogFiles()

for logdir in LOGDIRS:
    logfiles.total_dirs += 1

    if logdir.endswith(os.path.sep):
        logdir = logdir[:-1]

    if traverse_logdir(logdir, re.escape(filefilter), logfiles):
        logfiles.shown_dirs += 1

html_status, html_lines = search(logfiles, fileselect, query, ignorecase,
                                 invert, regex, limitlines, limitmemory)

result = ("""<html>
<head>
<title>LogBlitz</title>
<style type="text/css">
* {
  margin: 0;
}
html, body, form {
  height: 100%;
  width: 100%;
  font-family: sans-serif;
}
select, optgroup {
  font-family: monospace;
}
select {
  height: 100%;
}
#result {
  font-family: monospace;
  vertical-align: top;
  overflow: scroll;
}
.sbt, .sbb {
  background-color: lightgray;
}
.sbt {
  border-bottom: 1px solid black;
}
.sbb {
  border-top: 1px solid black;
}
.sr {
  background-color: lightyellow;
}
.red {
  color: red;
}
</style>
</head>"""
          f"""<body>
<form method="POST">
<div style="height:100%; display:grid; grid-template-rows:auto 1fr auto; grid-template-columns:auto 1fr">

<div class="sbt">
<input type="text" name="filefilter" value="{(html.escape(filefilter))}"
 placeholder="Filter filenames..." style="width:100%" id="filefilter"
 title="Use a regular expression to filter shown filenames">
</div>

<div class="sbt">
<input type="text" name="query" value="{(html.escape(query))}"
 placeholder="Search log entries..." style="width:40em"
 title="Enter an expression to search log entries">
<input type="submit" name="search" value="Search" style="margin-left:10px">
<input type="checkbox" name="ignorecase" style="margin-left:10px"
 {('checked="checked"' if ignorecase else "")}> Ignore case
<input type="checkbox" name="invert" style="margin-left:10px"
 {('checked="checked"' if invert else "")}> Invert
<input type="checkbox" name="regex" style="margin-left:10px"
 {('checked="checked"' if regex else "")}> Regular expression
<input type="text" name="limitlines" value="{html.escape(limitlines)}"
 title="Limit search results to this number of lines"
 style="margin-left:10px; text-align:right; width:4em"> line limit
<input type="text" name="limitmemory" value="{html.escape(limitmemory)}"
 title="Limit search results to this amount of memory"
 style="margin-left:10px; text-align:right; width:4em"> MiB memory limit
<span style="float:right; font-size:small">
<a href="https://ogris.de/logblitz/" target="_blank">About LogBlitz...</a>
</span>
</div>

<div>
<select name="fileselect" multiple>""")

for logdir in sorted(logfiles.dir2files):
    result += f'<optgroup label="{html.escape(logdir)}/">\n'

    for logfile in logfiles.dir2files[logdir]:
        filler = (logfiles.max_name_indent_len - 2 * logfile["indent"] -
                  len(logfile["name"]) + 1)

        if "path" in logfile:
            selected = (' selected="selected"' if logfile["path"] in fileselect
                        else "")
            result += (f'<option value="{html.escape(logfile["path"])}"'
                       f'{selected}>{"&nbsp;" * 2 * logfile["indent"]}'
                       f'{html.escape(logfile["name"])}{"&nbsp;" * filler}'
                       f' {"&nbsp;" * (8 - len(logfile["size_human"]))}'
                       f'{logfile["size_human"]}&nbsp;&nbsp;'
                       f'{logfile["mtime_human"]}&nbsp;</option>\n')
        else:
            result += (f'<option>{"&nbsp;" * 2 * logfile["indent"]}'
                       f'{html.escape(logfile["name"])}</option>\n')

    result += "</optgroup>\n"

result += f"""</select>
</div>

<div id="result">
{"<br>".join(html_lines)}
</div>

<div class="sbb">
{logfiles.shown_files}/{logfiles.total_files} files
({bytes_pretty(logfiles.shown_bytes)}/{bytes_pretty(logfiles.total_bytes)}),
{logfiles.shown_dirs}/{logfiles.total_dirs} folders shown
</div>

<div class="sbb">
{html_status}
<span style="float:right">
Server local time: {datetime.datetime.now().strftime(DATETIME_FMT)}
</span>
</div>

</div>
</form>
</body>
</html>"""

print("Content-Type: text/html; charset=utf-8\n"
      f'Content-Length: {len(result.encode("utf-8"))}\n')
print(result, end="")

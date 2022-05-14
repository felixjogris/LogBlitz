#!/usr/bin/env -S-P/usr/local/bin:/usr/bin:/bin python3

import sys, os, re, datetime, html, cgi, gzip, bz2, configparser, lzma
import collections

DATETIME_FMT = "%Y/%m/%d %H:%M:%S"
VERSION = "5"

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

def traverse_logdir(logdir, cfgdirfilter_re, cfgfilefilter_re, filefilter_re,
                    logfiles, showdotfiles, showunreadables,
                    subdir="", indent=0):
    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as _:
        return False

    if not showdotfiles:
        entries = filter(lambda entry: not entry.name.startswith("."), entries)
    entries = sorted(entries, key=logfile_sorter)
    entries = sorted(entries, key=lambda entry: entry.name)

    dir2files = logfiles.dir2files.setdefault(logdir, [])
    found_files = False

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if (entry.is_dir(follow_symlinks=False) and
            cfgdirfilter_re.search(entry.name)):
            logfiles.total_dirs += 1
            cnt = len(dir2files)
            found_files = traverse_logdir(logdir, cfgdirfilter_re,
                                          cfgfilefilter_re, filefilter_re,
                                          logfiles, showdotfiles,
                                          showunreadables, relname, indent + 1)
            if found_files:
                logfiles.shown_dirs += 1
                dir2files.insert(cnt, {
                    "name"   : entry.name + os.path.sep,
                    "indent" : indent })

                candid_name_indent_len = len(entry.name) + 1 + 2 * indent
                if candid_name_indent_len > logfiles.max_name_indent_len:
                    logfiles.max_name_indent_len = candid_name_indent_len

        elif (entry.is_file(follow_symlinks=False) and
              cfgfilefilter_re.search(entry.name)):
            stat = entry.stat(follow_symlinks=False)
            logfiles.total_files += 1
            logfiles.total_bytes += stat.st_size

            readable = os.access(entry.path, os.R_OK)

            if (filefilter_re.search(entry.name) and
                (showunreadables or
                 readable)):
                found_files = True
                logfiles.shown_files += 1
                logfiles.shown_bytes += stat.st_size
                size_human = bytes_pretty(stat.st_size)

                mtime_human = datetime.datetime.fromtimestamp(
                                  stat.st_mtime).strftime(DATETIME_FMT)

                dir2files.append({
                    "name"        : entry.name,
                    "readable"    : readable,
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

def search(charset, logdirs, logfiles, fileselect, query, reverse,
           ignorecase, invert, regex, limitlines, limitmemory):
    html_lines = []
    shown_lines = 0
    shown_bytes = 0
    matching_lines = 0
    matching_bytes = 0
    total_lines = 0
    total_bytes = 0
    num_logfiles = 0

    limit_lines = None if limitlines == "" else int(limitlines)
    limit_bytes = None if limitmemory == "" else int(limitmemory) * 1024**2

    try:
        query_re = re.compile(query if regex else re.escape(query),
                              re.IGNORECASE if ignorecase else 0)
    except Exception as e:
        return "", (f"Error: Invalid regex: {html.escape(str(e))}",)

    # logfiles.dir2files is a dictionary whose keys reflect any logdir given
    # in the config file
    # each value is sorted list of dictionaries, where each dictionary denotes
    # a logfile or a subdirectory, depending on whether the key "path" is set
    # or not, respectively
    # the inner filter() emits only those logdirs that contain logfiles
    # the outer filter() emits only those logfiles that the user asked for
    for logfile in filter(
        lambda logfile: "path" in logfile and logfile["path"] in fileselect,
        [logfile for logdir in filter(
            lambda logdir: logdir in logfiles.dir2files, logdirs)
         for logfile in logfiles.dir2files[logdir]]):

        num_logfiles += 1
        lines = collections.deque()

        try:
            if logfile["path"].lower().endswith(".gz"):
                fp = gzip.open(logfile["path"], "rb")
            elif logfile["path"].lower().endswith(".bz2"):
                fp = bz2.open(logfile["path"], "rb")
            elif logfile["path"].lower().endswith(".xz"):
                fp = lzma.open(logfile["path"], "rb")
            else:
                fp = open(logfile["path"], "rb")
        except Exception as e:
            return "", (f"Error: {html.escape(str(e))}",)

        line_number = 0
        for raw_line in fp:
            line_number += 1
            len_raw_line = len(raw_line)
            line = raw_line.decode(charset, errors="replace")

            total_lines += 1
            total_bytes += len_raw_line

            match = query_re.search(line)
            if (invert and match) or (not invert and not match):
                continue

            matching_lines += 1
            matching_bytes += len_raw_line

            while (reverse and len(lines) > 0 and 
                   ((limit_lines is not None and
                     limit_lines <= shown_lines) or
                    (limit_bytes is not None and
                     limit_bytes <= shown_bytes))):
                shown_lines -= 1
                l = lines.popleft()
                shown_bytes -= l[2]

            if ((limit_lines is None or limit_lines > shown_lines) and
                (limit_bytes is None or limit_bytes > shown_bytes)):
                shown_lines += 1
                shown_bytes += len_raw_line
                lines.append((line, match, len_raw_line, line_number))

        if reverse:
            lines.reverse()

        len_max_line_number = len(str(line_number))

        html_lines.append(f'<div class="lf">{logfile["path"]}</div>\n')
        if invert:
            for line in lines:
                html_lines.append('<div class="sl"><span class="ln">'
                                  f'{str(line[3]).rjust(len_max_line_number)}'
                                  f"</span>{html.escape(line[0])}</div>\n")
        else:
            for line in lines:
                line, s, e, line_number = line[0], line[1].start(), line[1].end(), line[3]
                html_lines.append(
                    '<div class="sl"><span class="ln">'
                    f"{str(line_number).rjust(len_max_line_number)}</span>"
                    f"{html.escape(line[:s])}"
                    f'<span class="sr">{html.escape(line[s:e])}</span>'
                    f"{html.escape(line[e:])}</div>\n")

    html_status = ("<span"
        f"""{' class="red"' if not limit_lines is None and
                               shown_lines >= limit_lines else ""}>"""
        f"{shown_lines}</span> (<span"
        f"""{' class="red"' if not limit_bytes is None and
                               shown_bytes >= limit_bytes else ""}>"""
        f"{bytes_pretty(shown_bytes)}</span>) lines shown, "
        f"{matching_lines} ({bytes_pretty(matching_bytes)}) matching, "
        f"{total_lines} ({bytes_pretty(total_bytes)}) total lines in "
        f"{num_logfiles} selected log file"
        f'{"" if num_logfiles == 1 else "s"}')

    return html_status, html_lines


configfile = os.path.join(os.path.dirname(sys.argv[0]), os.pardir, "etc",
                          "logblitz.ini")
config = configparser.ConfigParser()
config.read(configfile)

remote_user = os.environ.get("REMOTE_USER", "DEFAULT")
if config.has_option(remote_user, "logdirs"):
    logdirs = config.get(remote_user, "logdirs").split(os.path.pathsep)
else:
    logdirs = []

if config.has_option(remote_user, "charset"):
    charset = config.get(remote_user, "charset")
else:
    charset = "ISO-8859-1"

if config.has_option(remote_user, "dirfilter"):
    cfgdirfilter = config.get(remote_user, "dirfilter")
else:
    cfgdirfilter = ""

if config.has_option(remote_user, "filefilter"):
    cfgfilefilter = config.get(remote_user, "filefilter")
else:
    cfgfilefilter = ""

query = ""
query = ""
reverse = False
regex = False
showlinenumbers = True
ignorecase = False
invert = False
filefilter = ""
fileselect = []
limitlines = "1000"
limitmemory = "1"
showdotfiles = False
showunreadables = False

if os.environ.get("REQUEST_METHOD", "GET") == "POST":
    form = cgi.FieldStorage()
    query = form.getvalue("query", query)
    reverse = "reverse" in form
    ignorecase = "ignorecase" in form
    invert = "invert" in form
    regex = "regex" in form
    showlinenumbers = "showlinenumbers" in form
    showdotfiles = "showdotfiles" in form
    showunreadables = "showunreadables" in form
    charset = form.getvalue("charset", charset)
    filefilter = form.getvalue("filefilter", "")
    fileselect = form.getlist("fileselect")
    tmp = form.getvalue("limitlines", "")
    if tmp == "" or tmp.isnumeric():
        limitlines = tmp
    tmp = form.getvalue("limitmemory", "")
    if tmp == "" or tmp.isnumeric():
        limitmemory = tmp

try:
    cfgdirfilter_re = re.compile(cfgdirfilter)
except Exception as e:
    cfgdirfilter_re = None

try:
    cfgfilefilter_re = re.compile(cfgfilefilter)
except Exception as e:
    cfgfilefilter_re = None

try:
    filefilter_re = re.compile(filefilter)
except Exception as e:
    filefilter_re = None

logfiles = LogFiles()

if cfgdirfilter_re is None:
    html_status, html_lines = "", ("Error: Invalid dirfilter in config file:",
                                   html.escape(cfgdirfilter),
                                   html.escape(str(e)))
elif cfgfilefilter_re is None:
    html_status, html_lines = "", ("Error: Invalid filefilter in config file:",
                                   html.escape(cfgfilefilter),
                                   html.escape(str(e)))
elif filefilter_re is None:
    html_status, html_lines = "", ("Error: Invalid filefilter:",
                                   html.escape(filefilter),
                                   html.escape(str(e)))
else:
    for logdir in logdirs:
        logfiles.total_dirs += 1

        if logdir.endswith(os.path.sep):
            logdir = logdir[:-1]

        if traverse_logdir(logdir, cfgdirfilter_re, cfgfilefilter_re,
                           filefilter_re, logfiles, showdotfiles,
                           showunreadables):
            logfiles.shown_dirs += 1

    html_status, html_lines = search(charset, logdirs, logfiles, fileselect,
                                     query, reverse, ignorecase, invert, regex,
                                     limitlines, limitmemory)

result = ("""<!DOCTYPE html>
<html>
<head>
<title>LogBlitz</title>
<link rel="shortcut icon" href="data:image/x-icon;base64,AAABAAEAQEAQAAEABABoCgAAFgAAACgAAABAAAAAgAAAAAEABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/AAC7/wD///8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMzMzMzMzMAAAAAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMzMzMzMzMzAAAAAAAAAAAAAAAAMzAAAAAAAAAAAAAAAAAAAAAAAzMAAAAAAAAAAAAAAAAzMAAAAAAAAAAAAAAAEAAAAAADMwAAAAAAAAAAAAAAADMwAAAAAAAAAAAAAAARAAAAAAMzAAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMxERMzMzMzMAAAAAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMRETMzMzMwAAAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMxEhEzMzMzAAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMSIRMzMzMAAAAAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMxEiETMzMwAAAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMzMRIhEzMzAAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMzEiIRMzMAAAAAAAAAAAAAAAAzMAAAAAAAAAAAAAAAAAARIiETMwAAAAAAAAAAAAAAADMwAAAAAAAAAAAAAAAAAAESIhEzAAAAAAAAAAAAAAAAMzAAAAAAAAAAAAAAAAAAABEiIRMAAAAAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMzESIiEQAAAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMzMzMxEiIhEAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMzMzESIiIRAAAAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMzMxEiIiERAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMzMzMzMRIiIhEQAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMzMzMxEiIiIhEAAAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMzMzMRIiIiIRAAAAAAAAAAADMwAAAAAAAAAAAAAAAAAAAAABEiIiIiEQAAAAAAAAAAMzAAAAAAAAAAAAAAAAAAAAAAARIiIiIhEAAAAAAAAAAzMAAAAAAAAAAAABEREREREREREiIiIiIRAAAAAAAAADMzMzMzMzMzMzMzMRERERERERERIiIiIiEQAAAAAAAAMzMzMzMzMzMzMzMzESIiIiIiIiIiIiIiIhEAAAAAAAAzMzMzMzMzMzMzMzMRIiIiIiIiIiIiIiIiIREAAAAAADMzMzMzMzMzMzMzMzESIiIiIiIiIiIiIiIiERAAAAAAMzMzMzMzMzMzMzMzMxEiIiIiIiIiIiIiIiIiEQAAAAAzMzMzMzMzMzMzMzMzESIiIiIiIiIiIiIiIiIhEAAAADMwAAAAAAAAAAAAAAABEiIiIiIiIiIiIiIiIiIRAAAAMzAAAAAAAAAAAAAAAAESIiIiIiIiIhEREREREREAAAAzMAAAAAAAAAAAAAAAABEiIiIiIiIiEREREREREQAAADMzMzMzMzMzMzMzMzMzMRIiIiIiIiIRAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzMxEiIiIiIiIiEQAAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMRIiIiIiIiIhEAAAAAAAAAADMzMzMzMzMzMzMzMzMzMzESIiIiIiIiEQAAAAAAAAAAMzMzMzMzMzMzMzMzMzMzMRIiIiIiIiIhEAAAAAAAAAAzMzMzMzMzMzMzMzMzMzMzESIiIiIiIiEQAAAAAAAAADMwAAAAAAAAAAAAAAAAAAARIiIiIiIiIhEAAAAAAAAAMzAAAAAAAAAAAAAAAAAAAAESIiIiIiIiEQAAAAAAAAAzMAAAAAAAAAAAAAAAAAAAABEiIiIiIiIhEAAAAAAAADMzMzMzMzMzMzMzMzMzMzMzESIiIiIiIiIRAAAAAAAAMzMzMzMzMzMzMzMzMzAAAAABEiIiIiIiIhEAAAAAAAAzMzMzMzMzMzMzMzMzMAAAAAARIiIiIiIiIRAAAAAAADMzMzMzMzMzMzMzMzMwAAAAABEiIiIiIiIhEAAAAAAAMzMzMzMzMzMzMzMzMzAAMzMzMRIiIiIiIiIRAAAAAAAzMzMzMzMzMzMzMzMzMAAzMzMxEiIiIiIiIiEQAAAAADMwAAAAAAAAAAAAAAAAADMzMwARIiIiIiIiIRAAAAAAMzAAAAAAAAAAAAAAAAAAMzMwAAESIiIiIiIiEQAAAAAzMAAAAAAAAAAAAAAAAAAzMwAAARIiIiIiIiIRAAAAADMzMzMzMzMzMzMzMzMwADMwAAAAEREREREREREQAAAAMzMzMzMzMzMzMzMzMzAAMwAAAAABERERERERERAAAAAzMzMzMzMzMzMzMzMzMAAwAAAAAAAAAAAAAAAAAAAAADMzMzMzMzMzMzMzMzMwAAAAAAAAAAAAAAAAAAAAAAAAMzMzMzMzMzMzMzMzMzAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADgAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAH//4AAAAAAAf//gAAAAAAB//+AAAAAAAD//4AAAAAAAH//gAAAAAAAP/+AAAAAAAAf/4AAAAAAAA//gAAAAAAAB/+AAAAAAAAD/4AAAAAAAAH/gAAAAAAAAP+AAAAAAAAAP4AAAAAAAAAfgAAAAAAAAA+AAAAAAAAAB4AAAAAAAAADgAAAAAAAAAOAAAAAAAAAA4AAAAAAAD//gAAAAAAAH/+AAAAAAAAP/4AAAAAAAA//gAAAAAAAB/+AAAAAAAAH/4AAAAAAAAP/gAAAAAAAA/+AAAAAAAAB/4AAAAAAAAD/gAAAAAAAAP+AAAAAAAAAf4AAAAAAAAB/gAAAAAAAAD+AAAAAAAAAH4AAAAAAAAAfgAAAAAAAAA+AAAAAACAAD4AAAAAAcAAHgAAAAAD4AAeAAAAAAf///4AAAAAD////gAAAAAf///+AAAAAD////4AAAAAf////gAAAAD////w==" type="image/x-icon">
<style type="text/css">
* {
  margin: 0;
}
html, body, form {
  height: 100%;
  width: 100%;
  font-family: sans-serif;
}
optgroup {
  font-family: monospace;
}
.sbt, .sbb, .bar {
  background-color: lightgray;
}
.sbt, .sbb {
  overflow: hidden;
}
.sbt {
  border-bottom: 1px solid darkgray;
}
.sbb {
  border-top: 1px solid darkgray;
}
.box {
  white-space: nowrap;
}
.lf {
  font-weight: bold;
}
.sl, .sr {
  white-space: pre;
}
.sr {
  font-weight: bold;
  background-color: yellow;
}
.ln {
  margin-right: 2em;
  -webkit-user-select: none;
  display: """
        f'{"inline" if showlinenumbers else "none"}'
""";
}
.red {
  color: red;
}
.bar {
  cursor: col-resize;
  border-left: 1px solid darkgray;
  border-right: 1px solid darkgray;
}
#barm {
  background-image: url('data:image/svg+xml;utf8,<svg \\
    xmlns="http://www.w3.org/2000/svg" width="4" height="50"> \\
    <rect x="1" y="0" width="1" height="50" fill="gray" /></svg>');
  background-repeat: repeat-x;
  background-position: center;
}
</style>
</head>"""
          f"""<body>
<form method="POST">
<div style="height:100%; display:grid; grid-template-rows:auto 1fr auto;
 grid-template-columns:auto 12px 1fr">

<div class="sbt" id="filefilter">
<input type="text" name="filefilter" value="{(html.escape(filefilter))}"
 placeholder="Filter filenames..." style="width:20em"
 title="Use a regular expression to filter shown filenames">
<span class="box">
<input type="checkbox" name="showdotfiles" style="margin-left:10px"
 {('checked="checked"' if showdotfiles else "")} id="showdotfiles"
 title="Show files and directories which names start with a dot">
<span title="Show files and directories which names start with a dot"
 onclick="toggle('showdotfiles')">Show dot files</span>
</span>
<span class="box">
<input type="checkbox" name="showunreadables" style="margin-left:10px"
 {('checked="checked"' if showunreadables else "")} id="showunreadables"
 title="Show files and directories which are not accessible">
<span title="Show files and directories which are not accessible"
 onclick="toggle('showunreadables')">Show inaccessible files</span>
</span>
</div>

<div class="bar"></div>

<div class="sbt">
<input type="text" name="query" value="{(html.escape(query))}"
 placeholder="Search log entries..." style="width:40em"
 title="Enter an expression to search log entries">
<input type="submit" name="search" value="Search" style="margin-left:10px">
<span class="box">
<input type="checkbox" name="reverse" style="margin-left:10px"
 {('checked="checked"' if reverse else "")} id="reverse"
 title="Display latest log entries first">
<span title="Display latest log entries first" onclick="toggle('reverse')">Reverse</span>
</span>
<span class="box">
<input type="checkbox" name="ignorecase" style="margin-left:10px"
 {('checked="checked"' if ignorecase else "")} id="ignorecase"
 title="Search log entries regardless of case">
<span title="Search log entries regardless of case"
 onclick="toggle('ignorecase')">Ignore case</span>
</span>
<span class="box">
<input type="checkbox" name="invert" style="margin-left:10px"
 {('checked="checked"' if invert else "")} id="invert"
 title="Show log entries not matching the search expression">
<span title="Show log entries not matching the search expression"
 onclick="toggle('invert')">Invert
</span>
</span>
<span class="box">
<input type="checkbox" name="regex" style="margin-left:10px"
 {('checked="checked"' if regex else "")} id="regex"
 title="Assume search expression is a regular expression">
<span title="Assume search expression is a regular expression"
 onclick="toggle('regex')">Regular expression</span>
</span>
<span class="box">
<input type="checkbox" name="showlinenumbers" style="margin-left:10px"
 {('checked="checked"' if showlinenumbers else "")} id="showlinenumbers"
 title="Show line numbers" onchange="toggleCssClass('showlinenumbers', 'ln')">
<span title="Show line numbers"
 onclick="toggle('showlinenumbers');
          toggleCssClass('showlinenumbers', 'ln');">Show line numbers</span>
</span>
<span class="box">
<span title="Charset of logfiles" style="margin-left:10px">Charset:</span>
<input type="text" name="charset" value="{html.escape(charset)}"
 title="Charset of logfiles" style="width:7em">
</span>
<span class="box">
<input type="text" name="limitlines" value="{html.escape(limitlines)}"
 title="Limit search results to this number of lines"
 style="margin-left:10px; text-align:right; width:4em">
<span title="Limit search results to this number of lines">line limit</span>
</span>
<span class="box">
<input type="text" name="limitmemory" value="{html.escape(limitmemory)}"
 title="Limit search results to this amount of memory"
 style="margin-left:10px; text-align:right; width:4em">
<span title="Limit search results to this amount of memory">MiB memory
 limit</span>
<span style="float:right; font-size:small">
<a href="https://ogris.de/logblitz/"
 target="_blank">About LogBlitz {VERSION}...</a>
</span>
</span>
</div>

<div id="fileselect">
<select name="fileselect" multiple 
 style="font-family:monospace; height:100%; width:100%">""")

for logdir in sorted(logfiles.dir2files):
    result += f'<optgroup label="{html.escape(logdir)}{os.path.sep}">\n'

    for logfile in logfiles.dir2files[logdir]:
        filler = (logfiles.max_name_indent_len - 2 * logfile["indent"] -
                  len(logfile["name"]) + 1)

        if "path" in logfile:
            selected = (' selected="selected"' if logfile["path"] in fileselect
                        else "")
            style = ("" if logfile["readable"] else
                     ' style="text-decoration:line-through"')
            result += (f'<option value="{html.escape(logfile["path"])}"'
                       f'{selected}{style}>{"&nbsp;" * 2 * logfile["indent"]}'
                       f'{html.escape(logfile["name"])}{"&nbsp;" * filler}'
                       f' {"&nbsp;" * (8 - len(logfile["size_human"]))}'
                       f'{logfile["size_human"]}&nbsp;&nbsp;'
                       f'{logfile["mtime_human"]}&nbsp;</option>\n')
        else:
            result += (f'<option>{"&nbsp;" * 2 * logfile["indent"]}'
                       f'{html.escape(logfile["name"])}</option>\n')

    result += "</optgroup>\n"

result += (f"""</select>
</div>

<div class="bar" id="barm"></div>

<div style="font-family: monospace; vertical-align: top; overflow: scroll">
{"".join(html_lines)}
</div>

<div class="sbb" id="filestatus">
{logfiles.shown_files}/{logfiles.total_files} files
({bytes_pretty(logfiles.shown_bytes)}/{bytes_pretty(logfiles.total_bytes)}),
{logfiles.shown_dirs}/{logfiles.total_dirs} folders shown
</div>

<div class="bar"></div>

<div class="sbb">
{html_status}
<span style="float:right">
Server local time: {datetime.datetime.now().strftime(DATETIME_FMT)}
</span>
</div>

</div>
</form>
"""
"""<script>
document.querySelectorAll(".bar").forEach(function (elem) {
  elem.onmousedown = function (ev) {
    var fileFilter = document.getElementById("filefilter");
    var fileSelect = document.getElementById("fileselect");
    var fileStatus = document.getElementById("filestatus");

    var startWidth = Math.max(fileFilter.offsetWidth, fileSelect.offsetWidth);
    startWidth = Math.max(startWidth, fileStatus.offsetWidth);

    var startX = ev.clientX;

    document.onmouseup = function (ev) {
      document.onmouseup = null;
      document.onmousemove = null;
    };

    document.onmousemove = function (ev) {
      var width = startWidth + ev.clientX - startX;
      if (width >= 20) {
        width = width + "px";
        fileFilter.style.width = width;
        fileSelect.style.width = width;
        fileStatus.style.width = width;
      }
    };
  };
});

function toggle (elemId)
{
  var elem = document.getElementById(elemId);
  if (elem) {
    elem.checked = !elem.checked;
  }
}

function toggleCssClass (elemId, className)
{
  var elem = document.getElementById(elemId);
  if (elem) {
    var display = (elem.checked ? "inline" : "none");
    var elems = document.getElementsByClassName(className);
    for (i = 0; i < elems.length; i++) {
      elems[i].style.display = display;
    }
  }
}

</script>
</body>
</html>""")

print("Content-Type: text/html; charset=utf-8\n"
      f'Content-Length: {len(result.encode("utf-8"))}\n')
print(result, end="")

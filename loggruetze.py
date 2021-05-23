#!/usr/bin/env python3

LOGDIRS = ("/var/log",)

import sys, os, re, json

def traverse_logdir(logdir, subdir=""):
    logfiles = {}

    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except Exception as e:
        return logfiles

    for entry in entries:
        relname = os.path.join(subdir, entry.name)

        if entry.is_dir(follow_symlinks=False):
            logfiles[entry.path] = {
                "name"   : entry.name,
                "childs" : traverse_logdir(logdir, relname)
            }
        elif entry.is_file(follow_symlinks=False):
            stat = entry.stat(follow_symlinks=False)
            logfiles[entry.path] = {
                "name"  : entry.name,
                "mtime" : stat.st_mtime,
                "size"  : stat.st_size
            }

    return logfiles


logfiles = {}
for logdir in LOGDIRS:
    logfiles[logdir] = traverse_logdir(logdir)

request_method = os.environ.get("REQUEST_METHOD", "GET")

if request_method == "POST":
    content_length = int(os.environ.get("CONTENT_LENGTH", "0"))
    query = json.loads(sys.stdin.read(content_length))
    action = query.get("action", "")

    if action == "logfiles":
        result = logfiles
    elif action == "search":
        result = { "error" : "not yet implemented" }
    else:
        result = { "error" : "unknown action" }

    content_type = "application/json"
    result = json.dumps(result)
else:
    content_type = "text/html; charset=utf-8"
    result = """<html>
<head>
<title>Loggrütze</title>
</head>
<body>
<p>Loggrütze</p>
<pre id="test">
</pre>
<script>
x = new XMLHttpRequest();
x.onreadystatechange = function () {
  if ((x.readyState == 4) && (x.status == 200)) {
    document.getElementById("test").textContent = x.response;
  }
};
x.open("POST", "");
x.timeout = 10000;
x.send(JSON.stringify({ action: "logfiles" }));
</script>
</body>
</html>"""

print("Content-Type: %s\nContent-Length: %i\n" % (content_type, len(result)))
print(result)

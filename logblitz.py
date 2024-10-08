#!/usr/bin/env -S-P/usr/local/bin:/usr/bin:/bin python3

import time
load_time = time.perf_counter()

import sys
import os
import datetime
import html
import urllib.parse
import gzip
import bz2
import configparser
import lzma
import collections
import http.cookies
import codecs
try:
    import re2 as re
    RE_MODULE = "re2"
except ModuleNotFoundError:
    import re
    RE_MODULE = "re"

VERSION = "21"
COOKIE_MAX_AGE = 365*24*60*60
DATETIME_FMT = "%Y/%m/%d %H:%M:%S"
HTML_CHARSET = "utf-8"


class LogFiles:
    def __init__(self):
        self.dir2files = {}
        self.max_name_indent_len = 0
        self.shown_files = 0
        self.total_files = 0
        self.shown_bytes = 0
        self.total_bytes = 0
        self.shown_dirs = 0
        self.total_dirs = 0


def bytes_pretty(filesize):
    if filesize < 1024:
        return f"{filesize}B"
    for suffix in ("K", "M", "G", "T"):
        filesize /= 1024
        if filesize < 1024:
            break
    return f"{filesize:.2f}{suffix}"


def logfile_number_sorter(entry):
    m = re.search(r"(?i:\.(\d+)(\.(bz2|gz|xz))?)$", entry.name)
    return int(m.group(1)) if m else -1


def logfile_prefix_sorter(entry):
    m = re.match(r"(?i:(.*)\.(\d+)(\.(bz2|gz|xz))?)$", entry.name)
    return m.group(1) if m else entry.name


def traverse_logdir(logdir, cfgdirfilter_re, cfgfilefilter_re, filefilter_re,
                    logfiles, showdotfiles, showunreadables,
                    subdir="", indent=0):
    try:
        entries = os.scandir(os.path.join(logdir, subdir))
    except OSError:
        return False

    if not showdotfiles:
        entries = filter(lambda entry: not entry.name.startswith("."),
                         entries)
    entries = sorted(entries, key=logfile_number_sorter)
    entries = sorted(entries, key=logfile_prefix_sorter)

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
                                          showunreadables, relname,
                                          indent + 1)
            if found_files:
                logfiles.shown_dirs += 1
                dir2files.insert(cnt, {
                    "name":   entry.name + os.path.sep,
                    "indent": indent
                })

                candid_name_indent_len = len(entry.name) + 1 + 2 * indent
                if candid_name_indent_len > logfiles.max_name_indent_len:
                    logfiles.max_name_indent_len = candid_name_indent_len

        elif (entry.is_file(follow_symlinks=False) and
              cfgfilefilter_re.search(entry.name)):
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue

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
                    "name":        entry.name,
                    "readable":    readable,
                    "indent":      indent,
                    "path":        entry.path,
                    "mtime":       stat.st_mtime,
                    "mtime_human": mtime_human,
                    "size":        stat.st_size,
                    "size_human":  size_human
                })

                candid_name_indent_len = len(entry.name) + 2 * indent
                if candid_name_indent_len > logfiles.max_name_indent_len:
                    logfiles.max_name_indent_len = candid_name_indent_len

    return found_files


def search(charset, logdirs, logfiles, fileselect, query, reverse, ignorecase,
           invert, regex, before, after, limitlines, limitmemory):
    html_lines = []
    shown_lines = 0
    shown_bytes = 0
    matching_lines = 0
    matching_bytes = 0
    total_lines = 0
    total_bytes = 0
    num_logfiles = 0

    limit_lines = int(limitlines) if limitlines else sys.maxsize
    limit_bytes = int(limitmemory) * 1024**2 if limitmemory else sys.maxsize
    before = int(before) if before else 0
    after = int(after) if after else 0

    if invert:
        def eval_matches(matches, line):
            return len(matches) <= 0, ((0, len(line)),)
    else:
        def eval_matches(matches, _):
            return len(matches) > 0, matches

    if regex and query:
        try:
            query_re = (re.compile(f"(?i:{query})") if ignorecase else
                        re.compile(query))
        except Exception as e:
            return "", (f"Error: Invalid regex: {html.escape(str(e))}",)

        def matcher(line):
            matchee = query_re.search(line, 0)
            while matchee:
                yield matchee.span()
                matchee = query_re.search(
                    line,
                    matchee.end() + int(matchee.end() == matchee.start())
                )
    elif query:
        fold_string = str.lower if ignorecase else str
        query_folded = fold_string(query)

        def matcher(line):
            line_folded = fold_string(line)
            start = line_folded.find(query_folded)
            while start >= 0:
                end = start + len(query_folded)
                yield start, end
                start = line_folded.find(query_folded, end)
    else:
        def matcher(_):
            yield 0, 0

    # logfiles.dir2files is a dictionary whose keys reflect any logdir given
    # in the config file
    # each value is sorted list of dictionaries, where each dictionary denotes
    # a logfile or a subdirectory, depending on whether the key "path" is set
    # or not, respectively
    # the inner filter() emits only those logdirs that contain logfiles
    # the outer filter() emits only those logfiles that the user asked for
    for num_logfiles, logfile in enumerate(filter(
        lambda logfile: "path" in logfile and logfile["path"] in fileselect,
        [logfile for logdir in filter(
            lambda logdir: logdir in logfiles.dir2files, logdirs)
         for logfile in logfiles.dir2files[logdir]]), 1):

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

        b4buf = collections.deque()
        lines = collections.deque()
        num_after = after
        line_number = 0

        for line_number, raw_line in enumerate(fp, 1):
            len_raw_line = len(raw_line)
            line = raw_line.decode(charset, errors="replace")

            total_bytes += len_raw_line
            found, matches = eval_matches(list(matcher(line)), line)

            if not found:
                if num_after < after:
                    lines.append((line, [], len_raw_line, line_number))
                    num_after += 1
                else:
                    b4buf.append((line, [], len_raw_line, line_number))
                    while len(b4buf) > before:
                        b4buf.popleft()
                continue

            matching_lines += 1
            matching_bytes += len_raw_line

            while (reverse and len(lines) > 0 and 
                   (limit_lines <= shown_lines or
                    limit_bytes <= shown_bytes)):
                shown_lines -= 1
                tmpline = lines.popleft()
                shown_bytes -= tmpline[2]

            if (limit_lines > shown_lines and
                    limit_bytes > shown_bytes):
                for tmpline in b4buf:
                    shown_lines += 1
                    shown_bytes += tmpline[2]
                    lines.append(tmpline)
                b4buf.clear()
                num_after = 0
                shown_lines += 1
                shown_bytes += len_raw_line
                lines.append((line, matches, len_raw_line, line_number))

        if reverse:
            lines.reverse()

        total_lines += line_number
        len_max_line_number = len(str(line_number))

        html_lines += ['<div class="lf">',
                       logfile["path"],
                       "</div>"]
        for line in lines:
            line, matches, line_number = line[0], line[1], line[3]
            html_line = ['<div class="sl"><span class="ln">',
                         str(line_number).rjust(len_max_line_number),
                         "</span>"]
            oldend = 0
            for m in matches:
                html_line += [html.escape(line[oldend:m[0]]),
                              '<span class="sr">',
                              html.escape(line[m[0]:m[1]]),
                              "</span>"]
                oldend = m[1]
            html_line += [html.escape(line[oldend:]),
                          "</div>"]
            html_lines += ["".join(html_line)]

    html_status = (
        f"""<span{' class="red"' if shown_lines >= limit_lines else ""}>"""
        f"{shown_lines}</span> (<span"
        f"""{' class="red"' if shown_bytes >= limit_bytes else ""}>"""
        f"{bytes_pretty(shown_bytes)}</span>) lines shown, "
        f"{matching_lines} ({bytes_pretty(matching_bytes)}) matching, "
        f"{total_lines} ({bytes_pretty(total_bytes)}) total lines in "
        f'{num_logfiles} selected log file{"" if num_logfiles == 1 else "s"}'
    )

    return html_status, html_lines


def re_compile_with_error(filter_text):
    try:
        filter_re = re.compile(filter_text)
    except Exception as e:
        return str(e), None

    return None, filter_re


def pocgi(environ, is_wsgi):
    class Form(dict):
        def getvalue(self, key, default):
            value = self.get(key, None)
            return value[0] if value else default

        def getlist(self, key):
            return self.get(key, [])

    clen = environ.get("CONTENT_LENGTH", None)
    if not type(clen) is str or not clen.isdecimal():
        return {}

    clen = int(clen)
    if is_wsgi:
        indata = environ["wsgi.input"].read(clen)
    else:
        indata = open(sys.stdin.fileno(), "rb").read(clen)

    return Form(urllib.parse.parse_qs(indata.decode(HTML_CHARSET),
                                      encoding=HTML_CHARSET))


def logblitz(environ, is_wsgi, start_time):
    rawcookies = http.cookies.SimpleCookie()
    try:
        rawcookies.load(environ.get("HTTP_COOKIE", ""))
    except http.cookies.CookieError:
        pass

    remote_user = environ.get("REMOTE_USER")
    sane_ruser = re.sub(r"[^a-zA-Z0-9.-]", "_",
                        (remote_user if remote_user else ""))
    is_post = (environ.get("REQUEST_METHOD", "GET") == "POST")

    if is_post:
        form = pocgi(environ, is_wsgi)
        role = form.getvalue("role", "")
    elif remote_user and "role_%s" % sane_ruser in rawcookies:
        role = rawcookies["role_%s" % sane_ruser].value
    else:
        role = ""

    if role:
        csuffix = "_%s" % role
    elif remote_user:
        csuffix = "_%s" % sane_ruser
    else:
        csuffix = ""

    cookies = {x[0].removesuffix(csuffix): x[1].value
               for x in rawcookies.items()
               if x[0].endswith(csuffix)}

    rawcookies.clear()

    configfile = environ.get("SCRIPT_FILENAME", None)
    if configfile:
        configfile = os.path.dirname(configfile)
    elif is_wsgi:
        configfile = os.getcwd()
    else:
        configfile = os.path.dirname(sys.argv[0])

    configfile = os.path.join(configfile, os.pardir, "etc", "logblitz.ini")

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(configfile)

    roles = []
    roles_error = None
    if remote_user:
        for section, options in config.items():
            add_section = None
            for k, v in options.items():
                if k == "users":
                    err, users_re = re_compile_with_error(v)
                    if err:
                        roles_error = "[%s]: %s: %s: %s" % (section, k, v,
                                                            str(err))
                        add_section = False
                    else:
                        add_section = ((add_section is None or add_section) and
                                       users_re.search(remote_user))
                elif k.startswith("env_"):
                    envname = k.removeprefix("env_")
                    err, env_re = re_compile_with_error(v)
                    if err:
                        roles_error = "[%s]: %s: %s: %s" % (section, k, v,
                                                            str(err))
                        add_section = False
                    else:
                        add_section = ((add_section is None or add_section) and
                                       envname in environ and
                                       env_re.search(environ[envname]))
            if add_section:
                roles.append(section)

    if role and role in roles:
        config_section = role
    elif remote_user:
        config_section = remote_user
    else:
        config_section = "DEFAULT"

    if config.has_option(config_section, "logdirs"):
        logdirs = config.get(config_section, "logdirs").split(os.path.pathsep)
    else:
        logdirs = []

    if config.has_option(config_section, "charset"):
        charset = config.get(config_section, "charset")
    else:
        charset = ""

    if config.has_option(config_section, "dirfilter"):
        cfgdirfilter = config.get(config_section, "dirfilter")
    else:
        cfgdirfilter = ""

    if config.has_option(config_section, "filefilter"):
        cfgfilefilter = config.get(config_section, "filefilter")
    else:
        cfgfilefilter = ""

    if config.has_option(config_section, "logout_url"):
        logout_url = config.get(config_section, "logout_url")
    else:
        logout_url = ""

    if config.has_option(config_section, "logout_option"):
        logout_option = config.get(config_section, "logout_option")
    else:
        logout_option = ""

    if config.has_option(config_section, "nice_username_env"):
        nice_username_env = config.get(config_section, "nice_username_env")
    else:
        nice_username_env = ""

    query = cookies["query"] if "query" in cookies else ""
    reverse = "reverse" in cookies and cookies["reverse"] == "True"
    ignorecase = "ignorecase" in cookies and cookies["ignorecase"] == "True"
    invert = "invert" in cookies and cookies["invert"] == "True"
    regex = "regex" in cookies and cookies["regex"] == "True"
    showlinenumbers = ("showlinenumbers" in cookies and
                       cookies["showlinenumbers"] == "True")
    wraplines = ("wraplines" in cookies and
                 cookies["wraplines"] == "True")
    showdotfiles = ("showdotfiles" in cookies and
                    cookies["showdotfiles"] == "True")
    showunreadables = ("showunreadables" in cookies and
                       cookies["showunreadables"] == "True")
    charset = cookies["charset"] if "charset" in cookies else charset
    filefilter = cookies["filefilter"] if "filefilter" in cookies else ""
    tmp = cookies["limitlines"] if "limitlines" in cookies else "1000"
    if tmp == "" or tmp.isnumeric():
        limitlines = tmp
    tmp = cookies["limitmemory"] if "limitmemory" in cookies else "1"
    if tmp == "" or tmp.isnumeric():
        limitmemory = tmp
    tmp = cookies["before"] if "before" in cookies else "0"
    if tmp == "" or tmp.isnumeric():
        before = tmp
    tmp = cookies["after"] if "after" in cookies else "0"
    if tmp == "" or tmp.isnumeric():
        after = tmp
    fileselect = (cookies["fileselect"].split(os.pathsep)
                  if "fileselect" in cookies else [])
    oldfileselect = [c for c in cookies.keys()
                     if c.startswith("fileselect") and c != "fileselect"]
    autorefresh = "autorefresh" in cookies and cookies["autorefresh"] == "True"
    tmp = cookies["refreshsec"] if "refreshsec" in cookies else ""
    refreshsec = tmp if tmp.isnumeric() else "2"

    if is_post:
        cookies.clear()

        oldrole = form.getvalue("oldrole", "")
        if role == oldrole:
            query = form.getvalue("query", "")
            reverse = "reverse" in form
            ignorecase = "ignorecase" in form
            invert = "invert" in form
            regex = "regex" in form
            showlinenumbers = "showlinenumbers" in form
            wraplines = "wraplines" in form
            showdotfiles = "showdotfiles" in form
            showunreadables = "showunreadables" in form
            charset = form.getvalue("charset", "")
            filefilter = form.getvalue("filefilter", "")
            fileselect = form.getlist("fileselect")
            tmp = form.getvalue("limitlines", "")
            if tmp == "" or tmp.isnumeric():
                limitlines = tmp
            tmp = form.getvalue("limitmemory", "")
            if tmp == "" or tmp.isnumeric():
                limitmemory = tmp
            tmp = form.getvalue("before", "")
            if tmp == "" or tmp.isnumeric():
                before = tmp
            tmp = form.getvalue("after", "")
            if tmp == "" or tmp.isnumeric():
                after = tmp
            autorefresh = "autorefresh" in form
            tmp = form.getvalue("refreshsec", "")
            refreshsec = tmp if tmp.isnumeric() else "2"

            cookies["query"] = query
            cookies["reverse"] = reverse
            cookies["ignorecase"] = ignorecase
            cookies["invert"] = invert
            cookies["regex"] = regex
            cookies["before"] = before
            cookies["after"] = after
            cookies["showlinenumbers"] = showlinenumbers
            cookies["wraplines"] = wraplines
            cookies["showdotfiles"] = showdotfiles
            cookies["showunreadables"] = showunreadables
            cookies["charset"] = charset
            cookies["filefilter"] = filefilter
            cookies["limitlines"] = limitlines
            cookies["limitmemory"] = limitmemory
            cookies["fileselect"] = os.pathsep.join(fileselect)
            cookies["autorefresh"] = autorefresh
            cookies["refreshsec"] = refreshsec

            for k, v in cookies.items():
                rawcookies["%s%s" % (k, csuffix)] = v

        if remote_user:
            rawcookies["role_%s" % sane_ruser] = role

    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "ISO-8859-1"

    is_https = (environ.get("wsgi.url_scheme", "http") == "https" or
                environ.get("HTTPS", "off") == "on")
    for c in rawcookies.keys():
        rawcookies[c]["Max-Age"] = COOKIE_MAX_AGE
        rawcookies[c]["SameSite"] = "Lax"
        rawcookies[c]["HttpOnly"] = c not in (
            "showlinenumbers", "showlinenumbers%s" % (csuffix,),
            "wraplines", "wraplines%s" % (csuffix,),
            "autorefresh", "autorefresh%s" % (csuffix,),)
        rawcookies[c]["Secure"] = is_https
    for c in oldfileselect:
        rawcookies[c] = ""
        rawcookies[c]["Max-Age"] = 0

    if len(str(rawcookies)) > 3072:
        for k in [k for k in rawcookies.keys() if k.startswith("fileselect")]:
            rawcookies.pop(k)

    error_ff, filefilter_re = re_compile_with_error(filefilter)
    error_cfgff, cfgfilefilter_re = re_compile_with_error(cfgfilefilter)
    error_cfgdf, cfgdirfilter_re = re_compile_with_error(cfgdirfilter)

    logfiles = LogFiles()

    html_status = ""
    html_lines = []

    if roles_error:
        html_lines = ("Error: Invalid roles in INI file:",
                      html.escape(roles_error))
    elif not cfgdirfilter_re:
        html_lines = ("Error: Invalid dirfilter in INI file:",
                      html.escape(cfgdirfilter), ":",
                      html.escape(str(error_cfgdf)))
    elif not cfgfilefilter_re:
        html_lines = ("Error: Invalid filefilter in INI file:",
                      html.escape(cfgfilefilter), ":",
                      html.escape(str(error_cfgff)))
    elif not filefilter_re:
        html_lines = ("Error: Invalid filefilter:",
                      html.escape(filefilter), ":",
                      html.escape(str(error_ff)))
    else:
        for logdir in logdirs:
            logfiles.total_dirs += 1

            if logdir.endswith(os.path.sep):
                logdir = logdir[:-1]

            if traverse_logdir(logdir, cfgdirfilter_re, cfgfilefilter_re,
                               filefilter_re, logfiles, showdotfiles,
                               showunreadables):
                logfiles.shown_dirs += 1

        if (is_post and (role == oldrole)) or autorefresh:
            html_status, html_lines = search(charset, logdirs, logfiles,
                                             fileselect, query, reverse,
                                             ignorecase, invert, regex,
                                             before, after, limitlines,
                                             limitmemory)

    result = ["""<!DOCTYPE html>
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
.sl {
  text-wrap: """ +
           ("wrap" if wraplines else "nowrap") +
           """;
}
.sr {
  font-weight: bold;
  background-color: yellow;
}
.ln {
  margin-right: 2em;
  -webkit-user-select: none;
  display: """ +
              ("inline" if showlinenumbers else "none") +
              ''';
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
</head>
<body>
<form accept-charset="''' +
              HTML_CHARSET +
              '''" method="POST">
<div style="height:100%; display:grid; grid-template-rows:auto 1fr auto;
 grid-template-columns:auto 12px 1fr">

<div class="sbt" id="filefilterbox">
<input type="text" name="filefilter" id="filefilter" value="''' +
              html.escape(filefilter) +
              '''" placeholder="Filter filenames..." style="width:20em"
 title="Use a regular expression to filter shown filenames">
<span class="box">
<input type="checkbox" name="showdotfiles" style="margin-left:10px" ''' +
              ('checked="checked" ' if showdotfiles else "") +
              '''id="showdotfiles"
 title="Show files and directories which names start with a dot">
<span title="Show files and directories which names start with a dot"
 onclick="toggle('showdotfiles')">Show dot files</span>
</span>
<span class="box">
<input type="checkbox" name="showunreadables" style="margin-left:10px" ''' +
              ('checked="checked" ' if showunreadables else "") +
              '''id="showunreadables"
 title="Show files and directories which are not accessible">
<span title="Show files and directories which are not accessible"
 onclick="toggle('showunreadables')">Show inaccessible files</span>
</span>
</div>

<div class="bar"></div>

<div class="sbt">
<input type="text" name="query" id="query" value="''' +
              html.escape(query) +
              '''" placeholder="Search log entries..." style="width:30em"
 title="Enter an expression to search log entries">
<input type="submit" name="search" value="Search" style="margin-left:10px"
 id="searchsubmit">
<span class="box">
<input type="checkbox" name="reverse" style="margin-left:10px" ''' +
              ('checked="checked" ' if reverse else "") +
              '''id="reverse"
 title="Display latest log entries first">
<span title="Display latest log entries first"
 onclick="toggle('reverse')">Reverse</span>
</span>
<span class="box">
<input type="checkbox" name="ignorecase" style="margin-left:10px" ''' +
              ('checked="checked" ' if ignorecase else "") +
              '''id="ignorecase"
 title="Search log entries regardless of case">
<span title="Search log entries regardless of case"
 onclick="toggle('ignorecase')">Ignore case</span>
</span>
<span class="box">
<input type="checkbox" name="invert" style="margin-left:10px" ''' +
              ('checked="checked" ' if invert else "") +
              '''id="invert"
 title="Show log entries not matching the search expression">
<span title="Show log entries not matching the search expression"
 onclick="toggle('invert')">Invert
</span>
</span>
<span class="box">
<input type="checkbox" name="regex" style="margin-left:10px" ''' +
              ('checked="checked" ' if regex else "") +
              '''id="regex"
 title="Assume search expression is a regular expression">
<span title="Assume search expression is a regular expression"
 onclick="toggle('regex')">Regular expression</span>
</span>
<span class="box">
<input type="checkbox" name="showlinenumbers" style="margin-left:10px" ''' +
              ('checked="checked" ' if showlinenumbers else "") +
              '''id="showlinenumbers"
 title="Show line numbers"
 onchange="toggleHiddenClass('showlinenumbers', 'ln');
           setCookie('showlinenumbers', 'showlinenumbers');">
<span title="Show line numbers"
 onclick="toggle('showlinenumbers');
          toggleHiddenClass('showlinenumbers', 'ln');
          setCookie('showlinenumbers',
                    'showlinenumbers');">Line numbers</span>
</span>
<span class="box">
<input type="checkbox" name="wraplines" style="margin-left:10px" ''' +
              ('checked="checked" ' if wraplines else "") +
              '''id="wraplines"
 title="Wrap lines"
 onchange="toggleTextWrap('wraplines', 'sl');
           setCookie('wraplines', 'wraplines');">
<span title="Wrap lines"
 onclick="toggle('wraplines');
          toggleTextWrap('wraplines', 'sl');
          setCookie('wraplines',
                    'wraplines');">Wrap lines</span>
</span>
<span class="box">
<span title="Show this # of lines before each matching line"
 style="margin-left:10px">Before:</span>
<input type="text" name="before" id="before" value="''' +
              html.escape(before) +
              '''"
 title="Show this # of lines before each matching line" style="width:1em">
</span>
<span class="box">
<span title="Show this # of lines after each matching line"
 style="margin-left:10px">After:</span>
<input type="text" name="after" id="after" value="''' +
              html.escape(after) +
              '''"
 title="Show this # of lines after each matching line" style="width:1em">
</span>
<span class="box">
<span title="Charset of logfiles" style="margin-left:10px">Charset:</span>
<input type="text" name="charset" id="charset" value="''' +
              html.escape(charset) +
              '''"
 title="Charset of logfiles" style="width:7em">
</span>
<span class="box">
<span title="Limit search results" style="margin-left:10px">Limits:</span>
<input type="text" name="limitlines" id="limitlines" value="''' +
              html.escape(limitlines) +
              '''"
 title="Limit search results to this number of lines"
 style="text-align:right; width:4em">
<span title="Limit search results to this number of lines">lines</span>
<input type="text" name="limitmemory" id="limitmemory" value="''' +
              html.escape(limitmemory) +
              '''"
 title="Limit search results to this amount of memory"
 style="text-align:right; width:3em">
<span title="Limit search results to this amount of memory">MiB</span>
</span>
<span class="box">
<input type="checkbox" name="autorefresh" style="margin-left:10px" ''' +
              ('checked="checked" ' if autorefresh else "") +
              '''id="autorefresh"
 title="Autorefresh search"
 onchange="setCookie('autorefresh', 'autorefresh');
           autoRefresh();">
<span title="Autorefresh search"
 onclick="toggle('autorefresh');
          setCookie('autorefresh', 'autorefresh');
          autoRefresh();">Refresh</span>
<input type="text" name="refreshsec" value="''' +
              html.escape(refreshsec) +
              '''" id="refreshsec"
 title="Autorefresh search every given second(s)"
 style="text-align:right; width:2em">
</span>
''']

    if logout_url:
        if nice_username_env in environ:
            nice_username = environ[nice_username_env]
        else:
            nice_username = remote_user

        result += ['<span style="float:right; margin-right:5px"><a href="' +
                   logout_url +
                   '" title="Logout' +
                   (html.escape(" user %s" % (nice_username,))
                    if nice_username else "") +
                   '"',
                   logout_option if logout_option else "",
                   ">Logout</a></span>"]

    result += ["</div>",
               "",
               '<div id="fileselectbox">',
               '<select name="fileselect" id="fileselect" multiple',
               ' style="font-family:monospace; height:100%; width:100%">']

    logfiles_selected_files = 0
    logfiles_selected_bytes = 0

    for logdir in sorted(logfiles.dir2files):
        result += ['<optgroup label="' +
                   html.escape(logdir) +
                   os.path.sep +
                   '">']

        for logfile in logfiles.dir2files[logdir]:
            filler = (logfiles.max_name_indent_len - 2 * logfile["indent"] -
                      len(logfile["name"]) + 1)

            if "path" in logfile:
                if logfile["path"] in fileselect:
                    selected = ' selected="selected"'
                    logfiles_selected_files += 1
                    logfiles_selected_bytes += logfile["size"]
                else:
                    selected = ""

                style = ("" if logfile["readable"] else
                         ' style="text-decoration:line-through"')
                result += ['<option value="' +
                           html.escape(logfile["path"]) +
                           '"' +
                           selected +
                           style +
                           ">" +
                           "&nbsp;" * 2 * logfile["indent"] +
                           html.escape(logfile["name"]) +
                           "&nbsp;" * filler +
                           " " +
                           "&nbsp;" * (8 - len(logfile["size_human"])) +
                           logfile["size_human"] +
                           "&nbsp;&nbsp;" +
                           logfile["mtime_human"] +
                           "&nbsp;</option>"]
            else:
                result += ["<option>" +
                           "&nbsp;" * 2 * logfile["indent"] +
                           html.escape(logfile["name"]) +
                           "</option>"]

        result += ["</optgroup>"]

    result += ["</select>",
               "</div>",
               '<div class="bar" id="barm"></div>',
               '<div style="font-family: monospace; vertical-align: top;' +
               ' overflow: scroll">']
    result += html_lines
    result += ["</div>",
               '<div class="sbb" id="filestatusbox">',
               str(logfiles_selected_files) + "/" +
               str(logfiles.shown_files) + "/" +
               str(logfiles.total_files),
               "files",
               "(" +
               bytes_pretty(logfiles_selected_bytes) + "/" +
               bytes_pretty(logfiles.shown_bytes) + "/" +
               bytes_pretty(logfiles.total_bytes) + "),",
               str(logfiles.shown_dirs) + "/" +
               str(logfiles.total_dirs),
               "folders shown</div>",
               '<div class="bar"></div>',
               '<div class="sbb">',
               html_status,
               '<span style="float:right">',
               '<span title="Role" style="margin-right:10px">Role:',
               '<select name="role" id="role">',
               "<option></option>"]

    for r in sorted(roles):
        result += ["<option" + (' selected="selected"' if r == role else "") +
                   ">",
                   html.escape(r),
                   "</option>"]

    result += ["</select>",
               "</span>",
               '<span style="margin-right:10px">',
               "Run time:",
               "%.1fs" % (time.perf_counter() - start_time,),
               "</span>",
               '<span style="margin-right:10px">',
               "Regex module:",
               RE_MODULE,
               "</span>",
               '<span style="margin-right:10px">',
               "Server local time:",
               datetime.datetime.now().strftime(DATETIME_FMT),
               "</span>",
               '<span style="margin-right:5px">',
               '<a href="https://ogris.de/logblitz/"',
               'target="_blank">About LogBlitz',
               VERSION + "...</a>",
               "</span>",
               "</span>",
               "</div>",
               "</div>",
               '<input type="hidden" name="oldrole" value="' +
               html.escape(role) + '">',
               "</form>",
               """<script>
document.querySelectorAll(".bar").forEach(function (elem) {
  elem.onmousedown = function (ev) {
    var fileFilter = document.getElementById("filefilterbox");
    var fileSelect = document.getElementById("fileselectbox");
    var fileStatus = document.getElementById("filestatusbox");

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
  if (elemId == "autorefresh" ||
      !document.getElementById("autorefresh").checked) {
    elem.checked = !elem.checked;
  }
}

function toggleHiddenClass (elemId, className)
{
  var display = (document.getElementById(elemId).checked ? "inline" : "none");
  var elems = document.getElementsByClassName(className);
  for (i = 0; i < elems.length; i++) {
    elems[i].style.display = display;
  }
}

function toggleTextWrap (elemId, className)
{
  var wrapmode = (document.getElementById(elemId).checked ? "wrap" : "nowrap");
  var elems = document.getElementsByClassName(className);
  for (i = 0; i < elems.length; i++) {
    elems[i].style.textWrap = wrapmode;
  }
}

function setCookie (elemId, cookieName)
{
  var show = (document.getElementById(elemId).checked ? "True" : "False");
  document.cookie = cookieName""" +
             " + '" + html.escape(csuffix) +
             "=' + show + '; max-age=" +
             str(COOKIE_MAX_AGE) + "; SameSite=Lax;" +
             (" Secure;" if is_https else "") + """';
}

var timeout = false;

function autoRefresh ()
{
  var autorefresh = document.getElementById("autorefresh").checked;
  if (autorefresh) {
    timeout = window.setTimeout(function () {
      window.location.search = "";
    }, """ + refreshsec + """ * 1000);
  } else if (timeout) {
    window.clearTimeout(timeout);
    timeout = false;
  }

  new Array("query",
            "searchsubmit",
            "reverse",
            "ignorecase",
            "invert",
            "regex",
            "showlinenumbers",
            "wraplines",
            "showdotfiles",
            "showunreadables",
            "charset",
            "filefilter",
            "fileselect",
            "limitlines",
            "limitmemory",
            "before",
            "after",
            "refreshsec",
            "role").forEach(function (id) {
    document.getElementById(id).disabled = autorefresh;
});
}

autoRefresh();
</script>
</body>
</html>"""]

    result = "\n".join(result)
    bresult = result.encode(HTML_CHARSET)
    headers = [
        ("Content-Type", "text/html; charset=" + HTML_CHARSET),
        ("Content-Length", str(len(bresult)))
    ] + [tuple(str(cookie).split(": ", 1)) for cookie in rawcookies.values()]

    return headers, bresult if is_wsgi else result


def application(environ, start_response):
    headers, bresult = logblitz(environ, True, time.perf_counter())
    start_response("200 Ok", headers)

    return [bresult]


if __name__ == "__main__":
    headers, result = logblitz(os.environ, False, load_time)
    print("Status: 200 Ok")
    for hdr in headers:
       print(": ".join(hdr))
    print()
    print(result)

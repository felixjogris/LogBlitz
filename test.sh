#!/bin/sh

tempdir=`mktemp -d`
[ ! -d "$tempdir" ] && exit 1

mkdir "$tempdir/cgi-bin" "$tempdir/etc" "$tempdir/logs" "$tempdir/logs2" || exit 1

cp -aiv logblitz.py "$tempdir/cgi-bin/" || exit 1

echo "[DEFAULT]
logdirs = $tempdir/logs:$tempdir/logs2" > "$tempdir/etc/logblitz.ini" || exit 1

echo "A line before.
This is a log entry.
A line after." > "$tempdir/logs/webserver.log" || exit 1

echo "A line before.
This is a log entry, too, but in another log file.
A line after." > "$tempdir/logs2/webserver2.log" || exit 1

cd "$tempdir" || exit 1

python3 -m http.server --cgi --bind 127.0.0.1 8002 &
pid=$!
python3 -m webbrowser -t "http://127.0.0.1:8002/cgi-bin/logblitz.py"
read
kill $pid

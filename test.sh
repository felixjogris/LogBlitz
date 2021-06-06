#!/bin/sh

mkdir cgi-bin
ln -s ../logblitz.py cgi-bin/
python3 -m http.server --cgi --bind 127.0.0.1 8002 &
pid=$!
python3 -m webbrowser -t "http://127.0.0.1:8002/cgi-bin/logblitz.py"
read
kill $pid
rm cgi-bin/logblitz.py
rmdir cgi-bin

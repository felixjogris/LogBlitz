#!/bin/sh

mkdir cgi-bin
ln -s ../loggruetze.py cgi-bin/
python3 -m http.server --cgi --bind 127.0.0.1 8002 &
pid=$!
python3 -m webbrowser -t "http://127.0.0.1:8002/cgi-bin/loggruetze.py"
read
kill $pid
rm cgi-bin/loggruetze.py
rmdir cgi-bin

#!/bin/sh

mkdir /tmp/logs /tmp/logs2

cat >/tmp/logs/webserver.log <<EOF
A line before.
This is a log entry.
A line after.
EOF

cat >/tmp/logs2/webserver2.log <<EOF
A line before.
This is a log entry, too, but in another log file.
A line after.
EOF

mv -iv /usr/local/www/etc/logblitz.ini /usr/local/www/etc/logblitz.ini.orig
cat >/usr/local/www/etc/logblitz.ini <<EOF
[DEFAULT]
logdirs = /tmp/logs:/tmp/logs2
charset = utf-8
EOF

read -p "Make screenshot, then press [Enter]" BLA

mv -v /usr/local/www/etc/logblitz.ini.orig /usr/local/www/etc/logblitz.ini

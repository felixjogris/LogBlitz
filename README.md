# LogBlitz

LogBlitz is a CGI script to search through your (sys-)log files. It is written in Python 3, and aims to be a webbased alter ego of grep, zgrep, bzgrep, xzgrep, and so on. You can configure multiple directories that contain logfiles, and you can give each HTTP authenticated user an individual set of log directories.
LogBlitz does not interpret the log entries in any way, but sees them just as a bunch of text lines. No additional modules need to be installed as a default installation of Python 3.8 or 3.9 is sufficient. In order to read XZ compressed files, you need to have the xz binary installed, e.g. /usr/bin/xz on most Linux systems or on FreeBSD. The webinterface uses JavaScript just for the moveable divider between the filetree and the logview area.

## Screenshot

## Installation
1. Put logblitz.py to the cgi-bin/ directory on you webserver, and make it executable
2. Optionally, place favicon.ico to the htdocs/ directory
3. Create etc/logblitz.ini, e.g.:

```
[DEFAULT]
logdirs = /var/log:/var/www/localhost/logs
xz = /usr/local/bin/xz
charset = iso-8895-15

[user1]
logdirs = /var/www/webpage1/logs:/var/www/webpage2/logs

[user2]
logdirs = /var/log/mysql
```

Any unnamed user may search through logfiles in /var/log and /var/www/localhost/logs. The xz command is expected in /usr/local/bin. If you omit the *xz* option, you may not read xz compressed files. Any log entry which is not valid UTF8, is expected to be an ISO-8895-15 compliant string.

## Homepage

https://ogris.de/logblitz/

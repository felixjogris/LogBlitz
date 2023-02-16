# LogBlitz

LogBlitz is a CGI script to search through your (sys-)log files. It is written in Python 3, and aims to be a webbased alter ego of grep, zgrep, bzgrep, xzgrep, and so on. You can configure multiple directories that contain logfiles, and you can give each HTTP authenticated user an individual set of log directories. LogBlitz expects the webserver to place the name of an authenticated user in the environment variable REMOTE\_USER.
LogBlitz does not interpret the log entries in any way, but sees them just as a bunch of text lines. No additional modules need to be installed as a default installation of Python 3.8 or 3.9 is sufficient. The webinterface uses JavaScript just for the moveable divider between the filetree and the logview area, and for toggling the display of line numbers.

## Screenshot

![web interface](https://ogris.de/logblitz/logblitz.jpg)

## Installation
1. Put logblitz.py to the cgi-bin/ directory on you webserver, and make it executable
2. Optionally, place favicon.ico to the htdocs/ directory
3. Highly recommended: Install https://github.com/facebook/pyre2/:
   * On FreeBSD: make -C /usr/ports/devel/py-google-re2 install clean
   * On Gentoo Linux: emerge pyre2
4. Create etc/logblitz.ini, e.g.:

   ```
   [DEFAULT]
   logdirs = /var/log:/var/www/localhost/logs
   charset = ISO-8859-15
   logout_url = https://my.server.test/cgi-bin/logout.py

   [user1]
   logdirs = /var/www/webpage1/logs:/var/www/webpage2/logs

   [user2]
   logdirs = /var/log/mysql
   charset = UTF-8

   [user3]
   filefilter = ^samba
   dirfilter = ^jail$|fileserver

   [role1]
   users = ^(tina|ulf)$
   logdirs = /var/www1/logs
   filefilter = .gz$

   [role2]
   users = ^(tina|ulf)$
   logdirs = /var/www2/logs
   filefilter = .bz2$
   ```

   Any unnamed user and any user, who has not its section (e.g. [user4]), may search through logfiles in /var/log and /var/www/localhost/logs (if the user under which the webserver runs, is allowed to read those directories and/or logfiles). ISO-8859-15 is the default charset for any logfile, but logfiles in /var/log/mysql are decoded to UTF-8. Every user can specify an alternate charset in the web interface. If you don't provide a charset in the config file nor in the web interface, ISO-8859-1 is used by default.

   The user *user1* may read any logfiles in /var/www/webpage1/logs and /var/www/webpage2/logs, whereas *user2* may just read logfiles from /var/log/mysql.

   User *user3* is allowed to read logfile, which name starts with "samba", and if it resides in /var/log, /var/www/localhost/logs (as from the default section), and in any subdirectory, which name either is "jail" or contains "fileserver".

   Users tina and ulf may select either role1 or role2 from a dropdown. Role1 allows them to read any (compressed) log file from /var/www1/logs, whose name ends with .gz, whereas role2 allows them to read any log files from /var/www2/logs, whose name ends with .bz2.

   LogBlitz expects the webserver to place the name of the authenticated user in the environment variable *REMOTE_USER*.

5. Limit access to /cgi-bin/logblitz.py, e.g. by an ip address restriction and/or an authentication scheme. Otherwise, anybody may read your logfiles. In any case, enforce https since you transfer log data which may contain sensitive information.

## Homepage

https://ogris.de/logblitz/

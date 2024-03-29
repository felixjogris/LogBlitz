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
   logout_option = onclick="window.close();"
   nice_username_env = REMOTE_USER_FULLNAME

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

   [role3]
   env_REMOTE_USER_EMAIL = ^.+@localhost$
   logdirs = /var/www2/logs
   filefilter = .log$
   ```

   Any unnamed user and any user, who has not its section (e.g. [user4]), may search through logfiles in /var/log and /var/www/localhost/logs (if the user under which the webserver runs, is allowed to read those directories and/or logfiles). ISO-8859-15 is the default charset for any logfile, but logfiles in /var/log/mysql are decoded to UTF-8. Every user can specify an alternate charset in the web interface. If you don't provide a charset in the config file nor in the web interface, ISO-8859-1 is used by default.

   The user *user1* may read any logfiles in /var/www/webpage1/logs and /var/www/webpage2/logs, whereas *user2* may just read logfiles from /var/log/mysql.

   User *user3* is allowed to read logfile, which name starts with "samba", and if it resides in /var/log, /var/www/localhost/logs (as from the default section), and in any subdirectory, which name either is "jail" or contains "fileserver".

   Users tina and ulf may select either role1 or role2 from a dropdown. Role1 allows them to read any (compressed) log file from /var/www1/logs, whose name ends with .gz, whereas role2 allows them to read any log files from /var/www2/logs, whose name ends with .bz2.

   Any user, for whom the webserver's authentication module sets an environment variable named *REMOTE_USER_EMAIL* to a value like "someuser@localhost", is allowed to read any log file from /var/www2/logs, whose name ends with .log.

   LogBlitz expects the webserver to place the name of the authenticated user in the environment variable *REMOTE_USER*.

   Since *logout_url* is set, LogBlitz will show a "Logout" link in the upper right corner. If hover your mouse over that link, a popup will show your username, which is expected in the environment variable *REMOTE_USER_FULLNAME* instead of the default *REMOTE_USER*.

   As *logout_option* is also set, that JavaScript snippet will be printed verbatim in the logout link (read: in the *a href* tag).

5. Limit access to /cgi-bin/logblitz.py, e.g. by an ip address restriction and/or an authentication scheme. Otherwise, anybody may read your logfiles. In any case, enforce https since you transfer log data which may contain sensitive information.

## WSGI
Starting with version 16, LogBlitz can be served by a [WSGI](https://en.wikipedia.org/wiki/Web_Server_Gateway_Interface) server in addition to its CGI interface. If you use [mod\_wsgi](https://pypi.org/project/mod-wsgi/), then you can build upon these configuration snippets for [Apache](https://http.apache.org/):

```
WSGIDaemonProcess logblitz processes=1 display-name=logblitz threads=5 user=logblitz group=logblitz umask=0777 script-user=root inactivity-timeout=3600 cpu-time-limit=600 memory-limit=536870912 virtual-memory-limit=1073741824
WSGIScriptAlias /wsgi/ /usr/local/www/wsgi/
<Directory /usr/local/www/wsgi>
    WSGIProcessGroup default
    AllowOverride None
    Options None
    Require all granted
</Directory>
```

This assumes that you have created a local user account named "logblitz", while the logblitz.py file is owned by root and placed in "/usr/local/www/wsgi". If you plan to use the re2 a regex library, which is an extension written in C, then set [WSGIApplicationGroup](https://modwsgi.readthedocs.io/en/master/configuration-directives/WSGIApplicationGroup.html) to "%{GLOBAL}":

```
<Directory /usr/local/www/wsgi>
    ...
    WSGIApplicationGroup %{GLOBAL}
    ...
</Directory>
```

## Homepage

https://ogris.de/logblitz/

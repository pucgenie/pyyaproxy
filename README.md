# pyyaproxy
Because some ISPs still don't get IPv6 right and some ISPs began making NAT worse (CGNAT without open ports) I was in need of a relay server that connected IPv4-only clients with IPv6-only servers.
Because understanding documentation for existing solutions is not easy I quickly found someone who shared their code in a familiar language.

Yet another proxy written in Python.

# Original sourcecode from (StackOverflow.com) gawel
https://stackoverflow.com/a/21297354/2714781

## See also
[ncat -kl localhost 8080 --sh-exec "ncat example.org 80"](https://nmap.org/ncat/guide/ncat-tricks.html#:~:text=Chain%20Ncats%20Together)

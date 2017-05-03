# NOT READY YET
# dns-integration
# DNS intergation script for unbound
## Quick description
This is DNS integration script / system for DNS integration between private (INTRANET) DNS and AWS/AZURE DNS. 

IT is tested with AWS and few private networks (via IPSEC) but can be used with AZURE as well.

## DNS intergration between private network and AWS/AZURE cloud network.

Idea is simple. When you create AWS VPC and activate ROUTE53, it allocates AWS DNS resolver on IP address (beginning of VPC + 2). 
This DNS resolver respond to the requests from this VPC, resolving DNS names in this VPC.

For example, we create ROUTE53 internal zones corevelocity.test.cloud and use them inside this VPC. VPC is 10.24.128.0 /22. ROUTE53 resolver is, then, on 10.24.128.2 . If any system from inside this VPC ask it, it can resolve our zone (corevelocity.test.cloud) and , if configured, zones 128.24.10.in-addr.arpa, 129.24.10.in-addr.arpa, 130.24.10.in-addr.arpa, 131.24.10.in-addr.arpa .

When we connect VPC to INTRANET network (or some DMZ) using VTI routers (see vti-router project next to this) or any hardware,
we integrate our INTRANET IP space and AWS VPC IP space. 

Next step is to make this zone visible in our INTRANET. We can not forward our requests to the 10.24.128.2 directly, as ROUTE53 DNS wil not answer requests from outside VPC, and more over, forward zones are not global property of INTRANET (if you use Microsoft DNS, forwarding is local property of DNS server and not of the AD domain; if using ProBIND2, it do not have forward zones feature yet).

So, what we do to resolve it:
1) We install 1 or 2 DNS proxies, using unbound.
2) We configure unbound to forward zones (in our case, corevelocity.test.cloud,  128.24.10.in-addr.arpa, 129.24.10.in-addr.arpa, 130.24.10.in-addr.arpa, 131.24.10.in-addr.arpa) to 10.24.128.2 (ROUTE53).
3) We install script from this project, which makes all requests to became recursive, adds AA (authoritative) bit into all responses, and replace NS records in responses.
4) We create zone (if not exists yet) cloud in our INTRANET, then we delegate zones (in our case, corevelocity.test.cloud,  128.24.10.in-addr.arpa, 129.24.10.in-addr.arpa, 130.24.10.in-addr.arpa, 131.24.10.in-addr.arpa) to these NS proxies, using standard NS records and names which can be resolved inside INTRANET (in my case, I add records

  corevelocity.test.cloud. NS test-ns.eisgroup.com.
  test-ns.eisgroup.com A <IP of first NS proxy>
  test-ns.eisgroup.com A <IP of second NS proxy>

Script intercept requests, adds RCURSION DESIRED bit into it, and send them to ROUTE53. IT adds 'authoritative' bit into the responses and replace NS records, if any, by our specified test-ns.eisgroup.com.  So, these proxies looks as athitative NS servers for our INTRANET and as local DNS clients for ROUTE53.

Scripts files should be extracted into /etc/unbound/conf.d directory, and extra UNBOUND configuration is required. In case of CentOS7, it includes:
(This is just an example):
```
server:
        verbosity: 1
        statistics-interval: 0
        statistics-cumulative: no
        extended-statistics: yes
        num-threads: 2
        interface-automatic: no
        chroot: ""
        username: "unbound"
        directory: "/etc/unbound"
        log-time-ascii: yes
        pidfile: "/var/run/unbound/unbound.pid"
        target-fetch-policy: "0 0 0 0 0"
        harden-glue: yes
        harden-dnssec-stripped: yes
        harden-below-nxdomain: no
        harden-referral-path: no
        use-caps-for-id: no
        unwanted-reply-threshold: 10000000
        prefetch: yes
        prefetch-key: yes
        rrset-roundrobin: yes
        minimal-responses: yes
        val-clean-additional: yes
        val-permissive-mode: no
        val-log-level: 1
        include: /etc/unbound/local.d/*.conf
remote-control:
        control-enable: yes
        server-key-file: "/etc/unbound/unbound_server.key"
        server-cert-file: "/etc/unbound/unbound_server.pem"
        control-key-file: "/etc/unbound/unbound_control.key"
        control-cert-file: "/etc/unbound/unbound_control.pem"
include: /etc/unbound/conf.d/*.conf
```
These lines comes from local configuration in conf.d directory and wil depend of your situation:
```
server:
        target-fetch-policy: "3 3 3 3 3"
        local-zone: "10.in-addr.arpa" nodefault
forward-zone:
        name: "corevelocity.test.cloud"
        forward-addr: 10.24.128.2
forward-zone:
        name: "128.24.10.in-addr.arpa"
        forward-addr: 10.24.128.2
```
These lines come with project files (they are in ubmodule-FakedNS.conf):

```
server:
        module-config: "python validator iterator"
python:
         python-script: "/etc/unbound/conf.d/ubmodule-FakeNS.py"
```

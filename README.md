# Project Title

UNBOUND script for DNS integration between INTRANET and AWS/AZURE/Other clouds
(DNS proxy which became faked NS authoritative server for remote zones)

## Getting Started - example
This is DNS integration script / system for DNS integration between private (INTRANET) DNS and AWS/AZURE DNS. 

This system (script for unbound) is designed to simplify name space integration between 
AWS/AZURE cloud networks, and corprorative INTRANET network. It can be used in other cases, 
too (we use it to integrate internal name spaces of some of our customers, connected by normal,
policy based IPSEC, to our network). 
Script is created (and tested) for unbound 1.4.20 (default for Centos 7).

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

Without script, our NS servers may sent non recursive requests to the proxy, get in response
NS records, which can not be used in INTRANET< and end up with SERVFAIL message. With script, 
it makes all requests recursive (even when they are sent as non recursive), makes all 
responses authoritative (so it works as kind of proxy for remote authoritative DNS),
and replace additional NS records by our own desireble NS records (NSes to these DNS proxies).
as a result, INTRANET DNS system see these proxyes as authoritative servers for remote domains,
so effectively integrated together cloud DNS (ROUTE53 or similar) and INTRANET DNS.

## Presequisites
Scripts need unbound 1.4 or later (tested on 1.4.20), with python module support.

Unbound must be dedicated for proxying DNS request from AWS (or other remote / cloud network)
only. While it can be used as resolver, it is bad idea and better be avoided. 

Unbound must be, first, configured to resolve names from remote network / cloud (by 
forwarding requests into it for the proper domains). IT is recommended to test it before
you install script and configure unbound as faked NS server for the domain(s).

You must be able to add NS records for the domains you want to get from remote network/cloud,
in your own INTRANET DNS.

You must run your own INTRANET DNS system. 

## Installing 

### 1. Install unbound servers
Install 1 - 2 servers which will work as NS proxy for remote zones. They must have access
to remote DNS (for example, in case of AWS they must be inside AWS VPC on proper account).

Install unbound.

Before extracting our script, configure unbound to forward proper zones onto remote DNS
and resolve names, when requested directly. See example of configuration below.

We recommend to do it before extracting script, as it allow to separate errors, cauased by 
our script, from errors, caused by inproper unbound configuration.

### 2. Extract project files from conf.d folder of this project, into /etc/unbound/conf.d directory. 
It will include 
- ubmodule-FakeNS.py - script itself/
- ubmodule-FakeNS.conf - extra configuration for unbound , to rnable this script.
- ubmodule-FakeNS.ini-sample - sample ubmodule-FakeNS.ini configuration file
- proxy.conf-sample - sample file for proxy.conf itself (which describe zone forwardings)

### 3. Edit unbound.conf file and local.d/access.conf file (or merge them all). 
You must set up these configurations (access-control is required, other commands are recommended)
Make sure that these options are configured in any of your places (actual place depends of the unbound version):
```
server:
        access-control: 0.0.0.0/0 allow_snoop
        val-permissive-mode: yes
        prefetch: yes
        minimal-responses: yes
        cache-min-ttl: 3600
        prefetch: yes
        minimal-responses: yes
        val-clean-additional: yes
```

### 4. Copy sample files and configure them.
You will need to create conf.d/ubmodule-FakeNS.ini file (cppy from sample file and edit).
It contain list of domains you want to process by this script, list of NS records it should
return instead of remote NS records (make sure that some of them can be resolved in your 
INTRANET), and additional flags (for example, you just add recursive flag or cgange TTL 
in responses).

Create forwarding file - you can use proxy-conf-sample as an example.


### 5. Test unbound. It must resolve names in remote DNS zones.
If you can,. test it by sending non recursive requests. Script will convert
requests to recursive and will add 'autoritative answer' flag into the answers.

### 6. Delegate zones in your INTRANET.

Now, add NS records into your INTRANET DNS. To do it, you usually create lower level zone
as your INTRANET zone (for example, you can create test.cloud zone as integrated AD DNS zone),
and then add NS records into it ( corevelocity NS <name of NS proxy> )

Make sure that NS can be resolved without new NS proxy. 
Do not use STUB zone (you can experiment, maybe it will work too, but we did not test it).

### 7. Test remote zones.
Now, you can test, how names from remote zones are resolved in your INTRANET.
If something wrong, you likely will have SERVFAIL response. Make sure that you restaretd DNS servers or cleared caches before testing.

## Versioning

This is version 1.1 of the script. major numbers will be different for
different unbound version. No real versioning was used yet.

## Authors

* **Mikhail Koshelev** - *made all conding and debugging* -  m.koshelev@gmail.com 
* **Alexei Roudnev**   - designed delegation idea and tested it - aprudnev@gmail.com
* **EIS Group open source group** - open-source@eisgroup.com


## License

This project is licensed under the GPL license, and is donated by EIS Group (http://eisgroup.com) to the open source community (as it is based on mostly open source products,
but contains our code and was carefully tested in different conditions).

## UPDATES.

We discovered, that in some cases script cause unbound to crash. Cache invalidation was found unnecessary and so removed.
While it did not fix all crashes, it crashes now in heavy environment once / few days (so systemctl restarts it).
It never crashed in 4 different environments. 

I push updated python script.

IN addition, we discovered, that windows client may, in some cases, use NS name from SOA and not from NS records.
So make sure, that AWS or AZURE zone have correct (resolvable by your DNS) NS name in SOA and resolvable
NS recods in zone itself.

(Maybe, no need in proxy for Azure, not well tested yet. Azure DNS can resolve requests coming from outside VNET, while
AWS DNS never respond to the requests which originates outside of VPC network. So proxy is mandatory for AWS.)

## UPDATE 2 - invalidate_cache option addedd (default - yes)

There are cases, when we receive correct NSes from forwarded server or when we do not have subdomains.
It is usually the case for AWS ROUTE53. In such case, we better do not invalidate records in teh cache, as
it saves a lot of script runs, and scripts may fail under the very heavy load. So, we recommend to try this
option as 'no' for AWS integration.

On the other case, if other size has subdomains, cache invalidation became essential, as unbound may
cache NS responses, and when see request next time, may answer with these NS-es without runnig recursion
next time. We need to invalidate requests in cache in such cases, and it is default. We use it
when made DNS integration with our customer, via IPSEC connection.

Invalidating cahce more cause script to run more often, and is not recommended in AWS under the heavy traffic.


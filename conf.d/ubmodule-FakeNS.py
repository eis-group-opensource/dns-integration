#!/usr/bin/python
'''
 ubmodule-FakeNS.py: Replace NS records in replys
                     (except for local requests)
'''

import socket


#
# configuration
#
CONFIG_FILE = '/etc/unbound/conf.d/ubmodule-FakeNS.ini'

CONFIG_DEFAULTS = {
    'ttl': '0',
    'ttl_override': 'no',
    'recursion_only': 'no',
    'invalidate_cache': 'yes'
}

# NS override configuration (dict)
ns_map = {
    # <domain>:
    #   ns: [ <ns1>, ... ]
    #   ttl: <int>
    #   ttl_override: <bool>
    #   recursion_only: <bool>
    #   invalidate_cache: <bool>
    }

from ConfigParser import SafeConfigParser

def readConfig():
    log_info("reading FakeNS module configuration from %s" % CONFIG_FILE)
    cfg = SafeConfigParser( defaults=CONFIG_DEFAULTS )
    with open(CONFIG_FILE) as FH_cfg:
        cfg.readfp( FH_cfg )
        for section in cfg.sections():
            # read domain/ns set sections
            if not section.startswith('set'):
                continue
            # extract confuration parameters
            cfg_dlist = [ s.strip() for s in cfg.get( section, 'domains' ).split(',') ]
            cfg_nslist = [ n.strip() for n in cfg.get( section, 'ns' ).split(',') ]
            #cfg_ttl = cfg.getint( section, 'ttl' )
            #!TODO: check correctness
            for domain in cfg_dlist:
                if domain not in ns_map.keys():
                    ns_map[ domain ] = {}
                ns_map[ domain ]['ns'] = cfg_nslist
                ns_map[ domain ]['ttl'] = cfg.getint( section, 'ttl' )
                ns_map[ domain ]['ttl_override'] = cfg.getboolean( section, 'ttl_override' )
                ns_map[ domain ]['recursion_only'] = cfg.getboolean( section, 'recursion_only' )
                ns_map[ domain ]['invalidate_cache'] = cfg.getboolean( section, 'invalidate_cache' )
        log_info("FakeNS module configuration: %s" % ns_map)
        return True
    raise ModuleError("Can't read module configuration")


#
# standard module API functions
#

def init(id, cfg):
    return readConfig()

def deinit(id):
    return True

def inform_super(id, qstate, superqstate, qdata):
    return True


#
# helper and utility functions
#

# return configuration node for domain or None
#!NOTE: could be extended in future to support subdomains flag and/or multiple NS
def get_node(name):
    for dd in ns_map.keys():
        if name.rstrip('.').endswith( '.' + dd ) or \
            ( name.rstrip('.') == dd ):
            return ns_map[ dd ]
    return None

# check if request source belongs to filtered space
#!TODO: set IP list for 'true vision' in config file
def is_source_filtered(qstate):
    rl = qstate.mesh_info.reply_list
    while (rl):
        if rl.query_reply:
            q = rl.query_reply
            if (q.addr == '127.0.0.1'):
                return False
            #log_info("overriden query addr: %s" % q.addr)
            rl = rl.next
    return True


# first two bytes contain the payload length
# third byte is the length of the first label
def unpackIP(strIP):
    return socket.inet_ntoa(strIP[2:])

# first two bytes contain the payload length
# third byte is the length of the first label
def unpackNAME(strNAME):
    lbl_remain = ord(strNAME[2])
    name = ""
    for c in strNAME[3:]:
        if lbl_remain == 0:
            name += "."
            lbl_remain = ord(c)
            continue
        lbl_remain -= 1
        name += c
    return name

# replace NS records in selected replys (currently NS,A,CNAME)
# TODO: MX,SOA,PTR ?
def processRRSets(qstate):
    msg = DNSMessage(qstate.qinfo.qname_str, qstate.qinfo.qtype, RR_CLASS_IN, PKT_QR | PKT_RA | PKT_AA)
    qname = qstate.qinfo.qname_str.rstrip('.')
    rep = qstate.return_msg.rep

    node = get_node(qname)
    modified = False
    for i in xrange(rep.an_numrrsets):
        if rep.rrsets[i].rk.type_str == 'NS':
            if not modified:
                # only change NS records
                for ns in node['ns']:
                    msg.answer.append("%s %d IN NS %s" % (qname, node['ttl'], ns))
                modified = True
                #log_info("modifying NS in RR")
        elif rep.rrsets[i].rk.type_str == 'A':
            data = rep.rrsets[i].entry.data
            for j in xrange(data.count):
                msg.answer.append('%s %d IN A %s' % (qname, data.rr_ttl[j], unpackIP(data.rr_data[j])))
        elif rep.rrsets[i].rk.type_str == 'CNAME':
            data = rep.rrsets[i].entry.data
            for j in xrange(data.count):
                msg.answer.append('%s %d IN CNAME %s' % (qname, data.rr_ttl[j], unpackNAME(data.rr_data[j])))
        elif rep.rrsets[i].rk.type_str == 'PTR':
            data = rep.rrsets[i].entry.data
            for j in xrange(data.count):
                msg.answer.append('%s %d IN PTR %s' % (qname, data.rr_ttl[j], unpackNAME(data.rr_data[j])))
    if not msg.set_return_msg(qstate):
        raise ModuleError("Can't set the return message")


# Extract the response status code (RCODE_NOERROR, RCODE_NXDOMAIN, ...).
def get_return_msg_rcode(return_msg):
    if not return_msg:
        return RCODE_SERVFAIL
    # see macro FLAGS_GET_RCODE in util\net_help.h
    return return_msg.rep.flags & 0xf

# set authorative answer flag
def setAA(qstate):
    """Set AA flag for all replies"""
    if qstate.return_msg:
        if qstate.return_msg.rep:
            # BIT_AA 0x0400
            qstate.return_msg.rep.flags |= 0x0400
            qstate.return_msg.rep.authoritative = 1

# set TTL for reply
def setTTL(qstate, ttl):
    """Updates return_msg TTL and the TTL of all the RRs"""
    if qstate.return_msg:
        qstate.return_msg.rep.ttl = ttl
        if (qstate.return_msg.rep):
            for i in range(0,qstate.return_msg.rep.rrset_count):
                d = qstate.return_msg.rep.rrsets[i].entry.data
                for j in range(0,d.count+d.rrsig_count):
                    d.rr_ttl[j] = ttl


#
# main DNS requests handler function
#

def operate(id, event, qstate, qdata):

    if (event == MODULE_EVENT_NEW) or (event == MODULE_EVENT_PASS):

        # filter queries requiring special handling
        if get_node(qstate.qinfo.qname_str) is not None:
            # force RD flag for forwarded queries for special domain
            qstate.query_flags |= 0x0100
            #!NOTE: these cache controls seems to be introduced in 6.0 only
            qstate.no_cache_lookup = 1
            qstate.no_cache_store = 1
        qstate.ext_state[id] = MODULE_WAIT_MODULE
        return True

    if event == MODULE_EVENT_MODDONE:
        # configuration for specific domain node
        node = get_node(qstate.qinfo.qname_str)
        # filter queries requiring special handling
        if node is not None:
            # forward reply as is if 'recursion_only' flag is set
            if node['recursion_only']:
                qstate.ext_state[id] = MODULE_FINISHED
                return True


            # skip queries with no return messages
            if qstate.return_msg is None:
                #log_info("NO RETURN_MSG: str %s type %s" % (qstate.qinfo.qname_str,qstate.qinfo.qtype) )
                qstate.ext_state[id] = MODULE_FINISHED
                return True
		
            # don't save result in cache, as stored replies are not handled by python modules
	    # But for NS records only, as NS can be rquested by proxy itself
            #if ( qstate.qinfo.qtype == RR_TYPE_NS):
            if node['invalidate_cache']:
            	invalidateQueryInCache(qstate, qstate.return_msg.qinfo)
	  
	    qstate.no_cache_lookup = 1
	    qstate.no_cache_store = 1



            # pass reply to non-filtered source as is
            if not is_source_filtered(qstate):
                #log_info("pythonmod: passing request from non-filtered source as is")
                qstate.ext_state[id] = MODULE_FINISHED
                return True

            # for NS requests - simply return record pointing to this server
            if (qstate.qinfo.qtype == RR_TYPE_NS):
                msg = DNSMessage(qstate.qinfo.qname_str, RR_TYPE_NS, RR_CLASS_IN, PKT_QR | PKT_RA | PKT_AA)
                for ns in node['ns']:
                    msg.answer.append("%s %d IN NS %s" % (qstate.qinfo.qname_str, node['ttl'], ns))
                if not msg.set_return_msg(qstate):
                    log_info("pythonmod: ERROR handling NS reply")
                    qstate.ext_state[id] = MODULE_ERROR
                    return True
                # disable modified reply verification
                qstate.return_msg.rep.security = 2
                qstate.return_rcode = RCODE_NOERROR
                qstate.ext_state[id] = MODULE_FINISHED
                return True

            # for other request types - copy non-NS parts and replace NS (in RR's)
            elif qstate.qinfo.qtype in [ RR_TYPE_A, RR_TYPE_CNAME, RR_TYPE_PTR ]:
                # preserve return code (for NXDOMAIN and such)
                rcode = get_return_msg_rcode(qstate.return_msg)
                processRRSets(qstate)
                # update TTL if override is requested
                if node['ttl_override']:
                    setTTL( qstate, node['ttl'] )
                #set qstate.return_msg
                #if not msg.set_return_msg(qstate):
                #    log_info("pythonmod: ERROR handling A entries")
                #    qstate.ext_state[id] = MODULE_ERROR
                #    return True
                qstate.return_msg.rep.security = 2
                qstate.return_rcode = rcode
                qstate.ext_state[id] = MODULE_FINISHED
                return True

            # set AA flag for all other filtered queries
            setAA(qstate)
            # update TTL if override is requested
            if node['ttl_override']:
                setTTL( qstate, node['ttl'] )

        # for non-filtered replies
        qstate.return_rcode = RCODE_NOERROR
        qstate.ext_state[id] = MODULE_FINISHED 
        return True

    log_err("pythonmod: bad event")
    qstate.ext_state[id] = MODULE_ERROR
    return True


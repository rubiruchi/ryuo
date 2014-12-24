from grp import getgrnam
import os
from pwd import getpwnam
import re
import subprocess

from ryu.lib.dpid import dpid_to_str
from ryu.lib.port_no import port_no_to_str

from ryuo.scapy.layers import Pktgen


def name_to_dpid(name):
    nums = re.findall(r'\d+', name)
    if nums:
        return int(nums[0])


def add_addresses(addresses, controller_ip):
    for address in addresses:
        ip = address[0]
        router = address[1]
        port = address[2]
        subprocess.call(['curl',
                         '-X',
                         'POST',
                         '-d',
                         '{"address": "%s"}' % ip,
                         'http://%s:8080/router/%s/%s/address' % (
                             controller_ip, dpid_to_str(router),
                             port_no_to_str(port))])


def request_routing(controller_ip):
    subprocess.call(['curl', '-X', 'POST',
                     'http://%s:8080/router/routing' % controller_ip])


def parse_tshark_stats(outputs):
    lines = outputs.split('\n')
    return int(lines[-3].split('|')[-3])


def as_normal_user(user, grp):
    os.setgid(getgrnam(grp).gr_gid)
    os.setuid(getpwnam(user).pw_uid)


def run_tshark_stats(pcap_file, stat, field, user):
    return subprocess.Popen(
        ['tshark',
         '-r', pcap_file,
         '-qz', 'io,stat,0,%s&&%s' % (stat, field)],
        stdout=subprocess.PIPE,
        preexec_fn=lambda: as_normal_user(user, 'wireshark'))


def get_lost_sequence(pkts):
    max_seq = 0
    losted_seq = []
    counter = 0
    for pkt in pkts:
        if Pktgen not in pkt:
            continue
        counter += 1
        pkt = pkt[Pktgen]
        if pkt.seq > max_seq:
            losted_seq += [i for i in range(max_seq + 1, pkt.seq)]
            max_seq = pkt.seq
        elif pkt.seq < max_seq:
            if pkt.seq in losted_seq:
                losted_seq.remove(pkt.seq)
    return losted_seq, max_seq, counter



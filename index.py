import sys
import os
import yaml
import json
import requests
from time import sleep

from pymemcache.client.base import Client

from designateclient.v2 import client

from keystoneauth1.identity import generic
from keystoneauth1 import session as keystone_session


def json_serializer(key, value):
    if type(value) == str:
        return value, 1
    return json.dumps(value), 2


def json_deserializer(key, value, flags):
    if flags == 1:
        return value
    if flags == 2:
        return json.loads(value)
    raise Exception("Unknown serialization format")


print("Reading settings...")
config = "settings.yaml"
if os.path.isfile(config):
    with open(config) as f:
        settings = yaml.load(f, Loader=yaml.Loader)
else:
    sys.exit("Can't find settings.")

if settings["sleep"] != 0:
    print("\nSleeping...")  # allow hosts to save latency information
    sleep(settings["sleep"])

try:
    mc = Client(
        (settings["memcached"]["server"], int(settings["memcached"]["port"])),
        serializer=json_serializer,
        deserializer=json_deserializer)
except Exception as e:
    print(str(e))
    sys.exit("Can't connect to Memcached.")

try:
    auth = generic.Password(
        auth_url=settings["openstack"]["endpoint"],
        username=settings["openstack"]["username"],
        password=settings["openstack"]["password"],
        project_name=settings["openstack"]["project"]["name"],
        project_domain_id="default",
        user_domain_id="default")
    session = keystone_session.Session(auth=auth)
    client = client.Client(session=session)
except Exception as e:
    print(str(e))
    sys.exit("Can't connect to Nectar.")

token = "dns-lb"

print("\nGetting current DNS records...")
records = mc.get(token)
if records is None:
    records = []
for ip in records:
    print("- {}".format(ip))


hosts = {}
print("\nGetting latency...")
for host in settings["haproxy"]["hosts"]:
    try:
        rsp = requests.get(
            settings["haproxy"]["path"].format(host),
            timeout=settings["haproxy"]["timeout"])
        if rsp.status_code == 200:
            data = rsp.text.split("/")
            ping = int(data[1])  # min/avg/max/mdev
            if ping < settings["latency"]["threshold"]:
                hosts[host] = ping
                status = "UP"
            else:
                status = "DOWN"
            print("- {}: {} ({})".format(host, ping, status))
    except Exception as e:
        print("- {}: {}".format(host, str(e)))
        pass

if len(hosts) == 0:
    print("\nNo update due to no hosts information available.")
else:
    dns = []
    for ip in records:
        if ip in hosts:
            dns.append(ip)
    for ip in hosts:
        if ip not in dns:
            dns.append(ip)
    if len(records) != 0 and len(dns) > 1:
        dns = dns[1:] + dns[:1]
    if dns != records:
        print("\nUpdating DNS records...")
        for ip in dns:
            print("- {}".format(ip))
        try:
            client.recordsets.update(
                settings["dns"]["zone"],
                settings["dns"]["name"],
                {
                    "ttl": settings["dns"]["ttl"],
                    "records": dns
                }
            )
            mc.set(token, dns)
        except Exception as e:
            print(str(e))
            sys.exit("Can't update DNS information.")

print("\nCompleted.")

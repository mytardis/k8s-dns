import sys
import os
import yaml
import requests
from time import sleep

from designateclient.v2 import client

from keystoneauth1.identity import generic
from keystoneauth1 import session as keystone_session


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

auth = generic.Password(
    auth_url=settings["openstack"]["endpoint"],
    username=settings["openstack"]["username"],
    password=settings["openstack"]["password"],
    project_name=settings["openstack"]["project"]["name"],
    project_domain_id="default",
    user_domain_id="default")
session = keystone_session.Session(auth=auth)
client = client.Client(session=session)

try:
    print("\nGetting current DNS records...")
    records = client.recordsets.get(
        settings["dns"]["zone"],
        settings["dns"]["name"])
    for ip in records["records"]:
        print("- {}".format(ip))
except Exception as e:
    print(str(e))
    sys.exit("Can't fetch DNS information.")

hosts = {}
print("\nGetting latency...")
for host in settings["haproxy"]["hosts"]:
    try:
        rsp = requests.get(
            settings["haproxy"]["path"].format(host),
            timeout=settings["haproxy"]["timeout"])
        if rsp.status_code == 200:
            data = rsp.text.split("/")
            hosts[host] = data[1]  # min/avg/max/mdev
            print("- {}: {}".format(host, hosts[host]))
    except Exception as e:
        print("- {}: {}".format(host, str(e)))
        pass

if len(hosts) == 0:
    print("\nNo update due to no hosts information available.")
else:
    dns = []
    for ip in records["records"]:
        if ip in hosts:
            dns.append(ip)
    for ip in hosts:
        if ip not in dns:
            dns.append(ip)
    if len(dns) > 1:
        dns = dns[1:] + dns[:1]
    if dns != records["records"]:
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
        except Exception as e:
            print(str(e))
            sys.exit("Can't update DNS information.")

print("\nCompleted.")

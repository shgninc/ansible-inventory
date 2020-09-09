from __future__ import division

import json

from collections import defaultdict, namedtuple
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.inventory.manager import InventoryManager
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.vars.manager import VariableManager
from ansible import context
#from os.path import dirname, abspath

TOTAL_RESULTS = {}

def ram_allocated_gb(facts):
    """Return total memory allocation in GB"""
    return facts['ansible_memtotal_mb'] / 1024


def ram_used_gb(facts):
    """Return used memory in GB"""
    return (facts['ansible_memtotal_mb'] - facts['ansible_memfree_mb']) / 1024

def _size(key, mounts):
    return sum([item.get(key, 0) for item in mounts])

def lvm_disks(disk):
    out = []
    try:
        for k, val in disk['report'][0].items():
            for vg in val:
                out.append({'vg_name': vg['vg_name'], 'vg_size': vg['vg_size'], 'vg_free': vg['vg_free']})
    except Exception as e:
        print(e)
    return out

def storage_allocated_gb(facts):
    """Return total storage allocation in GB"""
    return _size('size_total', facts['ansible_mounts']) / 1024 ** 3

def storage_used_gb(facts):
    """Return used storage in GB"""
    return (_size('size_total', facts['ansible_mounts']) -
            _size('size_available', facts['ansible_mounts'])) / 1024 ** 3

def cpu_count(facts):
    """Return the number of CPUs"""
    return max([
        int(facts.get('ansible_processor_count', 0)),
        int(facts.get('ansible_processor_vcpus', 0))
    ])

def cpu_name(proc):
    """Return CPU name"""
    items_count = len(proc)
    if items_count == 1:
        return proc[0]
    if items_count >= 3:
        return proc[2]
    return 'Unknown'

class ResultCallback(CallbackBase):
    def v2_runner_on_ok(self, result):
        print("ansible result")
        print(result._result)
        if "stdout" in result._result:
            if "report" in result._result["stdout"]:
                disk = eval(result._result["stdout"])
                host = str(result._host)
                for key, val in TOTAL_RESULTS.items():
                    if key in host:
                        TOTAL_RESULTS[key]['disk'] = lvm_disks(disk)
                # print(json.dumps(disk, indent=4))
            else:
                print(result._result["stdout_lines"])
                arp_out = result._result["stdout_lines"]
                host = str(result._host)
                nets = {}
                for line in arp_out[1:]:
                    curr_ip = line.split()[0]
                    curr_mac = line.split()[2]
                    nets[curr_mac] = curr_ip
                for key, val in TOTAL_RESULTS.items():
                    if key in host:
                        TOTAL_RESULTS[key]['nets'] = nets

                    # print()
        else:
            facts = result._result['ansible_facts']
            TOTAL_RESULTS[str(facts['ansible_hostname'])] = {
                'name': facts['ansible_hostname'],
                'fqdn': facts['ansible_fqdn'],
                'network': facts['ansible_all_ipv4_addresses'],  # + facts['ansible_all_ipv6_addresses'],
                'ram': ram_allocated_gb(facts),
                'ram_used_gb': ram_used_gb(facts),
                # 'disk': lvm_disks(disk),
                'storage_used_gb': storage_used_gb(facts),
                'cpu': cpu_count(facts),
                'operating_system': facts['ansible_distribution'],
                'operating_system_version': facts['ansible_distribution_version'],
                'cpu_name': cpu_name(facts['ansible_processor']),
                'state': 'on'
            }

    def v2_runner_on_unreachable(self, result, **kwargs):
        host = result._host
        print("ansible Unreachable")
        print(json.dumps({host.name: result._result}, indent=4))

    def v2_runner_on_failed(self, result, ignore_errors=False):
        host = result._host
        print("ansible Fail")
        print(json.dumps({host.name: result._result}, indent=4))
        print("Exception:::::::")
        print(result._result['exception'])


context.CLIARGS = ImmutableDict(connection='smart', module_path=None, forks=10, become=False,
                    verbosity=True,become_method=None, become_user=None, check=False, diff=False)

LOADER = DataLoader()
RESULTS_CALLBACK = ResultCallback()
INVENTORY = InventoryManager(loader=LOADER, sources=None)
INVENTORY.add_host(host='shgn@dbg.10d.ir', group='all', port=9494)

# INVENTORY = InventoryManager(loader=LOADER, sources=('host,',))
# INVENTORY.add_host(host='loaclhost', group='all', port=9494)

VARIABLE_MANAGER = VariableManager(loader=LOADER, inventory=INVENTORY)
PLAY_SOURCE = dict(
    name='Ansible Play',
    hosts='all',
    gather_facts='yes',
    tasks=[
        # dict(name="WHOAMI", action=dict(module='win_whoami'))
        # dict(action=dict(module='shell', args='ls'), register='shell_out'),
        # dict(action=dict(module='debug', args=dict(msg='{{shell_out.stdout}}'))),
    ]
)

PLAY = Play().load(PLAY_SOURCE, variable_manager=VARIABLE_MANAGER, loader=LOADER)
TQM = None
try:
    TQM = TaskQueueManager(
        inventory=INVENTORY,
        variable_manager=VARIABLE_MANAGER,
        loader=LOADER,
        # options=OPTIONS,
        passwords=dict(),
        stdout_callback= RESULTS_CALLBACK
    )
    res = TQM.run(PLAY)
    # print(res)
    # print(json.dumps(TOTAL_RESULTS, indent=4))
finally:
    if TQM is not None:
        TQM.cleanup()
print(TOTAL_RESULTS)

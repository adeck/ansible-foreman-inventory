#!/usr/bin/env python
#
# Internet Systems Consortium license
#
# Copyright (c) 2014, Franck Cuny (<franckcuny@gmail.com>)
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.

# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
# TORTUOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
# THIS SOFTWARE.


'''
Foreman external inventory script
=================================

Generates inventory that Ansible can understand by making API requests
to Foreman.

Information about the Foreman's instance can be stored in the ``foreman.ini`` file.
A ``base_url``, ``username`` and ``password`` need to be provided. The path to an
alternate configuration file can be provided by exporting the ``FOREMAN_INI_PATH``
variable.

When run against a specific host, this script returns the following variables
based on the data obtained from Foreman:
 - id
 - ip
 - name
 - environment
 - os
 - model
 - compute_resource
 - domain
 - architecture
 - created
 - updated
 - status
 - hostgroup
 - ansible_ssh_host

When run in --list mode, instances are grouped by the following categories:
 - group

Examples:
  Execute uname on all instances in the dev group
  $ ansible -i theforeman.py dev -m shell -a \"/bin/uname -a\"

Author: Franck Cuny <franckcuny@gmail.com>
Version: 0.0.1
'''

import sys
import os
import re
import optparse
import ConfigParser
import collections

try:
    import json
except ImportError:
    import simplejson as json

try:
    from foreman.client import Foreman
    from requests.exceptions import ConnectionError
except ImportError, e:
    print ('python-foreman required for this module')
    print e
    sys.exit(1)


class ForemanInventory(object):
    """Foreman Inventory"""

    def _empty_inventory(self):
        """Empty inventory"""
        return {'_meta': {'hostvars': {}}}

    def _empty_cache(self):
        """Empty cache"""
        keys = ['operatingsystem', 'hostgroup', 'environment', 'model', 'compute_resource', 'domain', 'subnet', 'architecture', 'host']
        keys_d = {}
        for i in keys:
          keys_d[i] = {}
        return keys_d

    def __init__(self):
        """Main execution path"""

        self.inventory = self._empty_inventory()
        self._cache = self._empty_cache()

        self.base_url = None
        self.username = None
        self.password = None

        # Read settings and parse CLI arguments
        self.read_settings()
        self.parse_cli_args()

        if self.base_url is None or self.username is None or self.password is None:
            print '''Could not find values for Foreman base_url, username or password.
They must be specified via ini file.'''
            sys.exit(1)

        try:
            self.client = Foreman(self.base_url, (self.username, self.password))
        except ConnectionError, e:
            print '''It looks like Foreman's API is unreachable.'''
            print e
            sys.exit(1)

        if self.args.host:
            data_to_print = self.get_host_info(self.args.host)
        elif self.args.list:
            data_to_print = self.get_inventory()
        else:
            data_to_print = {}

        print(json.dumps(data_to_print, sort_keys=True, indent=4))

    def get_host_info(self, host_id):
        """Get information about an host"""
        host_desc = {}

        meta = self._get_object_from_id('host', host_id)
        if meta is None:
            return host_desc

        host_desc = {
            'id': meta.get('id'),
            'ip': meta.get('ip'),
            'name': meta.get('name'),
            'environment': meta.get('environment').get('environment').get('name').lower(),
            'os': self._get_from_id('operatingsystem', meta.get('operatingsystem_id')),
            'model': self._get_from_id('model', meta.get('model_id')),
            'compute_resource': self._get_from_id('compute_resource', meta.get('compute_resource_id')),
            'domain': self._get_from_id('domain', meta.get('domain_id')),
            'subnet': self._get_from_id('subnet', meta.get('subnet_id')),
            'architecture': self._get_from_id('architecture', meta.get('architecture_id')),
            'created': meta.get('created_at'),
            'updated': meta.get('updated_at'),
            'status': meta.get('status'),
            'hostgroup': self._get_from_id('hostgroup', meta.get('hostgroup_id')),
            # to ssh from ansible
            'ansible_ssh_host': meta.get('ip'),
        }

        return host_desc

    def get_inventory(self):
        """Get all the host from the inventory"""
        groups = collections.defaultdict(list)
        hosts  = []

        page = 1
        while True:
            resp = self.client.index_hosts(page=page)
            if len(resp) < 1:
                break
            page  += 1
            hosts += resp

        if len(hosts) < 1:
            return groups

        for host in hosts:
            host_group = self._get_hostgroup_from_id(host.get('host').get('hostgroup_id'))
            server_name = host.get('host').get('name')
            groups[host_group].append(server_name)

        return groups

    def read_settings(self):
        """Read the settings from the foreman.ini file"""
        config = ConfigParser.SafeConfigParser()
        foreman_default_ini_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'foreman.ini')
        foreman_ini_path = os.environ.get('FOREMAN_INI_PATH', foreman_default_ini_path)
        config.read(foreman_ini_path)
        self.base_url = config.get('foreman', 'base_url')
        self.username = config.get('foreman', 'username')
        self.password = config.get('foreman', 'password')

    def parse_cli_args(self):
        """Command line argument processing"""
        parser = optparse.OptionParser(description='Produce an Ansible Inventory file based on Foreman')
        parser.add_option('--list', action='store_true', default=True, help='List instances (default: True)')
        parser.add_option('--host', action='store', help='Get all the variables about a specific instance')
        (self.args, self.options) = parser.parse_args()


    def _get_from_id(self, param_name, param_id):
        """Get architecture from id"""
        " architecture, subnet, domain, compute_resource, model, environment, label, hostgroup, operatingsystem "
        param = self._get_object_from_id(param, param_id)
        if param is None:
            return None
        if param_name == "hostgroup":
            return param.get('label')
        elif param_name == 'operatingsystem':
            os_name = "{0}-{1}".format(os_obj.get('name'), os_obj.get('major'))
            return os_name
        else:
            result = param.get('name')
            if param_name == "environment":
                return result.lower()
            return result

    def _get_object_from_id(self, obj_type, obj_id):
        """Get an object from it's ID"""
        if obj_id is None:
            return None

        obj = self._cache.get(obj_type).get(obj_id, None)

        if obj is None:
            method_name = "show_{0}s".format(obj_type)
            func = getattr(self.client, method_name)
            obj = func(obj_id)
            self._cache[obj_type][obj_id] = obj

        return obj.get(obj_type)


ForemanInventory()

#  Copyright (c) 2018 Red Hat, Inc.
#
#  This file is part of ARA: Ansible Run Analysis.
#
#  ARA is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  ARA is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with ARA.  If not, see <http://www.gnu.org/licenses/>.

from ansible.plugins.action import ActionBase
from ansible import constants as ansible_constants

DOCUMENTATION = """
---
module: ara_record
short_description: Ansible module to record persistent data with ARA.
version_added: "2.0"
author: "David Moreau-Simard <dmsimard@redhat.com>"
description:
    - Ansible module to record persistent data with ARA.
options:
    playbook_id:
        description:
            - id of the playbook to write the key to
            - if not set, the module will use the ongoing playbook's id
        required: false
    key:
        description:
            - Name of the key to write data to
        required: true
    value:
        description:
            - Value of the key written to
        required: true
    type:
        description:
            - Type of the key
        choices: [text, url, json, list, dict]
        default: text

requirements:
    - "python >= 3.5"
    - "ara >= 1.0.0"
"""

EXAMPLES = """
- name: Associate specific data to a key for a playbook
  ara_record:
    key: "foo"
    value: "bar"

- name: Associate data to a playbook that previously ran
  ara_record:
    playbook_id: 21
    key: logs
    value: "{{ lookup('file', '/var/log/ansible.log') }}"
    type: text

- name: Retrieve the git version of the development repository
  shell: cd dev && git rev-parse HEAD
  register: git_version
  delegate_to: localhost

- name: Record and register the git version of the playbooks
  ara_record:
    key: "git_version"
    value: "{{ git_version.stdout }}"
  register: version

- name: Print recorded data
  debug:
    msg: "{{ version.playbook_id }} - {{ version.key }}: {{ version.value }}

# Write data with a type (otherwise defaults to "text")
# This changes the behavior on how the value is presented in the web interface
- name: Record different formats of things
  ara_record:
    key: "{{ item.key }}"
    value: "{{ item.value }}"
    type: "{{ item.type }}"
  with_items:
    - { key: "log", value: "error", type: "text" }
    - { key: "website", value: "http://domain.tld", type: "url" }
    - { key: "data", value: "{ 'key': 'value' }", type: "json" }
    - { key: "somelist", value: ['one', 'two'], type: "list" }
    - { key: "somedict", value: {'key': 'value' }, type: "dict" }
"""


class ActionModule(ActionBase):
    """ Record persistent data as key/value pairs in ARA """

    TRANSFERS_FILES = False
    VALID_ARGS = frozenset(('playbook_id', 'key', 'value', 'type'))
    VALID_TYPES = ['text', 'url', 'json', 'list', 'dict']

    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        # Retrieves the runtime plugin options for the ara_default callback plugin
        options = ansible_constants.config.get_plugin_options("callback", "ara_default")

        if options["api_client"] == "offline":
            self.client = AraOfflineClient()
        elif options["api_client"] == "http":
            self.client = AraHttpClient(endpoint=options["api_server"], timeout=options["timeout"])
        else:
            raise Exception("Unsupported API client: %s. Please use 'offline' or 'http'" % api_client)

#    def create_or_update_key(self, playbook_id, key, value, type):
#        # TODO: Need the client to return the response code
#        resp = self.client.get("/api/v1/records")
#        resp, exists = RecordApi().get(
#            playbook_id=playbook_id,
#            key=key
#        )
#        if resp.status_code == 404:
#            # TODO: Do a better job at validating this
#            resp, data = RecordApi().post(
#                playbook_id=playbook_id,
#                key=key,
#                value=value,
#                type=type
#            )
#        else:
#            # TODO: Do a better job at validating this
#            resp, data = RecordApi().patch(
#                id=exists[0]['id'],
#                key=key,
#                value=value,
#                type=type
#            )
#        return data

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        for arg in self._task.args:
            if arg not in self.VALID_ARGS:
                result = {
                    "failed": True,
                    "msg": '{0} is not a valid option.'.format(arg)
                }
                return result

        result = super(ActionModule, self).run(tmp, task_vars)

        playbook_id = self._task.args.get('playbook_id', None)
        key = self._task.args.get('key', None)
        value = self._task.args.get('value', None)
        type = self._task.args.get('type', 'text')

        required = ['key', 'value']
        for parameter in required:
            if not self._task.args.get(parameter):
                result['failed'] = True
                result['msg'] = "Parameter '{0}' is required".format(parameter)
                return result

        if type not in self.VALID_TYPES:
            result['failed'] = True
            msg = "Type '{0}' is not supported, choose one of: {1}".format(
                type, ", ".join(self.VALID_TYPES)
            )
            result['msg'] = msg
            return result

        if playbook_id is None:
            # We need to retrieve the playbook dynamically by working our way up from the play
            # self.client.get("/api/v1/plays", query={"uuid": self._play_context._uuid})

        try:
            data = self.create_or_update_key(playbook_id, key, value, type)
            result['key'] = data['key']
            result['value'] = data['value']
            result['type'] = data['type']
            result['playbook_id'] = data['playbook']['id']
            result['msg'] = 'Data recorded in ARA for this playbook.'
        except Exception as e:
            result['failed'] = True
            result['msg'] = 'Data not recorded in ARA: {0}'.format(str(e))
        return result

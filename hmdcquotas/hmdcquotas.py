#!/usr/bin/env python

__author__ = "Harvard-MIT Data Center DevOps"
__copyright__ = "Copyright 2018, HMDC"
__credits__ = ["Wesley Harrell", "Bradley Frank"]
__license__ = "GPL"
__maintainer__ = "HMDC"
__email__ = "ops@latte.harvard.edu"
__status__ = "Production"

from NaServer import *
import ConfigParser
import hmdclogger
import humanize
import re
import sys


class HMDCQuotas:
    """Tools for manipulating NetApp quotas using the NMSDK.

    Example:
        qh = HMDCQuotas()
        # Modify a group
        qh.modify(action, group, volume, vserver, policy, size, files)
        # Search everything
        qh.search_vservers(group)
        # Search all volumes
        qh.search_volumes(group, vserver)
        # Search when vserver and volume is known
        group_lookup(group, volume, vserver)

    Private Functions:
        _netapp_auth: Authenticates the vserver connections.
        _netapp_invoke: Handles add/delete/modify/search queries on the NetApp.
        _netapp_resize: Handles the resize query on the NetApp.

    Public Functions:
        convert_to_kb: Parses and converts given quota to KB.
        humanize_quotas: Makes NetApp quota results human readable.
        get_vserver: Returns the vserver of the given volume.
        group_lookup: Queries the NetApp for a group on a specific volume.
        modify: Preps and executes add/delete/modify queries.
        search_vservers: Finds group quota on any vserver/volume combination.
        search_volumes: Finds group quota on any volume in a specific vserver.

    Class Variables:
        CONFIG_FILE (string): Location of the conf file.
        DEFAULT_QUOTA (string): The quota value to use when none is specified.
        ERROR_MSG (string): Error message if raised.
        FILESIZES (dictionary): Valid filesize units and their kb multiplier.
        VOLUMES (dictionary): SVMs with their respective volumes.
    """

    CONFIG_FILE = '/etc/hmdcquotas.conf'

    DEFAULT_QUOTA = '5G'

    ERROR_MSG = ''

    FILESIZES = {'B': .0009765625,
                 'K': 1,
                 'M': 1024,
                 'G': 1048576,
                 'T': 1073741824}

    VOLUMES = {'nc-rce-svm01-mgmt': ('projects',
                                     'projects_nobackup',),
               'nc-bigdata-ci3-svm01-mgmt': ('bigdata_nobackup_ci3',
                                             'bigdata_ci3'),
               'nc-bigdata-svm02-mgmt': ('bigdata','bigdata_nobackup'),
               'nc-hmdc-svm01-mgmt': ('www',),
               'nc-nsaph-ci3-svm01-mgmt': ('nsaph_ci3',),
               'nc-projects-ci3-svm01-mgmt': ('projects_ci3',
                                              'projects_nobackup_ci3',),
               'nc-rshiny-svm01-mgmt': ('rshiny_ci3',) }

    def __init__(self, logger=None, debug_level=None, log_console=False,
                 log_file=False):
        """Initializes settings, logging, and creates connections to vservers.

        Arguments:
            debug_level (string): Level of debugging information to log.
            logger (instance): A previously instantiated HMDCLogger instance.
            log_console (boolean): Enable/disable logging to the console.
            log_file (string): Full path to log file; False if disabled.
        """

        config_name = self.__class__.__name__
        self.vservers = {}

        # Import conf file settings.
        conf = ConfigParser.ConfigParser()
        conf.read(self.CONFIG_FILE)

        self.options = {
            'debug_level': conf.get(config_name, 'debug_level'),
            'cdot_password': conf.get(config_name, 'cdot_password'),
            'cdot_username': conf.get(config_name, 'cdot_username'),
        }

        # Configure HMDC logging instance.
        if logger is None:
            if debug_level is None:
                debug_level = self.options['debug_level']
            self.hmdclog = hmdclogger.HMDCLogger(config_name, debug_level)
            if log_console:
                self.hmdclog.log_to_console()
            if log_file:
                self.hmdclog.log_to_file(log_file)
        else:
            self.hmdclog = logger

        # Instantiate and authenticate NetApp connections.
        for vserver in self.VOLUMES.iterkeys():
            # API major release 1, minor 20.
            self.vservers[vserver] = NaServer(vserver, 1, 20)
            # Authenticate to the NetApp.
            self._netapp_auth(vserver)

    def _netapp_auth(self, vserver):
        """Authenticates the vserver connections.

        Arguments:
            vserver (string): Name of the vserver to authenticate.
        """

        self.hmdclog.log('debug', "Authenticating \"" + vserver + "\"")
        svm = self.vservers[vserver]
        svm.set_style('LOGIN')
        svm.set_transport_type('HTTPS')
        svm.set_admin_user(self.options['cdot_username'],
                           self.options['cdot_password'])

    def _netapp_invoke(self, action, group, volume, vserver, policy,
                       disk_limit, file_limit):
        """Handles invokes to the NetApp: add/delete/modify/search queries.

        Arguments:
            action (string): Type of NetApp query.
            disk_limit (int): Group disk quota in KB.
            file_limit (int): Number of maximum files allowed for the group.
            group (string): Name of the LDAP group.
            policy (string): Name of the quota policy.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.
        """

        svm = self.vservers[vserver]

        # Convert the action to NetApp commands.
        if "add" in action:
            action = 'quota-add-entry'
            self.hmdclog.log('debug', "Recognized action: " + action)
        elif "delete" in action:
            action = 'quota-delete-entry'
            self.hmdclog.log('debug', "Recognized action: " + action)
        elif "modify" in action:
            action = 'quota-modify-entry'
            self.hmdclog.log('debug', "Recognized action: " + action)
        elif "get" in action or "search" in action:
            action = 'quota-get-entry'
            self.hmdclog.log('debug', "Recognized action: " + action)
        else:
            self.hmdclog.log('debug', "Unrecognized action: " + action)
            return (False, "Unknown action.")

        # Set a default quota policy.
        if not policy:
            policy = 'default'

        # Delete and search queries do not use disk_limit and file_limit.
        if "delete" in action or "get" in action:
            result = svm.invoke(action, 'policy', policy, 'qtree', '',
                                'quota-target', group, 'quota-type', 'group',
                                'volume', volume)
        elif "add" in action or "modify" in action:
            result = svm.invoke(action, 'policy', policy, 'qtree', '',
                                'quota-target', group, 'quota-type', 'group',
                                'volume', volume, 'disk-limit', disk_limit,
                                'soft-file-limit', file_limit)

        if result.results_status() == "failed":
            self.ERROR_MSG = result.results_reason()
            self.hmdclog.log('error', self.ERROR_MSG)
            return False
        else
            return result

    def _netapp_resize(self, volume, vserver):
        """Performs a quota resize on the NetApp to commit all quota changes.

        Arguments:
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.
        """

        svm = self.vservers[vserver]
        #
        # TODO: Need to find how to get results from quota-resize;
        #       the instance.results_*() does not work nor does
        #       instance.child_get_string("result-*").
        # UPDATE: According to NetApp SDK, this will have return codes
        #       0: result-error-code (code number, if error)
        #       1: result-error-message (description, if error)
        #       2: result-jobid (id of the job that was queued)
        #       3: result-status ("succeeded", "in-progress", "failed")
        #
        invoke = svm.invoke("quota-resize", "vserver", vserver,
                            "volume", volume)

    def convert_to_kb(self, disk_limit):
        """Converts almost any file size unit into KB.

        Arguments:
            disk_limit (string): Disk size in any unit, with unit label.
        """

        # Use regex to parse the disk quota into numeric values and units.
        match = re.match(r"([0-9]+)([a-z]+)", disk_limit, re.I)
        if match:
            items = match.groups()
        else:
            self.ERROR_MSG = "Unreadble disk quota format: " + disk_limit
            self.hmdclog.log('error', self.ERROR_MSG)
            return False

        size = int(items[0])
        unit = items[1][0].upper()

        self.hmdclog.log('debug', "Parsed disk quota: " + str(size) + unit)

        # Sanity check so the numbers don't get out of control.
        if unit in self.FILESIZES:
            disk_limit = size * self.FILESIZES[unit]
            _log_msg = "Converted disk quota: " + str(disk_limit)
            self.hmdclog.log('debug', _log_msg)
            return disk_limit
        else:
            self.ERROR_MSG = "Unrecognized unit: " + unit
            self.hmdclog.log('error', self.ERROR_MSG)
            return False

    def humanize_quotas(self, invoke):
        """Makes NetApp quota results human readable.

        Arguments:
            invoke (instance): Results from a NetApp query.
        """

        #
        # The quota-get-entry disk-limit API reports in KB, but humanize
        # translates bytes, therefore the * 1024.
        #
        disk_quota = invoke.child_get_string("disk-limit")
        self.hmdclog.log('debug', "Disk quota (raw): " + str(disk_quota))
        disk_quota = int(disk_quota) * 1024
        disk_quota = humanize.naturalsize(disk_quota, gnu=True)
        self.hmdclog.log('info', "Disk quota: " + str(disk_quota))

        file_quota = invoke.child_get_string("soft-file-limit")
        file_quota = str(file_quota)
        file_quota = None if file_quota == "-" else int(file_quota)
        self.hmdclog.log('info', "File quota: " + str(file_quota))

        return (disk_quota, file_quota)

    def get_vserver(self, volume_to_find):
        """Returns the vserver of the given volume.

        Arguments:
            volume_to_find (string): Name of the volume to search for.
        """

        for vserver, volumes in self.VOLUMES.iteritems():
            if volume_to_find in volumes:
                self.hmdclog.log('debug', "Found vserver " + vserver)
                return vserver
        else:
            self.ERROR_MSG = "Could not find volume " + volume_to_find + "."
            _log_msg = volume_to_find + "not found in VOLUMES dictionary"
            self.hmdclog.log('error', _log_msg)
            return False

    def group_lookup(self, group, policy, volume, vserver):
        """Queries the NetApp for a group on a specific vserver/volume.

        Arguments:
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.
        """

        result = self._netapp_invoke('search', group, volume, vserver, policy,
                                     None, None)

        if not result:
            self.ERROR_MSG = group + "not found on " + volume
            self.hmdclog.log('error', self.ERROR_MSG)
            return False
        else
            self.hmdclog.log('info', group + " found on " + volume)
            return True

    def modify(self, action, group, volume, vserver, policy, disk_limit=None,
               file_limit=None):
        """Preps disk and file quotas, then executes add/delete/modify queries.

        Arguments:
            action (string): Type of NetApp query.
            disk_limit (int): Group disk quota with unit.
            file_limit (int): Number of maximum files allowed for the group.
            group (string): Name of the LDAP group.
            policy (string): Name of the quota policy.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.
        """

        # Set the disk quota.
        if disk_limit is None:
            disk_limit = self.DEFAULT_QUOTA
            _log_msg = "Used default disk quota: " + str(self.DEFAULT_QUOTA)
            self.hmdclog.log('debug', _log_msg)

        disk_limit = self.convert_to_kb(disk_limit)

        if not disk_limit:
            return False

        # Set the file quota.
        if file_limit is None:
            file_limit = disk_limit / 16
            _log_msg = "Used default file quota: " + str(file_limit)
            self.hmdclog.log('debug', _log_msg)
        elif disk_limit % 16 != 0:
            self.hmdclog.log('warning', "File limit not normal.")

        # Perform the NetApp quota change.
        result = self._netapp_invoke(action, group, volume, vserver,
                                     policy, disk_limit, file_limit)

        if not result:
            return False
        else
            result = self._netapp_resize(volume, vserver)
            return True

    def search_vservers(self, group, policy, volume=None):
        """Finds group quota on any vserver/volume combination.

        Arguments:
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.
        """

        matches = {}

        if volume is None:
            # Volume was not specified.
            self.hmdclog.log('info', "Searching all vservers and volumes.")
            for vserver in self.VOLUMES.iterkeys():
                self.hmdclog.log('debug', "Searching " + vserver)
                result = self.search_volumes(group, policy, vserver)

                if not result:
                    return False
                elif len(result) > 0:
                    # Filters out empty result sets.
                    matches[vserver] = result
        else:
            # Volume was specified.
            result = self.get_vserver(volume)
            if not result:
                return False
            else
                vserver = result

            self.hmdclog.log('debug', "Searching " + vserver)

            result = self.group_lookup(group, policy, volume, vserver)

            if not result:
                return False
            else:
                quotas = self.humanize_quotas(result)
                # Each vserver with results becomes a dictionary.
                matches[vserver] = {volume: quotas}

        return matches

    def search_volumes(self, group, policy, vserver):
        """Finds group quota on any volume in a specific vserver.

        Arguments:
            group (string): Name of the LDAP group.
            vserver (string): The vserver to search.
        """

        matches = {}

        for volume in self.VOLUMES[vserver]:
            self.hmdclog.log('debug', "Searching " + volume)

            result = self.group_lookup(group, policy, volume, vserver)

            if not result:
                return False
            else
                quotas = self.humanize_quotas(result)
                # Each volume with results becomes a dictionary.
                matches[volume] = quotas

        return matches

if __name__ == '__main__':
    pass

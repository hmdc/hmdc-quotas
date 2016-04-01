#!/usr/bin/env python

__author__ = "Harvard-MIT Data Center DevOps"
__copyright__ = "Copyright 2014, HMDC"
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
        qh.modify(action, group,  volume, vserver, size, files)
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
        FILESIZES (dictionary): Valid filesize units and their kb multiplier.
        JERK_FILESIZES (tuple): Invalid filesize units.
        VOLUMES (dictionary): SVMs with their respective volumes.
    """

    CONFIG_FILE = '/etc/hmdcquotas.conf'

    DEFAULT_QUOTA = '5G'

    FILESIZES = {'B': .0009765625,
                 'K': 1,
                 'M': 1024,
                 'G': 1048576,
                 'T': 1073741824}
    JERK_FILESIZES = ('P', 'E', 'Z', 'Y')

    VOLUMES = {'nc-rce-svm01-mgmt': ('projects',
                                     'projects_nobackup',
                                     'projects_ci3',
                                     'projects_nobackup_ci3'),
               'nc-hmdc-svm01-mgmt': ('www',),
               'nc-rshiny-svm01-mgmt': ('rshiny_ci3',) }

    def __init__(self, logger=None, debug_level=None, log_console=False, log_file=False):
        """Initializes settings, logging, and creates connections to vservers.

        Arguments:
            debug_level (string): Level of debugging information to log.
            logger (instance): A previously instantiated HMDCLogger instance.
            log_console (boolean): Enable/disable logging to the console.
            log_file (string): Full path to log file; False if disabled.

        Attributes:
            config_name (string): Class name for referencing.
            hmdclog (instance): Instance of HMDCLogger for logging.
            options (dictionary): Settings imported from conf file.
            vservers (dictionary): Instances of NaServer (NetApp).
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

        Attributes:
            svm (instance): The NetApp instance to authenticate.
        """

        self.hmdclog.log('debug', "Authenticating \"" + vserver + "\"")
        svm = self.vservers[vserver]
        svm.set_style('LOGIN')
        svm.set_transport_type('HTTPS')
        svm.set_admin_user(self.options['cdot_username'],
                           self.options['cdot_password'])

    def _netapp_invoke(self, action, group, volume, vserver, disk_limit, file_limit):
        """Handles invokes to the NetApp: add/delete/modify/search queries.

        Arguments:
            action (string): Type of NetApp query.
            disk_limit (int): Group disk quota in KB.
            file_limit (int): Number of maximum files allowed for the group.
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.

        Attributes:
            action (string): Argument converted into a NetApp command.
            invoke (instance): Query sent to the NetApp.
            svm (instance): The NetApp instance for querying.

        Returns (tuple):
            [0] (boolean): Success of executing query.
            [1] (string/instance): Error message, or upon success, invoke.
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

        # Delete and search queries do not use disk_limit and file_limit.
        if "delete" in action or "get" in action:
            invoke = svm.invoke(action, 'qtree', '', 'quota-target', group,
                                'quota-type', 'group', 'volume', volume)
        elif "add" in action or "modify" in action:
            invoke = svm.invoke(action, 'qtree', '', 'quota-target', group,
                                'quota-type', 'group', 'volume', volume,
                                'disk-limit', disk_limit, 'soft-file-limit',
                                file_limit)

        return (True, invoke)

    def _netapp_resize(self, volume, vserver):
        """Placeholder function for eventual change in NetApp SDK.

        Arguments:
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.

        Attributes:
            svm (instance): The NetApp instance for querying.

        Returns (tuple):
            [0] (boolean): Success of executing query.
            [1] (placeholder)
        """

        svm = self.vservers[vserver]
        #
        # TODO: Need to find how to get results from quota-resize;
        #       the instance.results_*() does not work nor does
        #       instance.child_get_string("result-*").
        #
        svm.invoke("quota-resize", "volume", volume)

        return (True, None)

    def convert_to_kb(self, disk_limit):
        """Converts almost any file size unit into KB.

        Arguments:
            disk_limit (string): Disk size in any unit, with unit label.

        Attributes:
            match (re): Regex parse disk_limit to find size and unit.
            size (int): The requested disk limit size.
            unit (string): The file size unit of disk_limit.

        Returns (tuple):
            [0] (boolean): Success of executing request.
            [1] (string/int): Error message, or upon success, disk quota in KB.
        """

        # Use regex to parse the disk quota into numeric values and units.
        match = re.match(r"([0-9]+)([a-z]+)", disk_limit, re.I)
        if match:
            items = match.groups()
        else:
            self.hmdclog.log('error', "Unreadble disk quota format: " + disk_limit)
            return (False, "Unrecognized disk quota format.")

        size = int(items[0])
        unit = items[1][0].upper()

        self.hmdclog.log('debug', "Parsed disk quota: " + str(size) + unit)

        # Sanity check so the numbers don't get out of control.
        if unit in self.JERK_FILESIZES:
            self.hmdclog.log('error', "Quota entered in unhandled unit.")
            return (False, "Enter quota as terabytes or lower.")
        elif unit in self.FILESIZES:
            disk_limit = size * self.FILESIZES[unit]
            self.hmdclog.log('debug', "Converted disk quota: " + str(disk_limit))
            return (True, disk_limit)
        else:
            self.hmdclog.log('error', "Unrecognized unit: " + unit)
            return (False, "Unrecognized disk size unit.")

    def humanize_quotas(self, invoke):
        """Makes NetApp quota results human readable.

        Arguments:
            invoke (instance): Results from a NetApp query.

        Returns (tuple):
            [0] (int): Disk quota.
            [1] (int): File quota.
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

        Returns (tuple):
            [0] (boolean): Success of executing query.
            [1] (string/instance): Error message, or upon success, vserver.
        """

        for vserver, volumes in self.VOLUMES.iteritems():
            if volume_to_find in volumes:
                self.hmdclog.log('debug', "Found vserver \"" + vserver + "\" in VOLUMES dictionary")
                return (True, vserver)
        else:
            self.hmdclog.log('debug', "No \"" + volume_to_find + "\" in VOLUMES dictionary")
            return (False, "Did not find a matching vserver for volume \"" + volume_to_find + "\".")

    def group_lookup(self, group, volume, vserver):
        """Queries the NetApp for a group on a specific vserver/volume.

        Arguments:
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.

        Attributes:
            reason (string): Error message from NetApp if query failed.
            result (mixed): Value returned by called function.
            success (boolean): Result of running the query.

        Returns (tuple):
            [0] (boolean): Success of executing query.
            [1] (string/instance): Error message, or upon success, invoke.
        """

        success, result = self._netapp_invoke('search', group, volume, vserver, None, None)
        if success:
            reason = result.results_reason()
        else:
            return (False, result)

        if reason is None:
            # reason is blank if the group was found.
            self.hmdclog.log('info', "Group \"" + group +
                             "\" found on volume \"" + volume + "\"")
            return (True, result)
        else:
            if "entry doesn't exist" in reason:
                # No errors, but the group wasn't found.
                self.hmdclog.log('info', "Group \"" + group +
                                 "\" not found on volume \"" + volume + "\"")
                return (False, None)
            else:
                # There was an actual error with the query.
                self.hmdclog.log('error', reason)
                return (False, reason)

    def modify(self, action, group, volume, vserver, disk_limit=None, file_limit=None):
        """Preps disk and file quotas, then executes add/delete/modify queries.

        Arguments:
            action (string): Type of NetApp query.
            disk_limit (int): Group disk quota with unit.
            file_limit (int): Number of maximum files allowed for the group.
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.
            vserver (string): The vserver the volume lives on.

        Attributes:
            disk_limit (int): Converted disk quota in KB.
            file_limit (int): Number of maximum files allowed for the group.
            reason (string): Error message from NetApp if query failed.
            result (mixed): Value returned by called function.
            success (boolean): Result of running the query.

        Returns (tuple):
            [0] (boolean): Success of executing request.
            [1] (string/None): Error message, or upon success, None.
        """

        # Set the disk quota.
        if disk_limit is None:
            disk_limit = self.DEFAULT_QUOTA
            self.hmdclog.log('debug', "Used default disk quota: " + str(self.DEFAULT_QUOTA))

        success, result = self.convert_to_kb(disk_limit)
        if not success:
            return (False, result)
        else:
            disk_limit = result

        # Set the file quota.
        if file_limit is None:
            file_limit = disk_limit / 16
            self.hmdclog.log('debug', "Used default file quota: " + str(file_limit))
        elif disk_limit % 16 != 0:
            self.hmdclog.log('warning', "File limit not normal.")

        # Perform the NetApp quota change.
        sucess, result = self._netapp_invoke(action, group, volume, vserver,
                                             disk_limit, file_limit)
        if success:
            reason = result.results_reason()
        else:
            return (False, result)

        if reason is None:
            # reason is blank if no errors; perform the resize.
            success, result = self._netapp_resize(volume, vserver)
            if success:
                return (True, None)
            else:
                return (False, "Unknown error with resize.")
        else:
            self.hmdclog.log('error', reason)
            return (False, reason)

    def search_vservers(self, group, volume=None):
        """Finds group quota on any vserver/volume combination.

        Arguments:
            group (string): Name of the LDAP group.
            volume (string): The volume where the group quota resides.

        Attributes:
            matches (dictionary): Each vserver where quotas were found.
            result (mixed): Value returned by called function.
            success (boolean): Result of running the query.
            vserver (string): The vserver to search.

        Returns (tuple):
            [0] (boolean) Success or failure.
            [1] (string/dictionary): Error message, or upon success, matches.
        """

        matches = {}

        if volume is None:
            # Volume was not specified.
            self.hmdclog.log('info', "Searching all vservers and volumes.")
            for vserver in self.VOLUMES.iterkeys():
                self.hmdclog.log('debug', "Searching vserver \"" + vserver + "\"")

                success, result = self.search_volumes(group, vserver)
                if not success:
                    self.hmdclog.log('error', result)
                    return (False, result)
                elif len(result) > 0:
                    # Filters out empty result sets.
                    matches[vserver] = result
        else:
            # Volume was specified.
            success, result = self.get_vserver(volume)
            if success:
                vserver = result
            else:
                return (False, result)

            self.hmdclog.log('debug', "Searching vserver \"" + vserver + "\"")

            success, result = self.group_lookup(group, volume, vserver)
            if success:
                quotas = self.humanize_quotas(result)
                # Each vserver with results becomes a dictionary.
                matches[vserver] = {volume: quotas}
            else:
                # result has content only if there was an error.
                if result is not None:
                    return (False, result)

        return (True, matches)

    def search_volumes(self, group, vserver):
        """Finds group quota on any volume in a specific vserver.

        Arguments:
            group (string): Name of the LDAP group.
            vserver (string): The vserver to search.

        Attributes:
            matches (dictionary): Each volume where quotas were found.
            result (mixed): Value returned by called function.

        Returns (tuple):
            [0] (boolean) Success or failure.
            [1] (string/dictionary): Error message, or upon success, matches.
        """

        matches = {}

        for volume in self.VOLUMES[vserver]:
            self.hmdclog.log('debug', "Searching volume \"" + volume + "\"")

            success, result = self.group_lookup(group, volume, vserver)
            if success:
                quotas = self.humanize_quotas(result)
                # Each volume with results becomes a dictionary.
                matches[volume] = quotas
            else:
                # result has content only if there was an error.
                if result is not None:
                    return (False, result)

        return (True, matches)

if __name__ == '__main__':
    pass

#!/usr/bin/env python

__author__ = "Harvard-MIT Data Center DevOps"
__copyright__ = "Copyright 2014, HMDC"
__credits__ = ["Wesley Harrell", "Bradley Frank"]
__license__ = "GPL"
__maintainer__ = "HMDC"
__email__ = "ops@latte.harvard.edu"
__status__ = "Production"

"""
Script for manipulating group quotas on the NetApp using the Quotas module.

Public Functions:
    modify_quota: Preps and calls add/delete/modify NetApp queries.
    print_quotas: Formats the quota results for printing to console.
    search_quotas: Preps and calls search NetApp queries.
"""

from hmdclogger import HMDCLogger
from hmdcquotas import hmdcquotas
import argparse

def modify_quota(args, qh, hmdclog):
    """Checks requirements, then calls appropriate function from Quotas module.

    Arguments:
        args (object): Namespace object of parsed arguments.
        qh (object): Quotas object handler.
        hmdclog (object): HMDCLogger object handler.

    Attributes:
        result (mixed): Value returned by called function.
        success (boolean): Result of running the query.
        vserver (string): The vserver to search.

    Returns (tuple):
        [0] (boolean): Success of executing request.
        [1] (string/None): Error message, or upon success, None.
    """

    # Volume is required because of duplicate group names.
    if args.volume is None:
        hmdclog.log('error', "No volume specified in query")
        return (False, "Error: You need to specify a volume.")

    # Find the right vserver to use.
    success, result = qh.get_vserver(args.volume)
    if success:
        vserver = result
    else:
        return (False, result)

    # Determine specific modify action (add/delete/modify).
    if args.action == 'A':
        action = 'add'
    elif args.action == 'D':
        action = 'delete'
    elif args.action == 'M':
        action = 'modify'
    else:
        return (False, "Unhandled action.")

    # Perform the NetApp quota change.
    success, result = qh.modify(action, args.group, args.volume, vserver,
                                args.size, args.files)
    if not success:
        return (False, "An error occurred while modifying quota: " + result)
    else:
        return (True, None)


def print_quotas(results):
    """Iterates through the results to print a formatted list of quotas.

    Arguments:
        results (dictionary): Each vserver and volume where quotas were found.

    Attributes:
        disk_quota (string): Disk quota displayed in GB.
        file_quota (string): File quota displayed by number of files.
        output (string): Format of output for use in a chart-layout.
        svm (string): Name of the vserver where quotas were found.
    """

    output = "{:<15} {:<25} {:>5} {:>15} {:>15}"

    print output.format("GROUP", "VOLUME", "SVM", "DISK QUOTA", "FILE QUOTA")
    for vserver, volumes in results.iteritems():
        for name, quotas in volumes.iteritems():
            disk_quota, file_quota = quotas
            svm = vserver.split('-')[1]
            print output.format(args.group, name, svm, disk_quota, file_quota)


def search_quotas(args, qh, hmdclog):
    """Calls functions from Quotas module to search for quotas.

    Arguments:
        args (object): Namespace object of parsed arguments.
        qh (object): Quotas object handler.
        hmdclog (object): HMDCLogger object handler.

    Attributes:
        result (mixed): Value returned by called function.
        success (boolean): Result of running the query.
    """

    success, result = qh.search_vservers(args.group, args.volume)
    if not success:
        print("Error: " + result)
    elif len(result) < 1:
        hmdclog.log('debug', "No matches for group \"" + args.group + "\" were found")
        print("No matches for group \"" + args.group + "\" were found.")
    else:
        print_quotas(result)


# Setup argument parsing with the argparse module.
parser = argparse.ArgumentParser(description="Manage RCE group quotas.")
parser.add_argument('-d', '--debug', action='store_true',
                    help="Enables verbose output.")
parser.add_argument('-a', '--action', required=True, choices=['A', 'D', 'M', 'S'],
                    help="Add | Delete | Modify | Search")
parser.add_argument('-g', '--group', required=True,
                    help="Name of the group.")
parser.add_argument('-v', '--volume', choices=['projects', 'projects_nobackup',
                    'projects_ci3', 'projects_nobackup_ci3', 'www'],
                    help="The NetApp volume.")
parser.add_argument('-s', '--size',
                    help="Size of the disk quota.")
parser.add_argument('-f', '--files', type=int,
                    help="Maximum number of files.")
args = parser.parse_args()

# Set logging level based on the debug argument.
debug_level = 'DEBUG' if args.debug else 'NOTSET'
hmdclog = HMDCLogger("QuotasUtil", debug_level)
hmdclog.log_to_console()

# Instantiate a Quotas class handler.
qh = HMDCQuotas(hmdclog)

# Determine action to perform.
if args.action == 'S':
    search_quotas(args, qh, hmdclog)
else:
    success, result = modify_quota(args, qh, hmdclog)
    if success:
        if args.action == 'D':
            print("Quota successfully deleted.")
        else:
            print("Quota successfully modified.")
            search_quotas(args, qh, hmdclog)
    else:
        print(result)

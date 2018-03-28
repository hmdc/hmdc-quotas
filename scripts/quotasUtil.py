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

ERROR_MSG = ""

import hmdcquotas
import hmdclogger
import argparse

def modify_quota(args, qh, hmdclog):
    """Checks requirements, then calls appropriate function from Quotas module.

    Arguments:
        args (object): Namespace object of parsed arguments.
        qh (object): Quotas object handler.
        hmdclog (object): HMDCLogger object handler.
    """

    # Volume is required because of duplicate group names.
    if args.volume is None:
        hmdclog.log('error', "No volume specified in query")
        ERROR_MSG = "Error: You need to specify a volume."
        return False

    # Find the right vserver to use.
    vserver = qh.get_vserver(args.volume)
    if not vserver:
        return False

    # Determine specific modify action (add/delete/modify).
    if args.action == 'A':
        action = 'add'
    elif args.action == 'D':
        action = 'delete'
    elif args.action == 'M':
        action = 'modify'
    else:
        ERROR_MSG = "Unhandled action."
        return False

    # Perform the NetApp quota change.
    result = qh.modify(action, args.group, args.volume, vserver,
                       args.policy, args.size, args.files)
    if not result:
        ERROR_MSG = "An error occurred while modifying quota: " + qh.ERROR_MSG
        return False
    else:
        return True


def print_quotas(results):
    """Iterates through the results to print a formatted list of quotas.

    Arguments:
        results (dictionary): Each vserver and volume where quotas were found.
    """

    output = "{0:<15} {1:<25} {2:>5} {3:>15} {4:>15}"

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
    """

    result = qh.search_vservers(args.group, args.policy, args.volume)

    if not result:
        print("Error: " + qh.ERROR_MSG)
    elif len(result) < 1:
        ERROR_MSG = "No matches for " + args.group + " were found."
        hmdclog.log('debug', ERROR_MSG)
        print(ERROR_MSG)
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
parser.add_argument('-v', '--volume', choices=[
                        'projects', 'projects_nobackup',
                        'projects_ci3', 'projects_nobackup_ci3',
                        'www', 'rshiny_ci3', 'bigdata', 'bigdata_ci3',
                        'bigdata_nobackup', 'bigdata_nobackup_ci3', 'nsaph_ci3'],
                    help="The NetApp volume.")
parser.add_argument('-s', '--size',
                    help="Size of the disk quota.")
parser.add_argument('-p', '--policy',
                    help="Name of the quota policy to use. (Optional)")
parser.add_argument('-f', '--files', type=int,
                    help="Maximum number of files. (Optional)")
args = parser.parse_args()

# Set logging level based on the debug argument.
debug_level = 'DEBUG' if args.debug else 'NOTSET'
hmdclog = hmdclogger.HMDCLogger("QuotasUtil", debug_level)
hmdclog.log_to_console()

# Instantiate a Quotas class handler.
qh = hmdcquotas.HMDCQuotas(hmdclog)

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

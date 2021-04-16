#!/usr/bin/env python

import os
import json
import requests
import sys
import argparse
from datetime import datetime, timedelta
import logging

QUAY_API_TOKEN_NAME = 'QUAY_API_TOKEN'
QUAY_ORG_DEFAULT = 'redhat-cop'
QUAY_HOSTNAME_DEFAULT = 'quay.io'


def valid_date(s):
    try:
        return datetime.strptime("{} UTC".format(s), "%Y-%m-%d %Z")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def generate_default_date():
    today_date = datetime.now()
    return datetime.strptime("{0}-{1}-{02}".format(
        today_date.year, today_date.month, today_date.day), "%Y-%m-%d")


def get_logs(session, url, params, next_page):

    if next_page is not None:
        params["next_page"] = next_page

    log_request = session.get(url, params=params)
    log_request.raise_for_status()

    log_request_json = log_request.json()

    if 'next_page' in log_request_json:
        return log_request.json()['logs'] + get_logs(session, url, params, log_request_json['next_page'])
    else:
        return log_request.json()['logs']


def print_repository_statistics(organization, repository, logs):
    print(
        "\n- Repository '{1}' -\n".format(organization, repository))

    if len(logs) > 0:
        country_count = {}

        for log in logs:
            if log['kind'] == 'pull_repo':
                if 'resolved_ip' in log['metadata']:

                    if log['metadata']['resolved_ip']['country_iso_code'] not in country_count:
                        country_count[log['metadata']
                                      ['resolved_ip']['country_iso_code']] = 1
                    else:
                        country_count[log['metadata']['resolved_ip']['country_iso_code']
                                      ] = int(country_count[log['metadata']['resolved_ip']['country_iso_code']]) + 1

        print("Earliest Record: {}".format(logs[-1]['datetime']))
        print("Most Recent Record: {}".format(logs[0]['datetime']))

        print(
            "\nCountry Counts:")

        for country_key in country_count.keys():
            print("{} - {}".format(country_key, country_count[country_key]))
    else:
        print("No Records Found")


parser = argparse.ArgumentParser(description='Gather GitHub Statistics.')
parser.add_argument("-s", "--start-date",
                    help="The start date to query from", type=valid_date)
parser.add_argument("-o", "--organization",
                    help="Organization name", default=QUAY_ORG_DEFAULT)
parser.add_argument("-r", "--repositories",
                    help="Repositories", nargs='+', default=[])
parser.add_argument("-q", "--quay",
                    help="Quay hostname", default=QUAY_HOSTNAME_DEFAULT)
args = parser.parse_args()

repositories = args.repositories
start_date = args.start_date
organization = args.organization
quay_host = args.quay

current_date = datetime.utcnow()

if start_date is None:
    start_date = generate_default_date()

if start_date > current_date:
    print("Start date cannot be greater than current date")


quay_api_token = os.environ.get(QUAY_API_TOKEN_NAME)

if not quay_api_token:
    print("Error: Quay API Key is Required!")
    sys.exit(1)


session = requests.Session()
session.headers = {
    'Authorization': 'Bearer {0}'.format(quay_api_token),
    'Accept': "application/json"
}

if len(repositories) > 0:
    print(
        "=== Statistics for Quay Organization '{0}' ====\n".format(organization))

for repository in repositories:

    logs = []
    current_repository_start_date = start_date
    while True:
        params = {
            "starttime": current_repository_start_date.strftime("%m/%d/%Y"),
            "endtime": current_repository_start_date.strftime("%m/%d/%Y")
        }

        url = "https://{}/api/v1/repository/{}/{}/logs".format(
            quay_host, organization, repository)

        logs.extend(get_logs(session, url, params, None))

        current_repository_start_date = current_repository_start_date + \
            timedelta(days=1)

        if current_repository_start_date > current_date:
            break

    print_repository_statistics(organization, repository, logs)

#!/usr/bin/env python

import os, json, requests, sys, pytz, argparse, dateutil.parser
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Fill in GitHub Token
GITLAB_API_TOKEN_NAME = 'GITLAB_API_TOKEN'
GITLAB_GROUP_NAME = 'GITLAB_GROUP'
GITLAB_SERVER_NAME = 'GITLAB_SERVER'
GITLAB_SERVER_DEFAULT = 'https://gitlab.consulting.redhat.com'
GITLAB_GROUP_DEFAULT ='redhat-cop'
DEFAULT_START_DATE_MONTH = '03'
DEFAULT_START_DATE_DAY = '01'

merged_mrs = {}

def encode_text(text):
    if text:
        return text.encode("utf-8")

    return text

def generate_start_date():
    today_date = datetime.now()
    target_start_date = datetime.strptime("{0}-{1}-{02}".format(today_date.year, DEFAULT_START_DATE_MONTH, DEFAULT_START_DATE_DAY), "%Y-%m-%d")

    if target_start_date.month < int(DEFAULT_START_DATE_MONTH):
        target_start_date = target_start_date - relativedelta(years=1)

    return target_start_date

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def handle_pagination_items(session, url):
    
    pagination_request = session.get(url)
    pagination_request.raise_for_status()

    if 'next' in pagination_request.headers["Link"] and pagination_request.links['next']:
        print pagination_request.links['next']['url']
        return pagination_request.json() + handle_pagination_items(session, pagination_request.links['next']['url'])
    else:
        return pagination_request.json()

def get_group_projects(session, server, group_id):
    group_projects = handle_pagination_items(session, "{0}/api/v4/groups/{1}/projects".format(server,group_id))

    return group_projects

def get_group_with_projects(session, server, group_name):
    groups = handle_pagination_items(session, "{0}/api/v4/groups?search={1}".format(server,group_name))

    for group in groups:

        if group_name == group["path"]:
            group['projects'] = get_group_projects(session, server, group["id"])
            return group

def is_merge_request_in_project_group(merge_request, group):
    for project in group["projects"]:
        if project["id"] == merge_request["target_project_id"]:
            return True
    
    return False

def get_group_merge_requests(session, server, group):
    all_merge_requests = handle_pagination_items(session, "{0}/api/v4/merge_requests?state=merged&scope=all&per_page=1000".format(server))

    return [item for item in all_merge_requests if is_merge_request_in_project_group(item, group)]


parser = argparse.ArgumentParser(description='Gather GitLab Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u","--username", help="Username to query")
parser.add_argument("-l","--labels", help="Comma separated list to display. Add '-' at end of each label to negate")
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels


if start_date is None:
    start_date = generate_start_date()

start_date = pytz.utc.localize(start_date)

gitlab_api_token = os.environ.get(GITLAB_API_TOKEN_NAME)
gitlab_group = os.getenv(GITLAB_GROUP_NAME, GITLAB_GROUP_DEFAULT)
gitlab_server = os.getenv(GITLAB_SERVER_NAME, GITLAB_SERVER_DEFAULT)

if not gitlab_api_token:
    print "Error: GitLab API Key is Required!"
    sys.exit(1)

session = requests.Session()
session.headers = {
    'Private-Token': gitlab_api_token
}

group = get_group_with_projects(session ,gitlab_server, gitlab_group)

if group is None:
    print "Unable to Locate Group!"
    sys.exit(1)

group_merge_requests = get_group_merge_requests(session, gitlab_server, group)

for group_merge_request in group_merge_requests:
    
    # Skip items that do not have a valid updated_at datetime
    if dateutil.parser.parse(group_merge_request["updated_at"]) < start_date:
        continue
    
    merge_request_author_login = group_merge_request["author"]["username"]

    #Filter out unwanted mr users
    if username is not None and merge_request_author_login != username:
        continue

    if merge_request_author_login not in merged_mrs:
        merge_request_author_prs = []
    else:
        merge_request_author_prs = merged_mrs[merge_request_author_login]
    
    merge_request_author_prs.append(group_merge_request)
    merged_mrs[merge_request_author_login] = merge_request_author_prs

print "=== Statistics for GitLab Group '{0}' ====".format(gitlab_group)

print "\n== Merged MR's ==\n"

for key, value in merged_mrs.iteritems():
    print "{0} - {1}".format(value[0]["author"]["username"], len(value))
    for mr_value in value:
        print "   {0} - {1}".format(encode_text(mr_value['web_url'].split('/')[-3]), encode_text(mr_value['title']))


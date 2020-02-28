#!/usr/bin/env python

import os, json, requests, sys, pytz, argparse, dateutil.parser, re
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
DEFAULT_POINTS_GROUPING = 'Merge Requests'
merged_mrs = {}

req_group = 0
req_pagination = 0
is_debug = False


def encode_text(text):
    if text:
        return text.encode("utf-8")

    return text

def generate_start_date():
    today_date = datetime.now()
    target_start_date = datetime.strptime("{0}-{1}-{02}".format(today_date.year, DEFAULT_START_DATE_MONTH, DEFAULT_START_DATE_DAY), "%Y-%m-%d")

    if today_date.month < int(DEFAULT_START_DATE_MONTH):
        target_start_date = target_start_date - relativedelta(years=1)

    return target_start_date

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def handle_pagination_items(session, url):
    if is_debug: print "DEBUG:: handle_pagination_items(): url = {0}".format(url)
    pagination_request = session.get(url)
    pagination_request.raise_for_status()
    global req_pagination
    req_pagination+=1

    if 'next' in pagination_request.headers["Link"] and pagination_request.links['next']:
        return pagination_request.json() + handle_pagination_items(session, pagination_request.links['next']['url'])
    else:
        return pagination_request.json()


def get_group_with_projects(session, server, group_name):
    #groups = handle_pagination_items(session, "{0}/api/v4/groups?search={1}".format(server,group_name))
    groups = session.get("{0}/api/v4/groups/{1}".format(server,group_name))
    global req_group
    req_group+=1
    groups.raise_for_status()
    return groups.json()

def is_merge_request_in_project_group(merge_request, group, repo_matcher, repo_excluder):
    for project in group["projects"]:
        repo_name_matches = True if re.match(repo_matcher, project["name"]) != None else False
        repo_name_excluded = True if None != repo_excluder and re.match(repo_excluder, project["name"]) != None else False
        if repo_name_matches and repo_name_excluded == False and (project["id"] == merge_request["target_project_id"]):
            return True
    
    return False

def get_group_merge_requests(session, server, group, repo_matcher, repo_excluder, start_date):
    all_merge_requests = handle_pagination_items(session, "{0}/api/v4/merge_requests?state=merged&scope=all&per_page=1000&created_after={1}".format(server, start_date.strftime("%Y-%m-%d")))
    return [item for item in all_merge_requests if is_merge_request_in_project_group(item, group, repo_matcher, repo_excluder)]

parser = argparse.ArgumentParser(description='Gather GitLab Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u","--username", help="Username to query")
parser.add_argument("-l","--labels", help="Comma separated list to display. Add '-' at end of each label to negate")
parser.add_argument("-r","--human-readable", help="Human readable display")
parser.add_argument("-o","--organization", help="Organization name", default=GITLAB_GROUP_DEFAULT)
parser.add_argument("-p","--points-grouping", help="Points Bucket", default=DEFAULT_POINTS_GROUPING)
parser.add_argument("-m","--repo-matcher", help="Repo Matcher", default=".+")
parser.add_argument("-x","--repo-excluder", help="Repo Excluder")
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels
human_readable = args.human_readable is not None
gitlab_group = args.organization
points_grouping = args.points_grouping
repo_matcher = args.repo_matcher
repo_excluder = args.repo_excluder

if start_date is None:
    start_date = generate_start_date()
start_date = pytz.utc.localize(start_date)

#print "Config:\n  - gitlab_group:    {0}\n  - points_grouping: {1}\n  - repo_matcher:    {2}\n  - repo_excluder:   {3}\n".format(gitlab_group, points_grouping, repo_matcher, repo_excluder)

gitlab_api_token = os.environ.get(GITLAB_API_TOKEN_NAME)
gitlab_server = os.getenv(GITLAB_SERVER_NAME, GITLAB_SERVER_DEFAULT)

if not gitlab_api_token:
    print "Error: GitLab API Token is Required!"
    sys.exit(1)

session = requests.Session()
session.headers = {
    'Private-Token': gitlab_api_token
}

group = get_group_with_projects(session ,gitlab_server, gitlab_group)


if group is None:
    print "Unable to Locate Group!"
    sys.exit(1)

group_merge_requests = get_group_merge_requests(session, gitlab_server, group, repo_matcher, repo_excluder, start_date)

for group_merge_request in group_merge_requests:
    
    # Skip items that do not have a valid updated_at datetime
    if dateutil.parser.parse(group_merge_request["updated_at"]) < start_date:
        if is_debug: print "DEBUG:: Omit {0} MR {1} {2}/{3}".format(group_merge_request["state"], group_merge_request["updated_at"], group_merge_request['id'], group_merge_request['title'])
        continue
    if is_debug: print "DEBUG:: Incl {0} MR {1} {2}/{3}".format(group_merge_request["state"], group_merge_request["updated_at"], group_merge_request['id'], group_merge_request['title'])
    
    if not human_readable:
        print "{0}/GL{1}/{2}/{3}".format(points_grouping, group_merge_request['id'], group_merge_request['author']['username'], 1) # 1 points for all closed MR's
    
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


if is_debug: print "DEBUG:: requests made: group={0}, pagination={1}".format(req_group, req_pagination)

if not human_readable:
    sys.exit(0)

print "=== Statistics for GitLab Group '{0}' ====".format(gitlab_group)

print "\n== Merged MR's ==\n"

for key, value in merged_mrs.iteritems():
    print "{0} - {1}".format(value[0]["author"]["username"], len(value))
    for mr_value in value:
        print "   {0} - {1}".format(encode_text(mr_value['web_url'].split('/')[-3]), encode_text(mr_value['title']))


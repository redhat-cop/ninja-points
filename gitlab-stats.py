#!/usr/bin/env python

import os
import json
import requests
import sys
import pytz
import argparse
import dateutil.parser
import urllib
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Fill in GitHub Token
GITLAB_API_TOKEN_NAME = 'GITLAB_API_TOKEN'
GITLAB_GROUP_NAME = 'GITLAB_GROUP'
GITLAB_SERVER_NAME = 'GITLAB_SERVER'
GITLAB_SERVER_DEFAULT = 'https://gitlab.consulting.redhat.com'
GITLAB_GROUP_DEFAULT = 'redhat-cop'
DEFAULT_START_DATE_MONTH = '03'
DEFAULT_START_DATE_DAY = '01'
merged_mrs = {}
closed_issues = {}
reviewed_mrs = {}
project_cache = {}

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
    if is_debug:
        print "DEBUG:: handle_pagination_items(): url = {0}".format(url)
    pagination_request = session.get(url)
    pagination_request.raise_for_status()

    if 'link' in pagination_request.headers and 'next' in pagination_request.headers["Link"] and pagination_request.links['next']:
        return pagination_request.json() + handle_pagination_items(session, pagination_request.links['next']['url'])
    else:
        return pagination_request.json()

def get_group(session, server, group_name):
    group = session.get("{0}/api/v4/groups/{1}".format(server, urllib.quote(group_name, safe='')))
    global req_group
    result = group.json()

    if is_debug:
        print "DEBUG:: Group Data"
        print "  {0}".format(json.dumps(result, indent=4, sort_keys=True))

    return result

def get_project(session, project_id):
    if project_id not in project_cache:
        project_request = session.get("{0}/api/v4/projects/{1}".format(gitlab_server, project_id))
        project_request.raise_for_status()
        project_cache[project_id]=project_request.json()

        if is_debug:
            print "DEBUG:: Added project data to cache"
            print "  {0}".format(json.dumps(project_cache[project_id], indent=4, sort_keys=True))
    else:
        project_cache.get(project_id)

    return project_cache[project_id]

def is_data_item_allowed(item, group, session, repo_matcher):
    include_item = False

    project = get_project(session, item["project_id"])
    project_is_org_child = re.match("^{0}\/".format(group["path"]), project["path_with_namespace"]) != None
    item_matches = re.match(repo_matcher, project["path_with_namespace"]) != None

    if project_is_org_child and item_matches:
        if is_debug:
            print "DEBUG:: Including item - {0}".format(item["references"]["full"])
        include_item = True

    return include_item

def get_group_project_data(data_type, session, server, group, start_date, repo_matcher):
    allowed_data = []

    base_url = "{0}/api/v4/groups/{1}/{2}".format(server, group["id"], data_type)

    if is_debug:
        print "DEBUG:: Getting {0} group {1}".format(group["path"], data_type)

    query_state = "&state="
    if data_type == "issues":
        query_state += "closed"
    elif data_type == "merge_requests":
        query_state += "merged"
    else:
        query_state = ""

    query_date = "&updated_after={0}".format(start_date.strftime("%Y-%m-%d"))

    query_string = "?scope=all&per_page=1000{0}{1}".format(query_state, query_date)

    if is_debug:
        print "DEBUG:: Query URL: {0}".format(base_url+query_string)

    query_result = handle_pagination_items(session, base_url+query_string)

    for item in query_result:
        if is_data_item_allowed(item, group, session, repo_matcher):
            allowed_data.append(item)

    if is_debug:
        print "DEBUG:: ALLOWED_DATA - {0}\n{1}".format(data_type, json.dumps(allowed_data, indent=4, sort_keys=True))

    return allowed_data

# Determine if merge request is approved. Must be approved by at least 1 user who is not the merge request author
def is_merge_request_approved(session, merge_request):

    url = "{0}/api/v4/projects/{1}/merge_requests/{2}/approvals".format(gitlab_server, merge_request["project_id"], merge_request["iid"])

    if is_debug:
        print "DEBUG:: Getting project {0} merge_request {1} approval".format(merge_request["project_id"], merge_request["iid"])

    query_result = handle_pagination_items(session, url)

    if 'approved_by' in query_result:
        for approval in query_result["approved_by"]:
            if 'user' in approval:
                if merge_request["author"]["id"] != approval["user"]["id"]:
                    return True
    return False

parser = argparse.ArgumentParser(description='Gather GitLab Statistics.')
parser.add_argument("-s", "--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u", "--username", help="Username to query")
parser.add_argument("-l", "--labels", help="Comma separated list to display. Add '-' at end of each label to negate")
parser.add_argument("-r", "--human-readable", action="store_true", help="Human readable display")
parser.add_argument("-o", "--organization", help="Organization name", default=GITLAB_GROUP_DEFAULT)
parser.add_argument("-m", "--repo-matcher", help="Repo Matcher", default=".+")
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels
human_readable=(args.human_readable==True)
gitlab_group = args.organization
repo_matcher = re.compile(args.repo_matcher)

if start_date is None:
    start_date = generate_start_date()
start_date = pytz.utc.localize(start_date)

gitlab_api_token = os.environ.get(GITLAB_API_TOKEN_NAME)
gitlab_server = os.getenv(GITLAB_SERVER_NAME, GITLAB_SERVER_DEFAULT)

if not gitlab_api_token:
    print "Error: GitLab API Token is Required!"
    sys.exit(1)

session = requests.Session()
session.headers = {
    'Private-Token': gitlab_api_token
}


group = get_group(session, gitlab_server, gitlab_group)

if group is None:
    print "Unable to Locate Group!"
    sys.exit(1)


group_merge_requests = get_group_project_data('merge_requests', session, gitlab_server, group, start_date, repo_matcher)

for mr in group_merge_requests:
    # Skip items that do not have a valid merged_at datetime
    if not mr['merged_at']:
        continue

    if dateutil.parser.parse(mr["merged_at"]) < start_date:
        if is_debug:
            print "DEBUG:: Omit {0} MR {1} {2}/{3}".format(mr["state"], mr["merged_at"], mr['id'], mr['title'])
        continue
    if is_debug:
        print "DEBUG:: Incl {0} MR {1} {2}/{3}".format(mr["state"], mr["merged_at"], mr['id'], mr['title'])

    # Filter out unwanted mr users (if username is specified, then we're only interested in MRs that have that user either the author or merger)
    if username is not None and (mr["author"]["username"] != username or mr["merge_user"]["username"] != username):
        continue

    # Filter out if merged == author if approver != author
    if mr["author"]["username"] == mr["merge_user"]["username"] and not is_merge_request_approved(session, mr):
        print "# Error: Author==merge_user {0} {1} {2}".format(mr['id'], mr["author"]["username"], mr['title'])
        continue

    # Merged MRs
    if mr["author"]["username"] not in merged_mrs:
        author_mrs = []
    else:
        author_mrs = merged_mrs[mr["author"]["username"]]
    author_mrs.append(mr)
    merged_mrs[mr["author"]["username"]] = author_mrs

    # Reviewed MRs (assuming merge_user user is the reviewer, since GL doesn't have an "approve" feature in community edition)
    if mr["merge_user"]["username"] not in reviewed_mrs:
        reviewer_mrs = []
    else:
        reviewer_mrs = reviewed_mrs[mr["merge_user"]["username"]]
    reviewer_mrs.append(mr)
    reviewed_mrs[mr["merge_user"]["username"]] = reviewer_mrs


group_issues = get_group_project_data('issues', session, gitlab_server, group, start_date, repo_matcher)

for iss in group_issues:
    # Skip items that do not have a valid merged_at datetime
    if not iss['closed_at']:
        continue

    if dateutil.parser.parse(iss["closed_at"]) < start_date:
        if is_debug:
            print "DEBUG:: Omit {0} Issue {1} {2}/{3} (shortId={4})".format(iss["state"], iss["closed_at"], iss['id'], iss['title'], iss['iid'])
        continue
    if is_debug:
        print "DEBUG:: Incl {0} Issue {1} {2}/{3} (shortId={4})".format(iss["state"], iss["closed_at"], iss['id'], iss['title'], iss['iid'])

    # Filter out if closed_by == author
    if iss["author"]["username"] == iss["closed_by"]["username"]:
        # DISABLED SUPPORT INFORMATION UPDATES UNTIL FRONT END CAN USE THEM
        #        print "#Closed Issues/GL{0}/{1}/{2} [errorCode={6}, error={7}, org={3}, board={4}, linkId={5}]".format(iss['id'], iss["author"]["username"], 1, iss['web_url'].split('/')[3], iss['web_url'].split('/')[3], iss['iid'], "E1", "Author cannot close issues")
        continue

    # Filter out non-closed issues (shouldn't be any but good to check)

    # Filter out unwanted users
    if username is not None and (iss["author"]["username"] != username or iss["closed_by"]["username"] != username):
        print "# Info: Filtered out : Issue was opened by {0}, and closed by {1}. User {2} was specified as filter".format(iss["author"]["username"], iss["closed_by"]["username"], username)
        continue

    # Closed Issues
    if iss["closed_by"]["username"] not in closed_issues:
        closed_by_iss = []
    else:
        closed_by_iss = closed_issues[iss["closed_by"]["username"]]
    closed_by_iss.append(iss)
    closed_issues[iss["closed_by"]["username"]] = closed_by_iss


print "=== Statistics for GitLab Group '{0}' ====".format(gitlab_group)

print "\n== Merged MR's ==\n"
for key, value in merged_mrs.iteritems():
    if human_readable:
        print "{0} - {1}".format(value[0]["author"]["username"], len(value))
    for mr_value in value:
        if not human_readable:
            # 1 point to author for opening a merged MR
            print "Merge Requests/GL{0}/{1}/{2} [org={3}, board={4}, linkId={5}]".format(mr_value['id'], mr_value['author']['username'], 1, mr_value['web_url'].split('/')[3], '/'.join(mr_value['web_url'].split('/')[4:(len(mr_value['web_url'].split('/'))-3)]), mr_value['web_url'].split('/')[-1])
            if is_debug:
                print "  {0}".format(json.dumps(mr, indent=4, sort_keys=True))
        else:
            print "   {0} - {1}".format(encode_text(mr_value['web_url'].split('/')[-1]), encode_text(mr_value['title']))


print "\n== Reviewed MR's ==\n"
for key, value in reviewed_mrs.iteritems():
    if human_readable:
        print "{0} - {1}".format(value[0]['merge_user']['username'], len(value))
    for mr_value in value:
        if not human_readable:
            # 1 point to reviewer (assuming merge_user is reviewer) for merged MR's
            print "Reviewed Merge Requests/GL{0}/{1}/{2} [org={3}, board={4}, linkId={5}]".format(mr_value['id'], mr_value['merge_user']['username'], 1, mr_value['web_url'].split('/')[3], '/'.join(mr_value['web_url'].split('/')[4:(len(mr_value['web_url'].split('/'))-3)]), mr_value['web_url'].split('/')[-1])
            if is_debug:
                print "  {0}".format(json.dumps(mr_value, indent=4, sort_keys=True))
        else:
            print "   {0} - {1}".format(encode_text(mr_value['web_url'].split('/')[-1]), encode_text(mr_value['title']))


print "\n== Closed Issues ==\n"
for key, value in closed_issues.iteritems():
    if human_readable:
        print "{0} - {1}".format(value[0]['closed_by']['username'], len(value))
    for iss_value in value:
        if not human_readable:
            # 1 point person who closes an issue
            print "Closed Issues/GL{0}/{1}/{2} [org={3}, board={4}, linkId={5}]".format(iss_value['id'], iss_value['closed_by']['username'], 1, iss_value['web_url'].split('/')[3], '/'.join(iss_value['web_url'].split('/')[4:(len(iss_value['web_url'].split('/'))-3)]), iss_value['web_url'].split('/')[-1])
            if is_debug:
                print "  {0}".format(json.dumps(iss_value, indent=4, sort_keys=True))
        else:
            print "   {0} - {1}".format(encode_text(iss_value['web_url'].split('/')[-1]), encode_text(iss_value['title']))

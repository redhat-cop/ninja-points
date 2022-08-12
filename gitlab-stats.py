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
    if is_debug:
        print "DEBUG:: handle_pagination_items(): url = {0}".format(url)
    pagination_request = session.get(url)
    pagination_request.raise_for_status()
    global req_pagination
    req_pagination += 1

    if 'next' in pagination_request.headers["Link"] and pagination_request.links['next']:
        return pagination_request.json() + handle_pagination_items(session, pagination_request.links['next']['url'])
    else:
        return pagination_request.json()


def get_projects_for_group(session, server, group_id):
    return handle_pagination_items(session, "{0}/api/v4/groups/{1}/projects?include_subgroups=true".format(server, group_id))


def get_group_with_projects(session, server, group_name, repo_matcher):
    groups = session.get("{0}/api/v4/groups/{1}".format(server, urllib.quote(group_name, safe='')))
    global req_group
    req_group += 1
    groups.raise_for_status()
    result = groups.json()
    group_projects = get_projects_for_group(session, server, result["id"])

    for project in reversed(group_projects):
        regex_filter_out = re.match(repo_matcher, project["path_with_namespace"]) == None
        if not regex_filter_out and is_debug:
            print "DEBUG:: Including group - {0}".format(project["path_with_namespace"])
        if regex_filter_out:
            group_projects.remove(project)

    result["projects"] = group_projects

    return result


def is_merge_request_in_project_group(merge_request, group, repo_matcher, repo_excluder):
    for project in group["projects"]:
        repo_name_matches = True if re.match(repo_matcher, project["name"]) != None else False
        repo_name_excluded = True if None != repo_excluder and re.match(repo_excluder, project["name"]) != None else False
        if repo_name_matches and repo_name_excluded == False and (project["id"] == merge_request["target_project_id"]):
            return True

    return False


def get_group_merge_requests(session, server, group, repo_matcher, repo_excluder, start_date):
    all_merge_requests = handle_pagination_items(
        session, "{0}/api/v4/groups/{1}/merge_requests?state=merged&scope=all&per_page=1000&created_after={2}".format(server, group["id"], start_date.strftime("%Y-%m-%d")))
    return [item for item in all_merge_requests if is_merge_request_in_project_group(item, group, repo_matcher, repo_excluder)]


def is_issue_in_project_group(issue, group, repo_matcher, repo_excluder):
    for project in group["projects"]:
        if project["id"] == issue["project_id"]:
            return True
    return False


def get_group_issues(session, server, group, repo_matcher, repo_excluder, start_date):
    all_issues = handle_pagination_items(
        session, "{0}/api/v4/groups/{1}/issues?state=closed&scope=all&per_page=1000&created_after={2}".format(server, group["id"], start_date.strftime("%Y-%m-%d")))
    return [item for item in all_issues if is_issue_in_project_group(item, group, repo_matcher, repo_excluder)]


parser = argparse.ArgumentParser(description='Gather GitLab Statistics.')
parser.add_argument("-s", "--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u", "--username", help="Username to query")
parser.add_argument("-l", "--labels", help="Comma separated list to display. Add '-' at end of each label to negate")
parser.add_argument("-r", "--human-readable", action="store_true", help="Human readable display")
parser.add_argument("-o", "--organization", help="Organization name", default=GITLAB_GROUP_DEFAULT)
parser.add_argument("-m", "--repo-matcher", help="Repo Matcher", default=".+")
#parser.add_argument("-x","--repo-excluder", help="Repo Excluder")
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels
human_readable=(args.human_readable==True)
gitlab_group = args.organization
repo_matcher = args.repo_matcher
#repo_excluder = args.repo_excluder
repo_excluder = None  # this has been broken for now due to method "get_group_with_projects" but isn't used anyway

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


group = get_group_with_projects(session, gitlab_server, gitlab_group, repo_matcher)

if group is None:
    print "Unable to Locate Group!"
    sys.exit(1)


group_merge_requests = get_group_merge_requests(session, gitlab_server, group, repo_matcher, repo_excluder, start_date)
for mr in group_merge_requests:
    # Skip items that do not have a valid updated_at datetime
    if dateutil.parser.parse(mr["updated_at"]) < start_date:
        if is_debug:
            print "DEBUG:: Omit {0} MR {1} {2}/{3}".format(mr["state"], mr["updated_at"], mr['id'], mr['title'])
        continue
    if is_debug:
        print "DEBUG:: Incl {0} MR {1} {2}/{3}".format(mr["state"], mr["updated_at"], mr['id'], mr['title'])

    # Check if MR has been merged
    if not mr['merged_at']:
        continue

    # Filter out unwanted mr users (if username is specified, then we're only interested in MRs that have that user either the author or merger)
    if username is not None and (mr["author"]["username"] != username or mr["merged_by"]["username"] != username):
        continue

    # Filter out if merged == author
    if mr["author"]["username"] == mr["merged_by"]["username"]:
        print "# Error: Author==Merged_by {0} {1} {2}".format(mr['id'], mr["author"]["username"], mr['title'])
        continue

    # Merged MRs
    if mr["author"]["username"] not in merged_mrs:
        author_mrs = []
    else:
        author_mrs = merged_mrs[mr["author"]["username"]]
    author_mrs.append(mr)
    merged_mrs[mr["author"]["username"]] = author_mrs

    # Reviewed MRs (assuming merged_by user is the reviewer, since GL doesn't have an "approve" feature in community edition)
    if mr["merged_by"]["username"] not in reviewed_mrs:
        reviewer_mrs = []
    else:
        reviewer_mrs = reviewed_mrs[mr["merged_by"]["username"]]
    reviewer_mrs.append(mr)
    reviewed_mrs[mr["merged_by"]["username"]] = reviewer_mrs


group_issues = get_group_issues(session, gitlab_server, group, repo_matcher, repo_excluder, start_date)
for iss in group_issues:
    if dateutil.parser.parse(iss["updated_at"]) < start_date:
        if is_debug:
            print "DEBUG:: Omit {0} Issue {1} {2}/{3} (shortId={4})".format(iss["state"], iss["updated_at"], iss['id'], iss['title'], iss['iid'])
        continue
    if is_debug:
        print "DEBUG:: Incl {0} Issue {1} {2}/{3} (shortId={4})".format(iss["state"], iss["updated_at"], iss['id'], iss['title'], iss['iid'])

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
        print "{0} - {1}".format(value[0]['merged_by']['username'], len(value))
    for mr_value in value:
        if not human_readable:
            # 1 point to reviewer (assuming merged_by is reviewer) for merged MR's
            print "Reviewed Merge Requests/GL{0}/{1}/{2} [org={3}, board={4}, linkId={5}]".format(mr_value['id'], mr_value['merged_by']['username'], 1, mr_value['web_url'].split('/')[3], '/'.join(mr_value['web_url'].split('/')[4:(len(mr_value['web_url'].split('/'))-3)]), mr_value['web_url'].split('/')[-1])
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

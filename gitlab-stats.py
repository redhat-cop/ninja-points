#!/usr/bin/env python3

# pylint: disable=invalid-name

"""
This script counts GitLab merge request and issue contributions made within an
orgainization that have been updated after the specified start date.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import dateutil.parser
import pytz
import requests
from dateutil.relativedelta import relativedelta

# Fill in GitHub Token
GITLAB_API_TOKEN_NAME = "GITLAB_API_TOKEN"
GITLAB_GROUP_NAME = "GITLAB_GROUP"
GITLAB_SERVER_NAME = "GITLAB_SERVER"
GITLAB_SERVER_DEFAULT = "https://gitlab.consulting.redhat.com"
GITLAB_GROUP_DEFAULT = "redhat-cop"
DEFAULT_START_DATE_MONTH = "03"
DEFAULT_START_DATE_DAY = "01"
MERGED_MR_POINTS = 1
REVIEWED_MR_POINTS = 1
CLOSED_ISSUE_POINTS = 1

merged_mrs = {}
closed_issues = {}
reviewed_mrs = {}
project_cache = {}

IS_DEBUG = False


def generate_start_date():
    """
    Determine default query start date
    """
    today_date = datetime.now()
    target_start_date = datetime.strptime(
        f"{today_date.year}-{DEFAULT_START_DATE_MONTH}-{DEFAULT_START_DATE_DAY}",
        "%Y-%m-%d",
    )

    if today_date.month < int(DEFAULT_START_DATE_MONTH):
        target_start_date = target_start_date - relativedelta(years=1)

    return target_start_date


def valid_date(user_date):
    """
    Convert user supplied date to a datetime object
    """
    try:
        return datetime.strptime(user_date, "%Y-%m-%d")
    except ValueError as error:
        msg = f"Not a valid date: '{user_date}'."
        raise argparse.ArgumentTypeError(msg) from error


def handle_pagination_items(session, url):
    """
    Return paginated results. Called recursively for each page
    """
    if IS_DEBUG:
        print(f"DEBUG:: handle_pagination_items(): url = {url}")
    pagination_request = session.get(url)
    pagination_request.raise_for_status()

    if (
        "next" in pagination_request.headers["Link"]
        and pagination_request.links["next"]
    ):
        return pagination_request.json() + handle_pagination_items(
            session, pagination_request.links["next"]["url"]
        )

    return pagination_request.json()


def get_group(options):
    """
    Return GitLab group data
    """
    # The API call returns a lot of data. Only these keys/data are needed
    required_dict_keys = ["id", "path"]

    session = options["session"]
    server = options["server"]
    group_name = options["group_name"]

    try:
        group_data = session.get(
            f"{server}/api/v4/groups/{urllib.parse.quote(group_name, safe='')}"
        )
    except requests.HTTPError as exc:
        raise ValueError(f"GitLab group not found: {group_name}") from exc

    result = group_data.json()

    if IS_DEBUG:
        print("DEBUG:: Group Data")
        print(f"  {json.dumps(result, indent=4, sort_keys=True)}")

    data = {k: result[k] for k in required_dict_keys}

    return data


def get_project(project_id, options):
    """
    Return project data. If project is not in the cache the project data is
      fetched from GitLab and the cache updated
    """
    session = options["session"]
    server = options["server"]

    if project_id not in project_cache:
        project_request = session.get(f"{server}/api/v4/projects/{project_id}")
        project_request.raise_for_status()
        project_cache[project_id] = project_request.json()

        if IS_DEBUG:
            print("DEBUG:: Added project data to cache")
            print(
                f"  {json.dumps(project_cache[project_id], indent=4, sort_keys=True)}"
            )

    return project_cache.get(project_id)


def is_data_item_allowed(item, options):
    """
    Determine if item should be included in overall results.
    """
    include_item = False

    group = options["group"]
    repo_matcher = options["repo_matcher"]

    project = get_project(item["project_id"], options)

    project_is_org_child = (
        re.match(f"^{group['path']}/", project["path_with_namespace"]) is not None
    )

    item_matches = re.match(repo_matcher, project["path_with_namespace"]) is not None

    if project_is_org_child and item_matches:
        if IS_DEBUG:
            print(f"DEBUG:: Including item - {item['references']['full']}")
        include_item = True

    return include_item


def get_group_project_data(data_type, options):
    """
    Return array of items for the specified data_type (e.g. issues or merge_requests)
    """
    allowed_data = []

    session = options["session"]
    server = options["server"]
    group = options["group"]

    base_url = f"{server}/api/v4/groups/{group['id']}/{data_type}"

    if IS_DEBUG:
        print(f"DEBUG:: Getting {group['path']} group {data_type}")

    query_state = "&state="
    if data_type == "issues":
        query_state += "closed"
    elif data_type == "merge_requests":
        query_state += "merged"
    else:
        query_state = ""

    query_date = f"&updated_after={options['start_date'].strftime('%Y-%m-%d')}"

    query_string = f"?scope=all&per_page=1000{query_state}{query_date}"

    if IS_DEBUG:
        print(f"DEBUG:: Query URL: {base_url+query_string}")

    query_result = handle_pagination_items(session, base_url + query_string)

    for item in query_result:
        if is_data_item_allowed(item, options):
            allowed_data.append(item)

    if IS_DEBUG:
        print(
            f"DEBUG:: ALLOWED_DATA - {data_type}\n"
            f"{json.dumps(allowed_data, indent=4, sort_keys=True)}"
        )

    return allowed_data


def mrs_to_count(merge_requests, options):
    """
    Assign points for authored and reviewed merge requests
    """
    username = options["username"]

    filtered_merged = {}
    filtered_reviewed = {}

    for mr in merge_requests:
        # Skip items that do not have a valid merged_at datetime
        if not mr["merged_at"]:
            continue

        # Filter out merged before start_date
        if dateutil.parser.parse(mr["merged_at"]) < options["start_date"]:
            if IS_DEBUG:
                print(
                    f"DEBUG:: Omit {mr['state']} MR {mr['merged_at']} {mr['id']}/{mr['title']}"
                )
            continue

        if IS_DEBUG:
            print(
                f"DEBUG:: Incl {mr['state']} MR {mr['merged_at']} {mr['id']}/{mr['title']}"
            )

        # Filter out unwanted mr users (if username is specified, then we're only interested in
        # MRs that have that user either the author or merger)
        if username is not None and (
            mr["author"]["username"] != username
            or mr["merged_by"]["username"] != username
        ):
            continue

        # Filter out if merged == author
        if mr["author"]["username"] == mr["merged_by"]["username"]:
            continue

        # The Merged MR is valid to be counted
        if mr["author"]["username"] not in filtered_merged:
            author_mrs = []
        else:
            author_mrs = filtered_merged[mr["author"]["username"]]

        author_mrs.append(mr)
        filtered_merged[mr["author"]["username"]] = author_mrs

        # Reviewed MRs (assuming merged_by user is the reviewer, since GL doesn't have an "approve"
        # feature in community edition)
        if mr["merged_by"]["username"] not in filtered_reviewed:
            reviewer_mrs = []
        else:
            reviewer_mrs = filtered_reviewed[mr["merged_by"]["username"]]

        reviewer_mrs.append(mr)
        filtered_reviewed[mr["merged_by"]["username"]] = reviewer_mrs

    return filtered_merged, filtered_reviewed


def issues_to_count(issues, options):
    """
    Assign points for closed issues
    """
    username = options["username"]

    filtered_issues = {}

    for issue in issues:
        # Skip items that do not have a valid merged_at datetime
        if not issue["closed_at"]:
            continue

        # Filter out closed before start_date
        if dateutil.parser.parse(issue["closed_at"]) < options["start_date"]:
            if IS_DEBUG:
                print(
                    f"DEBUG:: Omit {issue['state']} Issue {issue['closed_at']} "
                    f"{issue['id']}/{issue['title']} (shortId={issue['iid']})"
                )
            continue
        if IS_DEBUG:
            print(
                f"DEBUG:: Incl {issue['state']} Issue {issue['closed_at']} "
                f"{issue['id']}/{issue['title']} (shortId={issue['iid']})"
            )

        # Filter out if closed_by == author
        if issue["author"]["username"] == issue["closed_by"]["username"]:
            continue

        # Filter out unwanted users
        if username is not None and (
            issue["author"]["username"] != username
            or issue["closed_by"]["username"] != username
        ):
            print(
                f"# Info: Filtered out : Issue was opened by {issue['author']['username']}, "
                f"and closed by {issue['closed_by']['username']}. "
                f"User {username} was specified as filter"
            )
            continue

        # Closed Issues
        if issue["closed_by"]["username"] not in filtered_issues:
            closed_by_iss = []
        else:
            closed_by_iss = filtered_issues[issue["closed_by"]["username"]]

        closed_by_iss.append(issue)
        filtered_issues[issue["closed_by"]["username"]] = closed_by_iss

    return filtered_issues


parser = argparse.ArgumentParser(description="Gather GitLab Statistics.")
parser.add_argument(
    "-s", "--start-date", help="The start date to query from", type=valid_date
)
parser.add_argument("-u", "--username", help="Username to query")
parser.add_argument(
    "-r", "--human-readable", action="store_true", help="Human readable display"
)
parser.add_argument(
    "-o", "--organization", help="Organization name", default=GITLAB_GROUP_DEFAULT
)
parser.add_argument("-m", "--repo-matcher", help="Repo Matcher", default=".+")
args = parser.parse_args()

human_readable = bool(args.human_readable)

# Store all the option necessary in a dictionary ease variable passing
opts = {
    "start_date": args.start_date,
    "username": args.username,
    "group_name": args.organization,
    "repo_matcher": re.compile(args.repo_matcher),
}

if opts["start_date"] is None:
    opts["start_date"] = generate_start_date()

opts["start_date"] = pytz.utc.localize(opts["start_date"])

opts["server"] = os.getenv(GITLAB_SERVER_NAME, GITLAB_SERVER_DEFAULT)

gitlab_api_token = os.environ.get(GITLAB_API_TOKEN_NAME)

if not gitlab_api_token:
    print("Error: GitLab API Token is Required!")
    sys.exit(1)

opts["session"] = requests.Session()
opts["session"].headers = {"Private-Token": gitlab_api_token}


opts["group"] = get_group(opts)

if opts["group"] is None:
    print("Unable to Locate Group!")
    sys.exit(1)


group_merge_requests = get_group_project_data("merge_requests", opts)

merged_mrs, reviewed_mrs = mrs_to_count(group_merge_requests, opts)


group_issues = get_group_project_data("issues", opts)

closed_issues = issues_to_count(group_issues, opts)


print(f"=== Statistics for GitLab Group '{opts['group_name']}' ====")

print("\n== Merged MR's ==\n")
for key, value in merged_mrs.items():
    if human_readable:
        print(f"{value[0]['author']['username']} - {len(value)}")
    for mr_value in value:
        if not human_readable:
            board = "/".join(
                mr_value["web_url"].split("/")[
                    4 : (len(mr_value["web_url"].split("/")) - 3)
                ]
            )
            print(
                f"Merge Requests/"
                f"GL{mr_value['id']}/"
                f"{mr_value['author']['username']}/"
                f"{MERGED_MR_POINTS} "
                f"[org={mr_value['web_url'].split('/')[3]}, "
                f"board={board}, "
                f"linkId={mr_value['web_url'].split('/')[-1]}]"
            )
            if IS_DEBUG:
                print(f"  {json.dumps(mr_value, indent=4, sort_keys=True)}")
        else:
            print(f"   {mr_value['web_url'].split('/')[-1]} - {mr_value['title']}")


print("\n== Reviewed MR's ==\n")
for key, value in reviewed_mrs.items():
    if human_readable:
        print(f"{value[0]['merged_by']['username']} - {len(value)}")
    for mr_value in value:
        if not human_readable:
            board = "/".join(
                mr_value["web_url"].split("/")[
                    4 : (len(mr_value["web_url"].split("/")) - 3)
                ]
            )
            print(
                f"Reviewed Merge Requests/"
                f"GL{mr_value['id']}/"
                f"{mr_value['merged_by']['username']}/"
                f"{REVIEWED_MR_POINTS} "
                f"[org={mr_value['web_url'].split('/')[3]}, "
                f"board={board}, "
                f"linkId={mr_value['web_url'].split('/')[-1]}]"
            )
            if IS_DEBUG:
                print(f"  {json.dumps(mr_value, indent=4, sort_keys=True)}")
        else:
            print(f"   {mr_value['web_url'].split('/')[-1]} - {mr_value['title']}")


print("\n== Closed Issues ==\n")
for key, value in closed_issues.items():
    if human_readable:
        print(f"{value[0]['closed_by']['username']} - {len(value)}")
    for iss_value in value:
        if not human_readable:
            board = "/".join(
                iss_value["web_url"].split("/")[
                    4 : (len(iss_value["web_url"].split("/")) - 3)
                ]
            )
            print(
                f"Closed Issues/"
                f"GL{iss_value['id']}/"
                f"{iss_value['closed_by']['username']}/"
                f"{CLOSED_ISSUE_POINTS} "
                f"[org={iss_value['web_url'].split('/')[3]}, "
                f"board={board}, "
                f"linkId={iss_value['web_url'].split('/')[-1]}]"
            )
            if IS_DEBUG:
                print(f"  {json.dumps(iss_value, indent=4, sort_keys=True)}")
        else:
            print(f"   {iss_value['web_url'].split('/')[-1]} - {iss_value['title']}")

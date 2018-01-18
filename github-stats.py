#!/usr/bin/env python

import os, json, requests, sys, argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Fill in GitHub Token
GITHUB_API_TOKEN_NAME = 'GITHUB_API_TOKEN'
GITHUB_ORG = 'redhat-cop'
USER_AGENT= 'redhat-cop-stats'
DEFAULT_START_DATE_MONTH = '03'
DEFAULT_START_DATE_DAY = '01'
DEFAULT_LABEL_LIST = ['enhancement']

def handle_pagination_items(session, url):
    
    pagination_request = session.get(url)
    pagination_request.raise_for_status()

    if 'next' in pagination_request.links and pagination_request.links['next']:
        return pagination_request.json()['items'] + handle_pagination_items(session, pagination_request.links['next']['url'])
    else:
        return pagination_request.json()['items']

def generate_start_date():
    today_date = datetime.now()
    target_start_date = datetime.strptime("{0}-{1}-{02}".format(today_date.year, DEFAULT_START_DATE_MONTH, DEFAULT_START_DATE_DAY), "%Y-%m-%d")

    if target_start_date.month < DEFAULT_START_DATE_MONTH:
        target_start_date = target_start_date - relativedelta(years=1)

    return target_start_date

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def string_to_list(s):
    return [x.strip() for x in s.split(',')]

def encode_text(text):
    if text:
        return text.encode("utf-8")

    return text

def get_org_repos(session):
    
    return handle_pagination_items(session, "https://api.github.com/orgs/{0}/repos".format(GITHUB_ORG))

def get_org_members(session):

    return handle_pagination_items(session, "https://api.github.com/orgs/{0}/members".format(GITHUB_ORG))

def get_pr(session, url):
    pr_request = session.get(url)
    pr_request.raise_for_status()

    return pr_request.json()

def get_reviews(session, url):
    pr_request = session.get("{0}/reviews".format(url))
    pr_request.raise_for_status()

    return pr_request.json()

def get_org_search_issues(session, start_date, labels):
    
    query = "https://api.github.com/search/issues?q=user:redhat-cop+updated:>={}+archived:false+state:closed{}".format(start_date.date().isoformat(), labels)
    return handle_pagination_items(session, query)

def process_labels(labels):
    output_labels = "";

    for label in labels:

        if label[-1] == "-":
            output_labels += "-"
            label = label[0:-1]

        output_labels += " label:{0}".format(label)

    return output_labels


parser = argparse.ArgumentParser(description='Gather GitHub Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u","--username", help="Username to query")
parser.add_argument("-l","--labels", help="Comma separated list to filter on (default: enhancement). Add '-' at end of each label to negate", type=string_to_list)
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels if args.labels else DEFAULT_LABEL_LIST


if start_date is None:
    start_date = generate_start_date()


github_api_token = os.environ.get(GITHUB_API_TOKEN_NAME)

if not github_api_token:
    print "Error: GitHub API Key is Required!"
    sys.exit(1)

session = requests.Session()
session.headers = {
    'Accept': 'application/vnd.github.v3+json',
    'Authorization': 'Token {0}'.format(github_api_token),
    'User-Agent': USER_AGENT
}

# Produce Label String
labels = process_labels(input_labels)

# Initialize Collection Statistics
general_prs = {}
closed_issues = {}
reviewed_prs = {}

org_search_issues = get_org_search_issues(session, start_date, labels)

for issue in org_search_issues:

    issue_author_id = issue['user']['id']
    issue_author_login = issue['user']['login']

    # Check if Issue is a Pull Request
    if 'pull_request' in issue:
        is_pull_request = True

        pr_url = issue['pull_request']['url']

        pr = get_pr(session, pr_url)

        # Check if PR Has Been Merged
        if not pr['merged_at']:
            continue

        # Check for Reviews
        pr_reviews = get_reviews(session, pr_url)

        for review in pr_reviews:
            review_author_login = review['user']['login']

            #Filter out unwanted review users
            if username is not None and review_author_login != username:
                continue

            if review_author_login not in reviewed_prs:
                review_author_prs = {}
            else:
                review_author_prs = reviewed_prs[review_author_login]
            
            if issue['id'] not in review_author_prs:
                review_author_prs[issue['id']] = issue
            
            reviewed_prs[review_author_login] = review_author_prs

        #Filter out unwanted pr users
        if username is not None and issue_author_login != username:
            continue

        # If We Have Gotten This Far, it is not an enhancement
        if issue_author_id not in general_prs:
            all_author_prs = []
        else:
            all_author_prs =general_prs[issue_author_id]

        all_author_prs.append(issue)
        general_prs[issue_author_id] = all_author_prs
    else:

        if issue['state'] == 'closed' and issue['assignee'] is not None:

            closed_issue_author_id = issue['assignee']['id']
            closed_issue_author_login = issue['assignee']['login']

            #Filter out unwanted assignees
            if username is not None and closed_issue_author_login != username:
                continue

            # Ignore Self Assigned Issues
            if issue_author_id == closed_issue_author_id:
                continue

            if closed_issue_author_id not in closed_issues:
                closed_issue_author = []
            else:
                closed_issue_author = closed_issues[closed_issue_author_id]
            
            closed_issue_author.append(issue)
            closed_issues[closed_issue_author_id] = closed_issue_author 

print "=== Statistics for GitHub Organization '{0}' ====".format(GITHUB_ORG)      

print "\n== General PR's ==\n"
for key, value in general_prs.iteritems():
    print "{0} - {1}".format(value[0]['user']['login'], len(value))
    for issue_value in value:
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Reviewed PR's ==\n"
for key, value in reviewed_prs.iteritems():
    print "{0} - {1}".format(key, len(value))
    for issue_key, issue_value in value.iteritems():
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Closed Issues ==\n"

for key, value in closed_issues.iteritems():
    print "{0} - {1}".format(value[0]['assignee']['login'], len(value))
    for issue_value in value:
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))
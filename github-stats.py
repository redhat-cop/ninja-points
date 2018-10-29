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
UNLABELED = 'unlabeled'

def handle_pagination_items(session, url):
#    print "pagination called: {}".format(url)
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

def get_org_search_issues(session, start_date):

    query = "https://api.github.com/search/issues?q=user:{}+updated:>={}+archived:false+state:closed&per_page=50".format(GITHUB_ORG, start_date.date().isoformat())
    return handle_pagination_items(session, query)

def process_labels(labels):
    label_dict = {}

    if labels:
        for x in labels.split(','):
            label_dict[x.strip()] = None

    return label_dict

def process_general_issues(issue, all_prs, label_prs):
    
    author_login = issue['user']['login']

    if author_login not in label_prs:
            all_author_prs = []
    else:
        all_author_prs = label_prs[author_login]

    all_author_prs.append(issue)
    label_prs[author_login] = all_author_prs

    return label_prs

def show_label(label_items_key, input_labels):
    
    # Check if length of input labels is 0. If so, show all labels
    if len(input_labels) == 0:
        return True

    # Loop through input labels
    for key in input_labels:

        # Check if label should be omitted
        if key[-1] == "-":
            if key[0:-1] == label_items_key:
                return False
            else:
                return True
        
        # Check if label is found
        if key == label_items_key:
            return True

    return False

parser = argparse.ArgumentParser(description='Gather GitHub Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-r","--human-readable", action="store_true", help="Human readable format")
parser.add_argument("-u","--username", help="Username to query")
parser.add_argument("-l","--labels", help="Comma separated list to display. Add '-' at end of each label to negate")
args = parser.parse_args()

start_date = args.start_date
username = args.username
input_labels = args.labels

human_readable=(args.human_readable==True)

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
input_labels = process_labels(args.labels)

# Initialize Collection Statistics
general_prs = {}
closed_issues = {}
reviewed_prs = {}

org_search_issues = get_org_search_issues(session, start_date)

for issue in org_search_issues:

#    print "{}:".format(issue['id'])
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

        # Check if Label exists
        if issue['labels']:
            for label in issue['labels']:
                
                label_name = label['name']

                # Determine is Label Exists
                if label_name not in general_prs:
                    label_issues = {}
                else:
                    label_issues = general_prs[label_name]
                
                general_prs[label_name] = process_general_issues(issue,general_prs, label_issues)

        else:
            if UNLABELED not in general_prs:
                label_issues = {}
            else:
                label_issues = general_prs[UNLABELED]

            general_prs[UNLABELED] = process_general_issues(issue,general_prs, label_issues)

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
    # Determine whether to print out Label
    if(show_label(key, input_labels)):
        if (human_readable):
            print "{}:".format(key)
        for label_key, label_value in value.iteritems():
            if (human_readable):
                print "  {0} - {1}".format(label_key, len(label_value))
            for issue_value in label_value:
                if (not human_readable):
                    print "Pull Requests/GH{0}/{1}/{2}".format(issue_value['id'], label_key, 1)
                else:
                    print "    {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Reviewed PR's ==\n"
for key, value in reviewed_prs.iteritems():
    if (not human_readable):
        print "Reviewed Pull Requests/GH{0}/{1}/{2}".format(issue_value['id'], key, 1)
    else:
        print "{0} - {1}".format(key, len(value))
        for issue_key, issue_value in value.iteritems():
            print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Closed Issues ==\n"
for key, value in closed_issues.iteritems():
    if (not human_readable):
        print "Closed Issues/GH{0}/{1}/{2}".format(key, value[0]['assignee']['login'], len(value))
    else:
        print "{0} - {1}".format(value[0]['assignee']['login'], len(value))
        for issue_value in value:
            print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))


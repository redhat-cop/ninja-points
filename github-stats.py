#!/usr/bin/env python

import json, requests, sys, argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Fill in GitHub Token
GITHUB_API_TOKEN = ''

GITHUB_ORG = 'redhat-cop'
USER_AGENT= 'redhat-cop-stats'
ENHANCEMENT_LABEL = 'enhancement'
DEFAULT_START_DATE_MONTH = '03'
DEFAULT_START_DATE_DAY = '01'

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
    
    query = "https://api.github.com/search/issues?q=user:redhat-cop+updated:>={}+archived:false+state:closed".format(start_date.date().isoformat())
    return handle_pagination_items(session, query)

def has_label(issue, label_name):
    if not 'labels' in issue:
        return False;
    else:
        for label in issue['labels']:
            if label['name'] == label_name:
                return True
    
    return False

session = requests.Session()
session.headers = {
    'Accept': 'application/vnd.github.v3+json',
    'Authorization': 'Token {0}'.format(GITHUB_API_TOKEN),
    'User-Agent': USER_AGENT

}



parser = argparse.ArgumentParser(description='Gather GitHub Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
args = parser.parse_args()

start_date = args.start_date

if start_date is None:
    start_date = generate_start_date()

# Initialize Collection Statistics
enhancement_prs = {}
bugfix_prs = {}
closed_issues = {}
reviewed_prs = {}

if not GITHUB_API_TOKEN:
    print "Error: GitHub API Key is Required!"
    sys.exit(1)    

org_search_issues = get_org_search_issues(session, start_date)

for issue in org_search_issues:

    issue_author_id = issue['user']['id']

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

            if review_author_login not in reviewed_prs:
                review_author_prs = {}
            else:
                review_author_prs = reviewed_prs[review_author_login]
            
            if issue['id'] not in review_author_prs:
                review_author_prs[issue['id']] = issue
            
            reviewed_prs[review_author_login] = review_author_prs

        # Scroll Through Labels
        # If Enhancement, Add to Bucket
        if has_label(issue, ENHANCEMENT_LABEL):
            
            if issue_author_id not in enhancement_prs:
                enhancement_author_prs = []
            else:
                enhancement_author_prs = enhancement_prs[issue_author_id]

            enhancement_author_prs.append(issue)
            enhancement_prs[issue_author_id] = enhancement_author_prs
            continue

        # If We Have Gotten This Far, it is not an enhancement
        if issue_author_id not in bugfix_prs:
            bugfix_author_prs = []
        else:
            bugfix_author_prs = bugfix_prs[issue_author_id]

        bugfix_author_prs.append(issue)
        bugfix_prs[issue_author_id] = bugfix_author_prs
    else:
        if issue['state'] == 'closed' and issue['assignee'] is not None:

            closed_issue_author_id = issue['assignee']['id']

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

print "\n== Enhancement PR's ==\n"
for key, value in enhancement_prs.iteritems():
    print "{0} - {1}".format(value[0]['user']['login'], len(value))
    for issue_value in value:
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Bugfix PR's ==\n"
for key, value in bugfix_prs.iteritems():
    print "{0} - {1}".format(value[0]['user']['login'], len(value))
    for issue_value in value:
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Reviewed PR's ==\n"
for key, value in reviewed_prs.iteritems():
    print "{0} - {1}".format(value.itervalues().next()['user']['login'], len(value))
    for issue_key, issue_value in value.iteritems():
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))

print "\n== Closed Issues ==\n"

for key, value in closed_issues.iteritems():
    print "{0} - {1}".format(value[0]['assignee']['login'], len(value))
    for issue_value in value:
        print "   {0} - {1}".format(encode_text(issue_value['repository_url'].split('/')[-1]), encode_text(issue_value['title']))
#!/usr/bin/env python

import os, json, requests, sys, argparse, collections, re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

TRELLO_ORG_NAME = 'redhatcop'
TRELLO_API_KEY_NAME = 'TRELLO_API_KEY'
TRELLO_API_TOKEN_NAME = 'TRELLO_API_TOKEN'
DEFAULT_START_DATE_MONTH = '03'
DEFAULT_START_DATE_DAY = '01'
CARD_TITLE_POINTS_REGEX_PATTERN = re.compile(r"\(([0-9]+)\)")
DEFAULT_POINTS_GROUPING = "Cards Closed"

# Search for cards that are done and have been modified in the past ? days
TRELLO_SEARCH_QUERY = 'list:Done edited:{0} {1}'

debug=False
memberCache={}
memberCacheBoards=[]
requestCount_org=0
requestCount_orgMembers=0
requestCount_member=0  #we need to limit these requests
requestCount_boardMembers=0
requestCount_cards=0

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def generate_start_date():
    today_date = datetime.now()
    target_start_date = datetime.strptime("{0}-{1}-{02}".format(today_date.year, DEFAULT_START_DATE_MONTH, DEFAULT_START_DATE_DAY), "%Y-%m-%d")

    if today_date.month < int(DEFAULT_START_DATE_MONTH):
        target_start_date = target_start_date - relativedelta(years=1)

    return target_start_date

def get_org_id(session):
    #print "org = {0}".format(TRELLO_ORG_NAME)
    org_request = session.get("https://api.trello.com/1/organizations/{0}".format(TRELLO_ORG_NAME))
    global requestCount_org
    requestCount_org+=1
    org_request.raise_for_status()
    return org_request.json()

def search_cards(session, org_id, days, author):
    author = "@{0}".format(author) if author is not None else ""
    query = TRELLO_SEARCH_QUERY.format(days, author)
    card_request = session.get("https://api.trello.com/1/search", params={'query': query, 'idOrganizations': org_id, 'card_fields': 'name,idBoard,idMembers,idLabels,shortLink', 'board_fields': 'name,idOrganization', 'card_board': 'true', 'cards_limit': 1000})
    global requestCount_cards
    requestCount_cards+=1
    card_request.raise_for_status()
    return card_request.json()

def get_member(session, member_id):
		if member_id not in memberCache:
		    member_request = session.get("https://api.trello.com/1/members/{0}".format(member_id))
		    global requestCount_member
		    requestCount_member+=1
		    member_request.raise_for_status()
		    memberCache[member_id]=member_request.json()
		    if debug: print "get_member:: memberCache.add({0})".format(memberCache[member_id]['username'])
		return memberCache.get(member_id)

def plural_items(text, obj):
    if obj is not None and (isinstance(obj, collections.Iterable) and len(obj) == 1) or obj == 1:
        return text[:-1]
    else:
        return text

def calculate_points(text):
    matches = re.findall(CARD_TITLE_POINTS_REGEX_PATTERN, text)
    
    if(len(matches) == 0):
        return 1
    else:
        return min(5,int(matches[-1])); # cap at a maximum of 5 points for any card

def encode_text(text):
    if text:
        return text.encode("utf-8")

    return text

def preload_member_cache_from_org(session, org_id):
    # Add the organization members
    members = session.get("https://api.trello.com/1/organizations/{0}/members".format(org_id))
    global requestCount_orgMembers
    requestCount_orgMembers+=1
    members.raise_for_status()
    for member in members.json():
        add_member_to_cache(member)
    
def preload_member_cache_from_board(session, board_id):
    # Add the boards members
    if board_id not in memberCacheBoards:
        board_members=session.get("https://api.trello.com/1/boards/{0}/members".format(board_id))
        global requestCount_boardMembers
        requestCount_boardMembers+=1
        for member in board_members.json():
            add_member_to_cache(member)
        memberCacheBoards.append(board_id)

def add_member_to_cache(member):
    if member['id'] not in memberCache:
        if debug: print "add_member_to_cache:: memberCache.add({0})".format(member['username'])
        memberCache[member['id']] = {"id":member['id'], "username":member['username'], "fullName":member['fullName']}



trello_api_key = os.environ.get(TRELLO_API_KEY_NAME)
trello_api_token = os.environ.get(TRELLO_API_TOKEN_NAME)


if not trello_api_key or not trello_api_token:
    print "Error: Trello API Key and API Token are Required!"
    sys.exit(1)

parser = argparse.ArgumentParser(description='Gather Trello Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-u","--username", help="Username to query")
parser.add_argument("-r","--human-readable", action="store_true", help="Human readable format")
parser.add_argument("-o","--organization", help="Trello organization name")
parser.add_argument("-p","--points-grouping", help="Points Bucket")
args = parser.parse_args()

start_date = args.start_date
username = args.username

if start_date is None:
    start_date = generate_start_date()

human_readable=(args.human_readable==True)

if args.organization is not None:
    TRELLO_ORG_NAME=args.organization;

points_grouping = args.points_grouping
if points_grouping is None:
    points_grouping = DEFAULT_POINTS_GROUPING

days = (datetime.now() - start_date).days

session = requests.Session()
session.params = {
    'key': trello_api_key,
    'token': trello_api_token,
}

org_response = get_org_id(session)
org_id = org_response['id']

resp_cards = search_cards(session, org_id, days, username)

cards = {}
members_items = {}

preload_member_cache_from_org(session, org_id)

for card in resp_cards['cards']:
    
    if not card['board']['idOrganization'] or card['board']['idOrganization'] != org_id:
        continue 
    
    card_id = card['id']
    cards[card_id] = card
    
    # pre-load the members from the board this card belongs to (because that's more efficient than loading members one-by-one later on)
    preload_member_cache_from_board(session, card['idBoard'])
    
    
    if 'idMembers' in card:
        for member in card['idMembers']:
           
            member_id = member

            if member_id not in members_items:
                member_items= {}
                member_items['points'] = 0
                member_items['cards'] = []
                member_cards = []
            else:
                member_items = members_items[member_id]
            
            member_items['cards'].append(card_id)
            points = calculate_points(card['name'])
            member_items['points'] += points

            members_items[member_id] = member_items
            if (not human_readable):
                print "{0}/TR{1}/{2}/{3} [linkId={4},board={5}]".format(points_grouping, card_id, get_member(session, member_id)['username'], points, card['shortLink'], card['board']['name'])


if (human_readable):
    print "=== Statistics for Trello Team '{0}' ====\n".format(encode_text(org_response['displayName']) if 'displayName' in org_response else encode_text(org_response['name']))
    for key, value in members_items.iteritems():
        member = get_member(session, key)
        value_points = value['points']
        value_cards = value['cards']

        if username is not None and member['username'] != username:
            continue

        print "{0} has {1} {2} - {3} {4}".format(encode_text(member['username']), len(value_cards), plural_items("cards", value_cards), value_points, plural_items("points", value_points))
        for card in value['cards']:
            print "   - Board: {0} | Card: {1}".format(encode_text(cards[card]['board']['name']), encode_text(cards[card]['name']))

if debug: print "REQUESTS: org={0}, orgMembers={1}, member={2}, boardMembers={3}, cards={4}".format(requestCount_org, requestCount_orgMembers, requestCount_member, requestCount_boardMembers, requestCount_cards)

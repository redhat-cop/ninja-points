#!/usr/bin/env python

import json, requests, sys

TRELLO_ORG_NAME = 'redhatcop'
TRELLO_API_KEY = ''
TRELLO_API_TOKEN = ''

# Search for cards that are done and have been modified in the past 30 days
TRELLO_SEARCH_QUERY = 'list:Done edited:30'


def get_org_id(session):
    
    org_request = session.get("https://api.trello.com/1/organizations/{0}".format(TRELLO_ORG_NAME))
    org_request.raise_for_status()

    return org_request.json()

def search_cards(session, org_id):
    card_request = session.get("https://api.trello.com/1/search", params={'query': TRELLO_SEARCH_QUERY, 'idOrganizations': org_id, 'card_fields': 'name,idMembers', 'board_fields': 'name,idOrganization', 'card_board': 'true'})
    card_request.raise_for_status()

    return card_request.json()

def get_member(session, member_id):
    member_request = session.get("https://api.trello.com/1/members/{0}".format(member_id))
    member_request.raise_for_status()

    return member_request.json()

if not TRELLO_API_KEY or not TRELLO_API_TOKEN:
    print "Error: Trello API Key and Token are Required!"
    sys.exit(1)



session = requests.Session()
session.params = {
    'key': TRELLO_API_KEY,
    'token': TRELLO_API_TOKEN,
}

org_response = get_org_id(session)
org_id = org_response['id']

resp_cards = search_cards(session, org_id)

cards = {}
members_cards = {}

for card in resp_cards['cards']:
    
    if not card['board']['idOrganization'] or card['board']['idOrganization'] != org_id:
        continue 

    card_id = card['id']
    cards[card_id] = card

    if 'idMembers' in card:
        for member in card['idMembers']:
           
            member_id = member

            if member_id not in members_cards:
                member_cards = []
            else:
                member_cards = members_cards[member_id]
            
            member_cards.append(card_id)

            members_cards[member_id] = member_cards

print "=== Statistics for Trello Team '{0}' ====\n".format(org_response['displayName'] if 'displayName' in org_response else org_response['name'])
for key, value in members_cards.iteritems():
        member = get_member(session, key)
        print "{0} has {1} cards".format(member['username'], len(value))
        for card in value:
            print "   - Board: {0} | Card: {1}".format(cards[card]['board']['name'], cards[card]['name'])

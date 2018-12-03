#!/usr/bin/env python

from oauth2client.service_account import ServiceAccountCredentials
from os import path
import os, requests, sys, argparse

SERVICE_ACCOUNT_KEY_FILE_NAME='SERVICE_ACCOUNT_KEY_FILE'
HANGOUTS_CHATS_API='https://chat.googleapis.com/v1'
GOOGLE_CHAT_SCOPE='https://www.googleapis.com/auth/chat.bot'
SPACES_KEY='spaces'
MEMBERS_KEY='memberships'


def login(session, service_account_key_file):
    scopes = [GOOGLE_CHAT_SCOPE]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(service_account_key_file, scopes)
    access_token = credentials.get_access_token()

    auth_headers = {
        'Authorization': 'Bearer ' + access_token.access_token
    }

    session.headers.update(auth_headers)

def get_spaces(session):
    return handle_pagination_items(session, "{0}/spaces".format(HANGOUTS_CHATS_API), SPACES_KEY)

def get_members_in_space(session, space):
    members = handle_pagination_items(session, "{0}/{1}/members".format(HANGOUTS_CHATS_API, space["name"]), MEMBERS_KEY)

    human_members = []

    for member in members:
        if member["state"] == "JOINED" and member["member"]["type"] == "HUMAN":
            human_members.append(member)
    
    return human_members

def get_spaces_with_members(session):
    spaces_with_members = {}

    spaces = get_spaces(session)


    for space in spaces:
        if space["type"] == "ROOM":
            val = {}

            val["space"] = space

            # Get members
            members = get_members_in_space(session, space)
            val["members"] = members

            spaces_with_members[space["name"]] = val
    
    return spaces_with_members

def handle_pagination_items(session, url, key, next_page_token=None):
    params = {}

    if next_page_token is not None and next_page_token != "":
        params["pageToken"] = next_page_token
 
    response = session.get(url, params=params)

    response_json = response.json()

    if "nextPageToken" in response_json and response_json["nextPageToken"] != "":
        return response_json[key] + handle_pagination_items(session, url, key, response_json["nextPageToken"])
    else:
        return response_json[key]

def encode_text(text):
    if text:
        return text.encode("utf-8")

    return text

parser = argparse.ArgumentParser(description='Gather Google Hangouts Statistics.')
parser.add_argument("-m","--show-members", help="Show members in each space")
args = parser.parse_args()

show_members = args.show_members

service_account_key_file = os.environ.get(SERVICE_ACCOUNT_KEY_FILE_NAME)

if not service_account_key_file:
    print "Error: Service Account Key File Location is Required!"
    sys.exit(1)

if not path.exists(service_account_key_file):
    print "Error: Service Account Key File Does Not Exist!"
    sys.exit(1)    

session = requests.Session()

error = login(session, service_account_key_file)

if error is not None:
    print error
    sys.exit(1)

spaces_with_members = get_spaces_with_members(session)

print "=== Statistics for Google Hangouts Chat\n"

for key, value in spaces_with_members.iteritems():
    print "- {0} - {1} Members".format(encode_text(value["space"]["displayName"]), len(value["members"]))

    if show_members is not None:
        for member in value["members"]:
            print "   - {0}".format(encode_text(member["member"]["displayName"]))
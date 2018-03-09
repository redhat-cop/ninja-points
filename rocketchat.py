#!/usr/bin/env python

import os, json, requests, sys, argparse, collections, re

ROCKETCHAT_SERVER_DEFAULT = 'chat.consulting.redhat.com'
ROCKETCHAT_USERNAME = 'ROCKETCHAT_USERNAME'
ROCKETCHAT_PASSWORD = 'ROCKETCHAT_PASSWORD'
ROCKETCHAT_AUTH_TOKEN = 'ROCKETCHAT_AUTH_TOKEN'
ROCKETCHAT_USER_ID = 'ROCKETCHAT_USER_ID'

def login(session, server, username, password, authToken, userId):
    if not authToken or not userId:
        if not username or not password:
            return "Error: No Rocketchat Authentication Details Provided"

        data = { "username": username,
             "password": password }

        try:
            login_request = session.post("https://{0}/api/v1/login".format(server), data=data)
        except:
            return "Error occurred during login process"

        response_json = login_request.json()

        if not 'status' in response_json.keys() or response_json['status'] != "success":
            return "Invalid Login Response"

        authToken = login_request.json()['data']['authToken']
        userId = login_request.json()['data']['userId']

    auth_headers = {
        'X-Auth-Token': authToken,
        'X-User-Id': userId,
        'Content-Type': 'application/json'
    }

    session.headers.update(auth_headers)

    return None

def get_channels(session, server, description):
    channels = []
    count = 50
    passes = 0
    fetched = 0
    total = 0

    while fetched <= total:
        params = {'count': count, 'offset': fetched}

        channel_list = session.get("https://{0}/api/v1/channels.list".format(server), params=params)

        channel_list_json = channel_list.json()

        total = channel_list_json['total']

        channels.extend(channel_list_json['channels'])

        passes += 1
        fetched = count * passes

    return channels

def filter_channels(channels, channel_filter):

    for channel in reversed(channels):
        if 'description' in channel:
            if channel_filter not in channel['description']:
                channels.remove(channel)
        else:
            channels.remove(channel)

def get_channel_members_stats(session, channel):

        params = {'roomId': channel['_id']}

        channel_info = session.get("https://{0}/api/v1/channels.members?".format(server), params=params)

        return {'id': channel['_id'], 'name': channel['name'], 'total': channel_info.json()['total']}

rocketchat_username = os.environ.get(ROCKETCHAT_USERNAME)
rocketchat_password = os.environ.get(ROCKETCHAT_PASSWORD)
rocketchat_auth_token = os.environ.get(ROCKETCHAT_AUTH_TOKEN)
rocketchat_user_id = os.environ.get(ROCKETCHAT_USER_ID)

parser = argparse.ArgumentParser(description='Gather Rocketchat Statistics.')
parser.add_argument("-d","--description", help="Text in Channel Description to Filter On", required=True)
parser.add_argument("-s","--server", help="Rocketchat Server")
args = parser.parse_args()

description = args.description
server = args.server

if not server:
    server = ROCKETCHAT_SERVER_DEFAULT

session = requests.Session()

error = login(session, server, rocketchat_username, rocketchat_password, rocketchat_auth_token, rocketchat_user_id)

if error is not None:
    print error
    sys.exit(1)


channels = get_channels(session, server, description)

filter_channels(channels, description)

print "=== Rocketchat Statistics ===\n"
if len(channels) > 0:
    for channel in channels:
        channel_members_stats = get_channel_members_stats(session, channel)
        print "- {0} - {1} Users".format(channel['name'], channel_members_stats['total'])

else:
    print "No Rocketchat Channels Match the description '{0}'".format(description)
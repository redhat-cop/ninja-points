#!/usr/bin/env python

import os, json, requests, sys, argparse, collections, re, operator
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

ROCKETCHAT_SERVER_DEFAULT = 'chat.consulting.redhat.com'
ROCKETCHAT_USERNAME = 'ROCKETCHAT_USERNAME'
ROCKETCHAT_PASSWORD = 'ROCKETCHAT_PASSWORD'
ROCKETCHAT_AUTH_TOKEN = 'ROCKETCHAT_AUTH_TOKEN'
ROCKETCHAT_USER_ID = 'ROCKETCHAT_USER_ID'
ROCKETCHAT_MESSAGE_SEARCH_DEFAULT=7
ROCKETCHAT_MESSAGE_COUNT=50
ROCKETCHAT_TIME_FORMAT='%Y-%m-%dT%H:%M:%S.000Z'

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

def get_channels(session, server):
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

def process_item(final_dict, history_type, key):
    if key in final_dict[history_type]:
        final_dict[history_type][key] += 1
    else:
        final_dict[history_type][key] = 1

    final_dict['statistics'][history_type] += 1

def get_channel_history_stats(session, channel, history_days):
    newest_date = datetime.now().utcnow()
    oldest_date = newest_date - relativedelta(days=history_days)
    formatted_oldest_date = oldest_date.strftime(ROCKETCHAT_TIME_FORMAT)
    formatted_newest_date = newest_date.strftime(ROCKETCHAT_TIME_FORMAT)
    return get_channel_history(session, channel, formatted_oldest_date, formatted_newest_date)

def get_channel_history(session, channel, oldest_date, newest_date, current_latest_date=None, final_dict=None):

    if final_dict is None:
        final_dict = {'messages': {}, 'joined': {}, 'removed': {}, 'statistics': {'messages': 0, 'joined': 0, 'removed': 0}}

    params = {'roomId': channel['_id'], 'oldest': oldest_date, 'count': ROCKETCHAT_MESSAGE_COUNT}

    if current_latest_date is not None:
        params['latest'] = current_latest_date

    channel_history = session.get("https://{0}/api/v1/channels.history?".format(server), params=params)

    messages = channel_history.json()['messages']

    for message in messages:

        if 't' in message:
            if message['t'] == "uj":
                process_item(final_dict, "joined",message['msg'])
            elif message['t'] == "ru":
                process_item(final_dict, "removed",message['msg'])
        else:
            process_item(final_dict, "messages",message['u']['username'])

    if len(messages) > 0:
        return get_channel_history(session, channel, oldest_date, newest_date, messages[-1]['ts'], final_dict)
    else:
        return final_dict


rocketchat_username = os.environ.get(ROCKETCHAT_USERNAME)
rocketchat_password = os.environ.get(ROCKETCHAT_PASSWORD)
rocketchat_auth_token = os.environ.get(ROCKETCHAT_AUTH_TOKEN)
rocketchat_user_id = os.environ.get(ROCKETCHAT_USER_ID)

parser = argparse.ArgumentParser(description='Gather Rocketchat Statistics.')
parser.add_argument("-f","--filter", help="Text in Channel Description to Filter On", required=True)
parser.add_argument("-d","--days", help="Number of Days to Search for Records", type=int)
parser.add_argument("-s","--server", help="Rocketchat Server")
args = parser.parse_args()

filtered_text = args.filter
server = args.server
days = args.days

if not server:
    server = ROCKETCHAT_SERVER_DEFAULT

if not days:
    days = ROCKETCHAT_MESSAGE_SEARCH_DEFAULT

session = requests.Session()

error = login(session, server, rocketchat_username, rocketchat_password, rocketchat_auth_token, rocketchat_user_id)

if error is not None:
    print error
    sys.exit(1)

channels = get_channels(session, server,)

filter_channels(channels, filtered_text)


print "=== Rocketchat Statistics For the Past {0} Days ===\n".format(days)
if len(channels) > 0:
    for channel in channels:
        channel_history_stats = get_channel_history_stats(session, channel, days)
        print "{0}".format(channel['name'])
        print "  {0} Users Joined".format(channel_history_stats['statistics']['joined'])
        print "  {0} Users Removed".format(channel_history_stats['statistics']['removed'])
        print "  {0} Messages".format(channel_history_stats['statistics']['messages'])
        for username, username_num_messages in sorted(channel_history_stats['messages'].iteritems(), key=lambda (k,v): (v,k), reverse=True):
            print "    * {0} - {1:.2f}% - {2} Messages".format(username, (float(username_num_messages)/float(channel_history_stats['statistics']['messages'])*100), username_num_messages)

else:
    print "No Rocketchat Channels Match the description '{0}'".format(filtered_text)
#!/usr/bin/env python

import os, json, requests, sys, argparse, collections, re, operator, csv
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

def process_item(final_dict, history_type, key):
    if key in final_dict[history_type]:
        final_dict[history_type][key] += 1
    else:
        final_dict[history_type][key] = 1

    final_dict['statistics'][history_type] += 1

def plural_items(text, obj):
    if obj is not None and (isinstance(obj, collections.Iterable) and len(obj) == 1) or obj == 1:
        return text[:-1]
    else:
        return text


def get_channel_history_stats(session, channel, newest_date, oldest_date):
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

def write_ouput_file_record(filename, output_file_records, first_record=None):

    mode = 'a' if not first_record else 'w'

    with open(filename, mode) as f:
        fieldnames = ['Chat Channel (ID)', 'Time Period', '# Users Joined', '# Messages', 'Individual User Data - % messages/channel/user']
        writer = csv.writer(f)

        if first_record is not None and first_record == True:
             writer.writerow(fieldnames)

        writer.writerow(output_file_records)


rocketchat_username = os.environ.get(ROCKETCHAT_USERNAME)
rocketchat_password = os.environ.get(ROCKETCHAT_PASSWORD)
rocketchat_auth_token = os.environ.get(ROCKETCHAT_AUTH_TOKEN)
rocketchat_user_id = os.environ.get(ROCKETCHAT_USER_ID)

parser = argparse.ArgumentParser(description='Gather Rocketchat Statistics.')
parser.add_argument("-f","--filter", help="Text in Channel Description to Filter On", required=True)
parser.add_argument("-d","--days", help="Number of Days to Search for Records", type=int)
parser.add_argument("-s","--server", help="Rocketchat Server")
parser.add_argument("-o","--output", help="Output File")
args = parser.parse_args()

filtered_text = args.filter
server = args.server
days = args.days
output_file = args.output

if not server:
    server = ROCKETCHAT_SERVER_DEFAULT

if not days:
    days = ROCKETCHAT_MESSAGE_SEARCH_DEFAULT

session = requests.Session()

error = login(session, server, rocketchat_username, rocketchat_password, rocketchat_auth_token, rocketchat_user_id)

if error is not None:
    print error
    sys.exit(1)

channels = get_channels(session, server)

filter_channels(channels, filtered_text)

newest_date = datetime.now().utcnow()
oldest_date = newest_date - relativedelta(days=days)

formatted_time_period = "{0} - {1}".format(oldest_date.strftime("%m/%d/%Y"), newest_date.strftime("%m/%d/%Y"))

print "=== Rocketchat Statistics For {0} ===\n".format(formatted_time_period)
if len(channels) > 0:
    for channel_index, channel in enumerate(channels):
        
        output_file_row_records = []

        channel_history_stats = get_channel_history_stats(session, channel, newest_date, oldest_date)

        formatted_channel_name = "#{0}".format(channel['name'])
        users_joined = channel_history_stats['statistics']['joined']
        users_removed = channel_history_stats['statistics']['removed']
        total_messages = channel_history_stats['statistics']['messages']

        print formatted_channel_name
        print "  {0} {1} Joined".format(users_joined, plural_items("Users", users_joined))
        print "  {0} {1} Removed".format(users_removed, plural_items("Users", users_removed))
        print "  {0} {1}".format(total_messages, plural_items("Messages", total_messages))

        output_file_user_messages = ""

        for username, username_num_messages in sorted(channel_history_stats['messages'].iteritems(), key=lambda (k,v): (v,k), reverse=True):
            
            user_messages = "{0} - {1:.2f}% - {2} {3}".format(username, (float(username_num_messages)/float(total_messages)*100), username_num_messages, plural_items("Messages", username_num_messages))
            
            print "    * {0}".format(user_messages)

            if output_file_user_messages is not "":
                output_file_user_messages += "\n"
            
            output_file_user_messages += user_messages
    
        if output_file is not None:
            
            output_file_row_records.append(formatted_channel_name)
            output_file_row_records.append(formatted_time_period)
            output_file_row_records.append(users_joined)
            output_file_row_records.append(total_messages)
            output_file_row_records.append(output_file_user_messages)

            if channel_index == 0:
                write_ouput_file_record(output_file, output_file_row_records, True)
            else:
                write_ouput_file_record(output_file, output_file_row_records)

else:
    print "No Rocketchat Channels Match the description '{0}'".format(filtered_text)

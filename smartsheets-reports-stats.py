#!/usr/bin/env python

import json,argparse,sys,re,os,requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

API_TOKEN_NAME = 'SMARTSHEETS_API_TOKEN'
DEFAULT_POINTS_GROUPING = "Cards Closed"

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

parser = argparse.ArgumentParser(description='Gather Smartsheet Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-e","--sheet-id", help="The smartsheets sheet id to pull data from")
parser.add_argument("-g","--points-grouping", help="Points grouping (ie. Cards Closed)")
parser.add_argument("-b","--board-id", help="Link back to the original smartsheet")
parser.add_argument("-c","--channel", help="Points Channel")
args = parser.parse_args()
start_date = args.start_date
points_grouping = args.points_grouping
channel = args.channel
sheet_id = args.sheet_id
board_id = args.board_id

if start_date is None:
    print "Error: Please provide a start date!"
    sys.exit(1)

if sheet_id is None:
    print "Error: Smartsheets sheet ID must be provided!"
    sys.exit(1)

if board_id is None:
    print "Error: Smartsheets board ID must be provided in order to build a like back to the origin of the points!"
    sys.exit(1)

if points_grouping is None:
    points_grouping = DEFAULT_POINTS_GROUPING


api_token = os.environ.get(API_TOKEN_NAME)
if not api_token:
    print "Error: Smartsheets API Key is Required!"
    sys.exit(1)


today_date = datetime.now()

headers = {}
resp = requests.get("https://api.smartsheet.com/2.0/reports/{0}?level=2&pageSize=400&include=objectValue".format(sheet_id), headers={"Authorization":"Bearer {0}".format(api_token)})
sheet = json.loads(resp.text)

column_map={}
for column in sheet["columns"]:
    column_map[column["title"]] = column["index"]

def get_cell_by_column_name(row, column_name):
    column_idx = column_map[column_name]
    return row["cells"][column_idx]


fields=["Row ID","Verification of Email","Program Name","Points","Approved / Declined Date"]
for r in sheet["rows"]:
    row={}
    row["modifiedAt"]=str(r["modifiedAt"])
    row["id"]=str(r["id"])
    row["Status"]=get_cell_by_column_name(r,"Status")["value"]
    row["modifiedAt"]=get_cell_by_column_name(r,"Approved / Declined Date")["value"]
    row["modifiedAt"]=datetime.strptime(row["modifiedAt"], "%Y-%m-%d") # remove the time part from the date/timestamp so it's easier to compare
    
    if row["modifiedAt"] >= start_date and row["Status"]=="Approved" and (channel is None or (channel!=None and re.search(channel, row["Program Name"])!=None)):
        for field in fields:
            row[field]=get_cell_by_column_name(r,field)["value"]
        
        recipient = row["Verification of Email"]
        recipient = recipient.replace("@redhat.com","")
        
        if re.search("Thought Leadership.*", row["Program Name"]):
            pool="ThoughtLeadership"
        elif re.search("Community.*", row["Program Name"]):
            pool="Trello" # should be CoP but we havent migrated CoP points to a multi-program structure yet
        elif re.search("Adopt.*", row["Program Name"]):
            pool="ServicesSupport"
        elif re.search("First and Thirds.*", row["Program Name"]):
            pool="ServicesSupport"
        else:
            pool="ServicesSupport"
        
        print "{0}/SS{1}/{2}/{3} [pool={4},board={5},rowId={6},linkId={7}]".format(points_grouping, row["id"], recipient,int(row["Points"]),pool,board_id,row["id"],row["Row ID"])
        
        # outputs Giveback "duplicate records" as output. Used to prevent historical duplicate allocation of points  
        #print "\"SS{0}.{1}\",".format(row["id"],recipient)






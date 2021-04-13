#!/usr/bin/env python

import smartsheet,json,argparse,sys,re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

TOKEN = "7o8djelr503ekzb4phyje3wvoh"
SHEET_ID = "3510398591756164"
SHEET_NAME = "*GiveBack Program Data"
DEFAULT_POINTS_GROUPING = "Cards Closed"
DEFAULT_POINTS_POOL = "UNKNOWN"

def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

parser = argparse.ArgumentParser(description='Gather Smartsheet Statistics.')
parser.add_argument("-s","--start-date", help="The start date to query from", type=valid_date)
parser.add_argument("-g","--points-grouping", help="Points Bucket")
parser.add_argument("-p","--pool", help="Points Pool")
parser.add_argument("-c","--channel", help="Points Channel")
args = parser.parse_args()
start_date = args.start_date
points_grouping = args.points_grouping
points_pool = args.pool
channel = args.channel

if start_date is None:
    print "Error: Please provide a start date!"
    sys.exit(1)

if points_pool is None:
    points_pool = DEFAULT_POINTS_POOL

if points_grouping is None:
    points_grouping = DEFAULT_POINTS_GROUPING

today_date = datetime.now()

ss = smartsheet.Smartsheet(TOKEN)
ss.errors_as_exceptions(True)
sheet = ss.Sheets.get_sheet(SHEET_ID)

column_map={}
for column in sheet.columns:
    column_map[column.title] = column.id


def get_cell_by_column_name(row, column_name):
    column_id = column_map[column_name]
    return row.get_column(column_id)


fields=["Row ID","Program Name","Points","Created By"]
for r in sheet.rows:
    row={}
    jsonData=json.loads(r.to_json())
    row["modifiedAt"]=jsonData["modifiedAt"]
    row["id"]=str(jsonData["id"])
    modifiedAt=datetime.strptime(str(row["modifiedAt"])[:10], "%Y-%m-%d")
    status=get_cell_by_column_name(r,"Status").value

    if modifiedAt >= start_date and status=="Approved" and (channel is None or (channel!=None and re.search(channel, row["Program Name"])!=None)):
        for field in fields:
            row[field]=get_cell_by_column_name(r,field).value
        row["Created By"]=row["Created By"].replace("@redhat.com","")
        if re.search("Thought Leadership.*", row["Program Name"]):
            pool="ThoughtLeadership"
        if re.search("Community.*", row["Program Name"]):
            pool="ThoughtLeadership"
        if re.search("Adopt.*", row["Program Name"]):
            pool="ServicesSupport"
        if re.search("First and Thirds.*", row["Program Name"]):
            pool="ServicesSupport"
        
        print "{0}/SS{1}/{2}/{3} [pool={4},board=cXCGH32HjPp2mQV3MfxJX4WVVFQ9xJ5J2VCmX8F1,linkId={5}]".format(points_grouping, row["id"], row["Created By"],int(row["Points"]),pool,row["Row ID"])
        
        # outputs Giveback "duplicate records" as output. Used to prevent historical duplicate allocation of points  
        #print "\"SS{0}.{1}\",".format(row["id"],row["Created By"])






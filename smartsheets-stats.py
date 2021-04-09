#!/usr/bin/env python

import smartsheet,json,argparse,sys,re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

TOKEN = "7o8djelr503ekzb4phyje3wvoh"
SHEET_ID = "3510398591756164"
SHEET_NAME = "*GiveBack Program Data"
DEFAULT_POINTS_GROUPING = "Completed"
DEFAULT_POINTS_POOL = "XXX"

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
parser.add_argument("-c","--community", help="Points Channel")
args = parser.parse_args()
start_date = args.start_date#datetime.strptime(args.start_date, "%Y-%m-%d")
points_grouping = args.points_grouping
points_pool = args.pool
community = args.community

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

# build a column map for later use
column_map={}
for column in sheet.columns:
    column_map[column.title] = column.id


def get_cell_by_column_name(row, column_name):
    column_id = column_map[column_name]
    return row.get_column(column_id)


fields=["Created By","Date","Status","Points"]
for r in sheet.rows:
    row={}
    jsonData=json.loads(r.to_json())
    row["modifiedAt"]=jsonData["modifiedAt"]
    row["id"]=str(jsonData["id"])
    row["username"]=get_cell_by_column_name(r,"Created By").value.replace("@redhat.com","")
    row["Community"]=get_cell_by_column_name(r,"Community").value#.replace("-","")
    modAt=datetime.strptime(str(row["modifiedAt"])[:10], "%Y-%m-%d")
    status=get_cell_by_column_name(r,"Status").value

    if modAt >= start_date and status=="Approved" and (community is None or (community!=None and re.search(community, row["Community"])!=None)):
        for field in fields:
            row[field]=get_cell_by_column_name(r,field).value
        if re.search("Thought Leadership.*", row["Community"]):
            pool="ThoughtLeadership"
        if re.search("Community.*", row["Community"]):
            pool="ThoughtLeadership"
        if re.search("Adopt.*", row["Community"]):
            pool="ServicesSupport"
        if re.search("First and Thirds.*", row["Community"]):
            pool="ServicesSupport"
#        if pool is None:
#            pool=row["Community"]
        #print row
        #print "{0}/SS{1}/{2}/{3} [pool={4}, community={5}]".format(points_grouping, row["id"], row["username"],int(row["Points"]),pool,row["Community"])
        print "{0}/SS{1}/{2}/{3} [pool={4}]".format(points_grouping, row["id"], row["username"],int(row["Points"]),pool)







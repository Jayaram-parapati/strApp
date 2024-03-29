import pandas as pd
import sys
import numpy as np
from datetime import datetime
import json
from pymongo import MongoClient
import threading
import os
import warnings


# Ignore all warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

#! todo: read year from first sheet
year = 2022
weekdays = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
week_range = []
mongoc = MongoClient("mongodb://localhost:27017")
# mongoc = MongoClient("mongodb://mongodbserver:27017")
db = mongoc["str7"]

# file = "04.04.2023"
# if len(sys.argv) > 1:
#     file = sys.argv[1]

# filename = f"files/STR (1)/{file}.xlsx"

config = {
    "required_sheets": [0,3,4,6,8],
    "meta_rows": {
        3: [range(4)],
        4: [range(4)],
        6: [range(4)],
        8: [range(4)],
    },
    "split_dfs": {3: True, 4: True, 6: True, 8: True},
    "save_to_db": True,
}


def consecs(ll):
    ol = []
    cfound = False
    for i, l in enumerate(ll):
        if i < len(ll) - 1 and l == ll[i + 1] - 1:
            cfound = True
            continue
        elif cfound == True:
            ol.append(l)
            cfound = False
    return ol


def boundaries(a, start, end):
    ranges = []
    for i in a:
        if start != i:
            ranges.append([start, i])
        start = i + 1
    if start < end:
        ranges.append([start, end])
    return ranges


def prepare_dfs(sheets,xl):
    dfs = []
    # meta_rows = [list() for x in sheets]
    for index, sheet in enumerate(sheets):
        
        if index not in config["required_sheets"]:
            continue

        df = xl.parse(sheet, header=None)
        
        if config["meta_rows"] != None:
            if index in config["meta_rows"].keys():
                for rows in config["meta_rows"][index]:
                    # meta_rows[index].append(df.iloc[rows])
                    dfs.append(
                        {"sheet": f"meta-{sheet}", "index": index, "df": df.iloc[rows]}
                    )

                    df.drop(df.index[rows], inplace=True)
                    

        df.reset_index(drop=True, inplace=True)
        
        df.columns = range(df.columns.size)
        

        if index in config["split_dfs"].keys():
            df["nancnt"] = df.isnull().sum(axis=1)
            
            maxcnt = max(df["nancnt"])
            maxrows = df.index[df["nancnt"] >= maxcnt].to_list()
            df.drop(columns=["nancnt"], inplace=True)
            

            splitindex = consecs(maxrows)
            boxes = boundaries(splitindex, 0, df.shape[0])

            for b in boxes:
                tdf = df.iloc[b[0] : b[1], :]
                if tdf.size > 1:
                    # print(tdf.size)
                    dfs.append({"sheet": sheet, "index": index, "df": tdf})

            # input("Enter any key...")
        else:
            dfs.append({"sheet": sheet, "index": index, "df": df})
    return dfs


def export_glance_to_mongo(dictdata, dates, str_id):
    if len(dates) == 0:
        # case: glance 1 - not implemented yet, need to think about storing cumulatives...
        return

    alldates = pd.date_range(dates[0], dates[1], freq="d")
    weekdates = dict(zip(weekdays, alldates))
    # print(weekdates)
    for d in dictdata:
        collection_name = d["Rtype"].lower()
        if (
            collection_name not in db.list_collection_names()
            and config["save_to_db"] == True
        ):
            # print(f"Creating Collection {collection_name}")
            db.create_collection(
                collection_name,
                timeseries={"timeField": "timestamp", "metaField": "metadata"},
            )
            # command = f"""db.{collection_name}.createIndex({{"metadata.label":-1, "timestamp":1}},{{"unique":true}})"""
            # db.command(command, collection_name)
            # print(command)
            # following index will avoid duplicates, but its not supported until monogo 6.3
            # failed with error : Unique indexes are not supported on collections clustered by _id
            # so either update mongodb to latest version, or employ other method to avoid duplicates
            # like update : upsert
            # db[collection_name].create_index(
            #     [("timestamp", 1), ("metadata.label", -1)], unique=True
            # )

        label_name = d["Label"]
        for wd in weekdays:
            change = d[f"{wd}-Change"]
            change_rate = d[f"{wd}-ChangeRate"]
            record = {
                "metadata": {"label": label_name, "str_id": str_id},
                "timestamp": weekdates[wd],
                "change": change,
                "change_rate": change_rate,
            }
            if config["save_to_db"] == True:
                db[collection_name].insert_one(record)
            # using update_one with upsert=True inorder to avoid duplicates
            # but failed with error : Cannot perform a non-multi update on a time-series collection
            # db[collection_name].update_one(
            #     {"timestamp": weekdates[wd], "metadata": {"label": label_name}},
            #     {
            #         "$set": {
            #             "change": change,
            #             "change_rate": change_rate,
            #         }
            #     },
            #     upsert=True,
            # )


extra_dfs = {}


def prepare_other_sheet(dfo, collection_name, str_id):
    global year
    # collection_name = "occ_ss"
    if (
        collection_name not in db.list_collection_names()
        and config["save_to_db"] == True
    ):
        # print(f"Creating Collection {collection_name}")
        db.create_collection(
            collection_name,
            timeseries={"timeField": "timestamp", "metaField": "metadata"},
        )
        # db[collection_name].create_index(
        #     [("timestamp", 1), ("metadata.label", -1)], unique=True
        # )
    df = dfo["df"]
    df.replace("Exchange Rate*", np.nan, inplace=True)
    df.dropna(axis="columns", how="all", inplace=True)
    df.dropna(axis="rows", how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)
    # year = 2023  # todo: read year from somewhere in current sheet or other sheet

    if df.shape[1] >= 28:
        label_name = df.iloc[0, 0]
        if pd.isnull(label_name):
            df.drop(df.head(2).index, axis=0, inplace=True)
            df.reset_index(drop=True, inplace=True)
            label_name = df.iloc[0, 0]

        df.iloc[[0]] = df.iloc[[0]].ffill(axis=1)

        if label_name != "Rank":
            df_date = df.iloc[:2, :-4]
            df_sms = df.iloc[-1:, :-4]
            df_weeklyavg = df.iloc[:,[0,-3,-2,-1]]
            # print(label_name)
            if df_date.shape[1] == df_sms.shape[1]:
                #! save to db
                for c in range(1, df_date.shape[1]):
                    mon, day = df_date.iloc[0, c], df_date.iloc[1, c]
                    dateobj = datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
                    ss = df_sms.iloc[0, c]
                    # if pd.isnull(ss):
                    #     print("alas! need recalibrations")
                    record = {
                        "metadata": {"label": label_name, "str_id": str_id},
                        "timestamp": dateobj,
                        "submarket_scale": ss,
                    }
                    # print(record)
                    try:
                        if config["save_to_db"] == True:
                            db[collection_name].insert_one(record)
                    except Exception as e:
                        print(e)

                #! save last     to db
                edf = df.iloc[:5, [0, -4]]
                edf.columns = [0, 1]
                if collection_name in extra_dfs:
                    extra_dfs[collection_name].append(edf)
                else:
                    extra_dfs[collection_name] = [edf]
            # saving weekly avgs 
            for r in range(2,df_weeklyavg.shape[0]):
                for c in range(1,df_weeklyavg.shape[1]): 
                    df_weeklyavg.columns = range(df_weeklyavg.columns.size)
                    df = df_weeklyavg
                    avg_type = str(df.iloc[0,c])+" "+str(df.iloc[1,c])
                    sub_label = df.iloc[r,0]
                    avg = df.iloc[r,c]
                    record = {
                        "metadata": {"label": label_name, "str_id": str_id},
                        "timestamp": week_range[0],
                        "avg_type":avg_type,
                        "sub_label":sub_label,
                        "average":avg
                    }
                    try:
                        if config["save_to_db"] == True:
                            db[collection_name].insert_one(record)
                    except Exception as e:
                        print(e)
                
        else:  # todo save ranks to db
            if (
                f"{collection_name}_ranks" not in db.list_collection_names()
                and config["save_to_db"] == True
            ):
                # print(f"Creating Collection {collection_name}")
                db.create_collection(
                    f"{collection_name}_ranks",
                    timeseries={"timeField": "timestamp", "metaField": "metadata"},
                )
            ranks_df = df.iloc[:, :-3]
            df_weekly_rank_avg = df.iloc[:,[0,-3,-2,-1]]

            # print(ranks_df)
            myrank_label = ranks_df.iloc[2, 0]
            typerank_label = ranks_df.iloc[3, 0]
            for c in range(1, ranks_df.shape[1]):
                mon, day = ranks_df.iloc[0, c], ranks_df.iloc[1, c]
                dateobj = datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
                
                myrankvalue = ranks_df.iloc[2, c]
                if not pd.isna(myrankvalue):
                    myrank = myrankvalue.split("of")
                else:myrank = [0,0]    
                
                typerankValue = ranks_df.iloc[3,c]
                if not pd.isna(typerankValue):
                    typerank = typerankValue.split("of")
                else:typerank = [0,0]    
                # if pd.isnull(myrank) or pd.isnull(typerank):
                #     print("alas! need recalibrations")
                record1 = {
                    "metadata": {"label": myrank_label, "str_id": str_id},
                    "timestamp": dateobj,
                    "rank": [int(myrank[0]),int(myrank[1])],
                }
                record2 = {
                    "metadata": {"label": typerank_label,"str_id": str_id},
                    "timestamp": dateobj,
                    "rank": [int(typerank[0]),int(typerank[1])],
                }
                # print(record1, record2)
                try:
                    if config["save_to_db"] == True:
                        db[f"{collection_name}_ranks"].insert_one(record1)
                        db[f"{collection_name}_ranks"].insert_one(record2)
                except Exception as e:
                    print(e)
            #saving weekly rank avgs
            for c in range(1, df_weekly_rank_avg.shape[1]):
                df_weekly_rank_avg.columns = range(df_weekly_rank_avg.columns.size)
                df = df_weekly_rank_avg
                avg_type = str(df.iloc[0,c])+" "+str(df.iloc[1,c]) 
                myrankvalue = df_weekly_rank_avg.iloc[2, c]
                if not pd.isna(myrankvalue):
                    myrank = myrankvalue.split("of")
                else:myrank = [0,0]    
                
                typerankValue = df_weekly_rank_avg.iloc[3,c]
                if not pd.isna(typerankValue):
                    typerank = typerankValue.split("of")
                else:typerank = [0,0]    
                # if pd.isnull(myrank) or pd.isnull(typerank):
                #     print("alas! need recalibrations")
                record1 = {
                    "metadata": {"label": myrank_label, "str_id": str_id},
                    "timestamp": week_range[0],
                    "rank": [int(myrank[0]),int(myrank[1])],
                    "avg_type":avg_type
                }
                record2 = {
                    "metadata": {"label": typerank_label,"str_id": str_id},
                    "timestamp": week_range[0],
                    "rank": [int(typerank[0]),int(typerank[1])],
                    "avg_type":avg_type
                }
                # print(record1, record2)
                try:
                    if config["save_to_db"] == True:
                        db[f"{collection_name}_ranks"].insert_one(record1)
                        db[f"{collection_name}_ranks"].insert_one(record2)
                except Exception as e:
                    print(e)

def prepare_daily_sheet(dfo, str_id):
    global year
    df = dfo["df"]
    df.dropna(axis="columns", how="all", inplace=True)
    df.dropna(axis="rows", how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)
    # year = 2023
    # if df.shape[0] < 9:
    # datestr = df.iloc[0, 0]
    # datestr = datestr.split(",")
    # year = datestr[len(datestr) - 1].strip()
    # print(year)
    if df.shape[0] >= 9:
        collection_name = df.iloc[0, 0]
        if pd.isnull(collection_name):
            df.drop(index=df.index[0], axis=0, inplace=True)
            df.reset_index(drop=True, inplace=True)
            collection_name = df.iloc[0, 0]
        collection_name = "".join([c for c in collection_name if c.isalpha()]).lower()

        # extract daily data, exclude last 3 columns
        df_change = df.iloc[2:5, :-3]
        df_rchange = df.iloc[6:9, :-3]

        # generate dates
        month_name = df.iloc[0, 1]
        # print(month_name)
        dates = [
            datetime.strptime(f"{month_name} 1, {year}", "%b %d, %Y").isoformat(),
            datetime.strptime(
                f"{month_name} {df_change.shape[1]-1}, {year}", "%b %d, %Y"
            ).isoformat(),
        ]
        alldates = pd.date_range(dates[0], dates[1], freq="d")
        # print(alldates)

        # shapes should match
        if df_change.shape == df_rchange.shape:
            # print(len(df_change.columns), df.shape[1])
            df_change.columns = range(df_change.shape[1])
            df_rchange.columns = range(df_rchange.shape[1])
            df_change.reset_index(drop=True, inplace=True)
            df_rchange.reset_index(drop=True, inplace=True)
            # print(df_change)
            # print(df_rchange)
            # pass
            # export_daily_to_mongo(dictdata, dates)
            if (
                collection_name not in db.list_collection_names()
                and config["save_to_db"] == True
            ):
                # print(f"Creating Collection {collection_name}")
                db.create_collection(
                    collection_name,
                    timeseries={"timeField": "timestamp", "metaField": "metadata"},
                )
                # db[collection_name].create_index(
                #     [("timestamp", 1), ("metadata.label", -1)], unique=True
                # )
                # create index if neccessary
            for r in range(df_change.shape[0]):
                label_name = df_change.iloc[r, 0]
                for d in range(1, df_change.shape[1]):
                    if not pd.isna(df_change.iloc[r, d]):
                        change = df_change.iloc[r, d]
                    else:change = 0 
                    if not pd.isna(df_rchange.iloc[r, d]):
                        change_rate = df_rchange.iloc[r, d]
                    else:change_rate = 0
                    record = {
                        "metadata": {"label": label_name, "str_id": str_id},
                        # "timestamp": dates[d - 1].strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "timestamp": alldates[d - 1],
                        "change": change,
                        "change_rate": change_rate,
                    }
                    # print(record)
                    try:
                        if config["save_to_db"] == True:
                            if record["change"] != 0:
                                ts = record["timestamp"]
                                ts_obj = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second)
                                q = {"timestamp":{"$eq":ts_obj},"metadata.str_id":str_id,"metadata.label":label_name}
                                match_obj = db[collection_name].find_one(q)
                                if not match_obj:
                                    db[collection_name].insert_one(record)                           
                    except Exception as e:
                        print(e)


def prepare_glance_sheet(dfo, str_id):
    # logic to convert glance to mongodb
    # print(dfo)
    colmns = [
        "Rtype",
        "Label",
    ]
    for wd in weekdays:
        colmns.append(f"{wd}-ChangeRate")
        colmns.append(f"{wd}-Change")
    colmns.extend(
        [
            "Total-ChangeRate",
            "Total-Change",
        ]
    )
    df = dfo["df"]
    # print(df.shape[0])
    # input("...")
    if df.shape[0] > 1 and df.shape[1] > 1:
        daterange = df.iloc[1, 1]
        dates = []
        if not pd.isnull(daterange):
            dates = daterange.split("-")
            dates = [
                datetime.strptime(d.strip(), "%B %d, %Y").isoformat() for d in dates
            ]  # from - to
            # print(dates)
    if df.shape[1] >= len(colmns) and df.shape[0] >= 9:
        rows = range(df.shape[0] - 12)  # remove first extra rows
        df.drop(df.index[rows], inplace=True)
        df.dropna(axis="columns", how="all", inplace=True)
        df.dropna(axis="rows", how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)
        # df.columns = range(df.shape[1])

        df.columns = colmns
        df = df.ffill()
        dictdata = df.to_dict("records")
        export_glance_to_mongo(dictdata, dates, str_id)


def process_extra_dfs(collection_name, str_id):
    # if collecion_name=="occ_ss":
    # occupancy
    edf = extra_dfs[collection_name]
    cname = collection_name.replace("_ss", "")

    def getrecord(index, rowindex, other=False):
        if other == False:
            label_name = edf[index].iloc[rowindex, 0]
        else:
            label_name = edf[index].iloc[0, 0]
        mon, day = edf[index].iloc[0, 1], edf[0].iloc[1, 1]
        dateobj = datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
        change = edf[index].iloc[rowindex, 1]
        change_rate = edf[index + 1].iloc[rowindex, 1]
        record = {
            "metadata": {"label": label_name, "str_id": str_id},
            "timestamp": dateobj,
            "change": change,
            "change_rate": change_rate,
        }
        # print(record)
        try:
            if config["save_to_db"] == True:
                db[cname].insert_one(record)
        except Exception as e:
            print(e)

    getrecord(0, 2)
    getrecord(0, 3)
    getrecord(2, 2, other=True)


def prepare_toc_sheet(dfo):
    # print(dfo)
    global year
    global week_range
    collection_name = "str_reports"
    df = dfo["df"]

    df.dropna(axis="columns", how="all", inplace=True)
    df.dropna(axis="rows", how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.columns = range(df.shape[1])
    # df.to_csv("output/toc.csv")
    strinfo = {}
    idc = df.iloc[0, 0].split("/")
    strinfo["str_id"] = idc[0].split("#")[1].strip()
    prop = df.iloc[1, 0].split(":")
    dtr = df.iloc[2, 0].split(":")
    dates = dtr[1].strip().split("-")
    drange = [datetime.strptime(d.strip(), "%B %d, %Y") for d in dates]
    strinfo["str_property"] = prop[1].strip()
    strinfo["str_date_range"] = drange
    year = drange[0].year
    week_range = drange
    if (
        collection_name not in db.list_collection_names()
        and config["save_to_db"] == True
    ):
        # print(f"Creating Collection {collection_name}")
        db.create_collection(
            collection_name,
            # timeseries={"timeField": "timestamp", "metaField": "metadata"},
        )
    if config["save_to_db"] == True:
        check_strid = db[collection_name].find_one({"str_id":strinfo["str_id"]})
        if check_strid:
            return check_strid["_id"]
        else:
            result = db[collection_name].insert_one(strinfo)
            return result.inserted_id
    # print(strinfo)
    # print(df)


def prepare_all_dfs(sheets,xl):
    
    dfs = prepare_dfs(sheets,xl)
    try:
        for index, dfo in enumerate(dfs):
            # print(dfo["sheet"])
            if dfo["sheet"] == "Table of Contents":
                str_id = prepare_toc_sheet(dfo)
            # if dfo["sheet"] == "Glance":
            #     prepare_glance_sheet(dfo)
            if dfo["sheet"] == "Daily by Month":
                prepare_daily_sheet(dfo, str_id)
            if dfo["sheet"] == "Occ":
                prepare_other_sheet(dfo, "occupancy_ss", str_id)
            if dfo["sheet"] == "ADR":  # todo: need to check if values are correct
                prepare_other_sheet(dfo, "adr_ss", str_id)
            if dfo["sheet"] == "RevPAR":  # todo: need to check if values are correct
                prepare_other_sheet(dfo, "revpar_ss", str_id)
        for key, value in extra_dfs.items():
            process_extra_dfs(key, str_id)    
        return {'message':'Extraction Success', 'status':200}
    except Exception as e:
        return {'message':e, 'status':500}

# prepare_all_dfs()




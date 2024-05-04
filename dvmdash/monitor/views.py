from django.shortcuts import render
from pymongo import MongoClient
import os
import sys
import dotenv
from pathlib import Path
from django.shortcuts import HttpResponse, redirect
from django.template import loader
from nostr_sdk import Timestamp
from datetime import datetime
import json
import monitor.helpers as helpers


if os.getenv("USE_MONGITA", "False") != "False":  # use a local mongo db, like sqlite
    print("Using mongita")
    from mongita import MongitaClientDisk

    mongo_client = MongitaClientDisk()
    db = mongo_client.dvmdash
    print("Connected to local mongo db using MONGITA")
else:
    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        print(f"There are {result} documents in events collection")
    except Exception as e:
        print("Could not count documents in db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo db")


def overview(request):
    print("calling overview!")
    context = {}

    # get the number of events in the database
    num_dvm_events_in_db = db.events.count_documents({})
    context["num_dvm_events_in_db"] = num_dvm_events_in_db

    # get the number of unique kinds of all events
    # TODO - use a proper mongo query here
    all_dvm_events_cursor = db.events.find({"kind": {"$gte": 5000, "$lte": 6999}})
    all_dvm_events = list(all_dvm_events_cursor)

    dvm_nip89_profiles = {}

    for nip89_event in db.events.find({"kind": 31990}):
        if "pubkey" in nip89_event:
            try:
                dvm_nip89_profiles[nip89_event["pubkey"]] = json.loads(
                    nip89_event["content"]
                )
                # print(
                #     f"Successfully loaded json from nip89 event for pubkey {nip89_event['pubkey']}"
                # )
            except Exception as e:
                # print(f"Error loading json from {nip89_event['content']}")
                # print(f"Content is: {nip89_event['content']}")
                # print(e)
                pass

    kinds_counts = {}
    kind_feedback_counts = {}
    zap_counts = 0
    dm_counts = 0
    uncategorized_counts = 0
    num_dvm_events = 0

    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_time_24hr = Timestamp.from_secs(current_secs - (24 * 60 * 60))
    max_time_1week = Timestamp.from_secs(current_secs - (7 * 24 * 60 * 60))

    dvm_tasks_24h = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    context["num_dvm_tasks_24h"] = dvm_tasks_24h

    dvm_results_24h = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 6000, "$lte": 6999},
        }
    )
    context["num_dvm_results_24h"] = dvm_results_24h

    dvm_tasks_1week = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_1week.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    context["num_dvm_tasks_1week"] = dvm_tasks_1week

    dvm_results_1week = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_1week.as_secs()},
            "kind": {"$gte": 6000, "$lte": 6999},
        }
    )

    context["num_dvm_results_1week"] = dvm_results_1week

    # print the memory usages of all events so far:
    memory_usage = sys.getsizeof(all_dvm_events)
    # Convert memory usage to megabytes
    memory_usage_mb = memory_usage / (1024 * 1024)
    print(f"Memory usage of all_dvm_events: {memory_usage_mb:.2f} MB")

    # pub ids of all dvms
    dvm_job_results = {}

    # pub ids of all dvm requests - these are probably people?
    dvm_job_requests = {}

    for dvm_event_i in all_dvm_events:
        if "kind" in dvm_event_i:
            kind_num = dvm_event_i["kind"]

            if 5000 <= kind_num <= 5999 and kind_num not in [5666]:
                num_dvm_events += 1
                if kind_num in kinds_counts:
                    kinds_counts[kind_num] += 1
                else:
                    kinds_counts[kind_num] = 1

                dvm_request_pub_key = dvm_event_i["pubkey"]
                if dvm_request_pub_key in dvm_job_requests:
                    dvm_job_requests[dvm_request_pub_key] += 1
                else:
                    dvm_job_requests[dvm_request_pub_key] = 1

            elif 6000 <= kind_num <= 6999 and kind_num not in [6666]:
                num_dvm_events += 1
                if kind_num in kind_feedback_counts:
                    kind_feedback_counts[kind_num] += 1
                else:
                    kind_feedback_counts[kind_num] = 1

                dvm_pub_key = dvm_event_i["pubkey"]
                if dvm_pub_key in dvm_job_results:
                    dvm_job_results[dvm_pub_key] += 1
                else:
                    dvm_job_results[dvm_pub_key] = 1

            elif kind_num == 9735:
                zap_counts += 1
            elif kind_num == 4:
                dm_counts += 1
            else:
                uncategorized_counts += 1
        else:
            print("WARNING - event missing kind field")
            print(f"{dvm_event_i}")

    # replace dvm_job_results keys with names if available
    dvm_job_results_names = {}
    for pub_key, count in dvm_job_results.items():
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            dvm_job_results_names[dvm_nip89_profiles[pub_key]["name"]] = count
        else:
            dvm_job_results_names[pub_key] = count

    context["num_dvm_kinds"] = len(list(kinds_counts.keys()))
    context["num_dvm_feedback_kinds"] = len(list(kind_feedback_counts.keys()))
    context["zap_counts"] = zap_counts
    context["dm_counts"] = dm_counts
    context["uncategorized_counts"] = uncategorized_counts
    context["kinds_counts"] = kinds_counts
    context["kind_feedback_counts"] = kind_feedback_counts
    context["num_dvm_events"] = num_dvm_events
    context["dvm_job_results"] = {
        k: v for k, v in dvm_job_results_names.items() if v > 100
    }
    context["dvm_pub_keys"] = len(list(dvm_job_results.keys()))

    # get the top 15 dvm job requests pub ids
    # first sort dictionary by value
    # then pick the top 15
    # Sort the dictionary by value in descending order and get the top 15 items
    top_dvm_job_requests = sorted(
        dvm_job_requests.items(), key=lambda x: x[1], reverse=True
    )[:15]

    # Convert the list of tuples back to a dictionary
    top_dvm_job_requests_dict = dict(top_dvm_job_requests)

    top_dvm_job_requests_via_name = {}
    for pub_key, count in top_dvm_job_requests_dict.items():
        print(f"pub_key: {pub_key}, count: {count}")
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            top_dvm_job_requests_via_name[dvm_nip89_profiles[pub_key]["name"]] = count
        else:
            top_dvm_job_requests_via_name[pub_key] = count

    context["dvm_job_requests"] = top_dvm_job_requests_via_name

    for kind, count in kinds_counts.items():
        print(f"\tKind {kind} has {count} instances")

    print(f"Setting var num_dvm_kinds to {context['num_dvm_kinds']}")

    template = loader.get_template("monitor/overview.html")
    return HttpResponse(template.render(context, request))


def dvm(request, pub_key=""):
    print(f"Calling dvm with dvm_pub_key: {pub_key}")
    context = {}

    if pub_key == "":
        # get all dvm pub keys
        dvm_pub_keys = list(
            db.events.distinct("pubkey", {"kind": {"$gte": 5000, "$lte": 6999}})
        )

        # get all dvm pub key names from nip 89s
        dvm_nip89_profiles = {}

        for nip89_event in db.events.find({"kind": 31990}):
            if "pubkey" in nip89_event:
                try:
                    dvm_nip89_profiles[nip89_event["pubkey"]] = json.loads(
                        nip89_event["content"]
                    )
                    # print(
                    #     f"Successfully loaded json from nip89 event for pubkey {nip89_event['pubkey']}"
                    # )
                except Exception as e:
                    # print(f"Error loading json from {nip89_event['content']}")
                    # print(f"Content is: {nip89_event['content']}")
                    # print(e)
                    pass

        dvm_pub_keys_and_names = {}  # key is pub key or dvm name, value is pub key

        for pub_key in dvm_pub_keys:
            dvm_pub_keys_and_names[pub_key] = pub_key
            dvm_pub_keys_and_names[helpers.hex_to_npub(pub_key)] = pub_key
            if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
                dvm_pub_keys_and_names[dvm_nip89_profiles[pub_key]["name"]] = pub_key

        context["dvm_pub_keys_and_names"] = dvm_pub_keys_and_names

        template = loader.get_template("monitor/dvm.html")
        return HttpResponse(template.render(context, request))

    # get profile information for this dvm
    # check to see if there is a nip89 profile, if so grab the latest one
    dvm_nip89_profile_latest = db.events.find_one(
        {"kind": 31990, "pubkey": pub_key},
        sort=[("created_at", -1)],
    )

    if dvm_nip89_profile_latest is not None:
        context["dvm_nip89_profile"] = json.loads(dvm_nip89_profile_latest["content"])

    # get all events from this dvm_pub_key
    dvm_events = list(db.events.find({"pubkey": pub_key}))

    memory_usage = sys.getsizeof(dvm_events)
    print(f"Memory usage of dvm_events: {memory_usage}")

    num_dvm_events = len(dvm_events)

    # compute that number of events per day for the last 30 days
    # get the current time
    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    num_events_per_day = {}

    for day_i in range(30):
        day_start = Timestamp.from_secs(current_secs - (day_i * 24 * 60 * 60))
        day_end = Timestamp.from_secs(current_secs - ((day_i - 1) * 24 * 60 * 60))
        num_events_day_i = db.events.count_documents(
            {
                "pubkey": pub_key,
                "created_at": {"$gte": day_start.as_secs(), "$lt": day_end.as_secs()},
            }
        )

        date_from_day_i = datetime.fromtimestamp(day_start.as_secs()).strftime(
            "%Y-%m-%d"
        )

        num_events_per_day[date_from_day_i] = num_events_day_i
        # print(f"Day {day_i} has {num_events_day_i} events")

    context["num_dvm_events"] = num_dvm_events
    context["dvm_pub_key"] = pub_key
    context["num_events_per_day"] = num_events_per_day

    template = loader.get_template("monitor/dvm.html")
    return HttpResponse(template.render(context, request))

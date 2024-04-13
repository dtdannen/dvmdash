from django.shortcuts import render
from pymongo import MongoClient
import os
import dotenv
from pathlib import Path
from django.shortcuts import HttpResponse, redirect
from django.template import loader
from nostr_sdk import Timestamp

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

    all_dvm_events = [doc for doc in all_dvm_events_cursor]
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

    context["num_dvm_kinds"] = len(list(kinds_counts.keys()))
    context["num_dvm_feedback_kinds"] = len(list(kind_feedback_counts.keys()))
    context["zap_counts"] = zap_counts
    context["dm_counts"] = dm_counts
    context["uncategorized_counts"] = uncategorized_counts
    context["kinds_counts"] = kinds_counts
    context["kind_feedback_counts"] = kind_feedback_counts
    context["num_dvm_events"] = num_dvm_events
    context["dvm_job_results"] = {k: v for k, v in dvm_job_results.items() if v > 100}
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
    context["dvm_job_requests"] = top_dvm_job_requests_dict

    for kind, count in kinds_counts.items():
        print(f"\tKind {kind} has {count} instances")

    print(f"Setting var num_dvm_kinds to {context['num_dvm_kinds']}")

    template = loader.get_template("monitor/overview.html")
    return HttpResponse(template.render(context, request))

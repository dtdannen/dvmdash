from django.shortcuts import render
from pymongo import MongoClient
import os
import dotenv
from pathlib import Path
from django.shortcuts import HttpResponse, redirect
from django.template import loader

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
    num_dvm_events = db.events.count_documents({})
    context["num_dvm_events"] = num_dvm_events
    print(f"Setting num_dvm_events to {num_dvm_events}")
    # get the number of unique kinds of all events
    # # TODO - use a proper mongo query here
    # all_dvm_events_cursor = db.events.find({})
    #
    # all_dvm_events = [doc for doc in all_dvm_events_cursor]
    # kinds_counts = {}
    # for dvm_event_i in all_dvm_events:
    #     if "kind" in dvm_event_i:
    #         kind_num = dvm_event_i["kind"]
    #         if kind_num in kinds_counts:
    #             kinds_counts[kind_num] += 1
    #         else:
    #             kinds_counts[kind_num] = 1
    #     else:
    #         print("WARNING - event missing kind field")
    #         print(f"{dvm_event_i}")
    #
    # context["num_dvm_kinds"] = len(list(kinds_counts.keys()))
    # context["kinds_counts"] = kinds_counts
    #
    # for kind, count in kinds_counts.items():
    #     print(f"\tKind {kind} has {count} instances")
    #
    # print(f"Setting num_dvm_kinds to {context['num_dvm_kinds']}")

    context["num_dvm_kinds"] = []
    context["kinds_counts"] = {}

    template = loader.get_template("monitor/overview.html")
    return HttpResponse(template.render(context, request))

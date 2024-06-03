from django.shortcuts import render
from pymongo import MongoClient
import os
import sys
import dotenv
from pathlib import Path
from django.shortcuts import HttpResponse, redirect
from django.template import loader
from django.http import HttpResponseNotFound, JsonResponse
from django.utils.timesince import timesince
from django.utils import timezone
from nostr_sdk import Timestamp
from datetime import datetime
import json
import monitor.helpers as helpers
from bson import json_util
from django.utils.safestring import mark_safe
from .neo4j_service import neo4j_service
from general.dvm import EventKind


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
    all_dvm_events_cursor = db.events.find(
        {"kind": {"$gte": 5000, "$lte": 6999, "$nin": EventKind.get_bad_dvm_kinds()}}
    )
    all_dvm_events = list(all_dvm_events_cursor)

    # print the memory usages of all events so far:
    memory_usage = sys.getsizeof(all_dvm_events)
    # Convert memory usage to megabytes
    memory_usage_mb = memory_usage / (1024 * 1024)
    print(f"Memory usage of all_dvm_events: {memory_usage_mb:.2f} MB")

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

    request_kinds_counts = {}
    response_kinds_counts = {}
    zap_counts = 0
    dm_counts = 0
    uncategorized_counts = 0
    num_dvm_request_events = 0
    num_dvm_response_events = 0

    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_time_24hr = Timestamp.from_secs(current_secs - (24 * 60 * 60))
    max_time_1week = Timestamp.from_secs(current_secs - (7 * 24 * 60 * 60))

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_tasks_24h = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    context["num_dvm_tasks_24h"] = dvm_tasks_24h

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_results_24h = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 6000, "$lte": 6999},
        }
    )
    context["num_dvm_results_24h"] = dvm_results_24h

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_tasks_1week = db.events.count_documents(
        {
            "created_at": {"$gte": max_time_1week.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    context["num_dvm_tasks_1week"] = dvm_tasks_1week

    # TODO - alter this to make sure bad dvm kinds are ignored
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

            if (
                5000 <= kind_num <= 5999
                and kind_num not in EventKind.get_bad_dvm_kinds()
            ):
                num_dvm_request_events += 1
                if kind_num in request_kinds_counts:
                    request_kinds_counts[kind_num] += 1
                else:
                    request_kinds_counts[kind_num] = 1

                dvm_request_pub_key = dvm_event_i["pubkey"]
                if dvm_request_pub_key in dvm_job_requests:
                    dvm_job_requests[dvm_request_pub_key] += 1
                else:
                    dvm_job_requests[dvm_request_pub_key] = 1

            elif (
                6000 <= kind_num <= 6999
                and kind_num not in EventKind.get_bad_dvm_kinds()
            ):
                num_dvm_response_events += 1
                if kind_num in response_kinds_counts:
                    response_kinds_counts[kind_num] += 1
                else:
                    response_kinds_counts[kind_num] = 1

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

    # this is used to make the bars and labels of the graphs clickable to go to the corresponding dvm page
    labels_to_pubkeys = {}

    # replace dvm_job_results keys with names if available
    dvm_job_results_names = {}
    for pub_key, count in dvm_job_results.items():
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            dvm_job_results_names[dvm_nip89_profiles[pub_key]["name"]] = count
            labels_to_pubkeys[dvm_nip89_profiles[pub_key]["name"]] = pub_key
        else:
            dvm_job_results_names[pub_key[:6]] = count
            labels_to_pubkeys[pub_key[:6]] = pub_key

    context["num_dvm_kinds"] = len(list(request_kinds_counts.keys()))
    context["num_dvm_feedback_kinds"] = len(list(response_kinds_counts.keys()))
    context["zap_counts"] = zap_counts
    context["dm_counts"] = dm_counts
    context["uncategorized_counts"] = uncategorized_counts
    context["num_dvm_request_kinds"] = len(
        [
            k
            for k in list(request_kinds_counts.keys())
            if k not in EventKind.get_bad_dvm_kinds()
        ]
    )
    context["num_dvm_response_kinds"] = len(
        [
            k
            for k in list(response_kinds_counts.keys())
            if k not in EventKind.get_bad_dvm_kinds()
        ]
    )
    context["request_kinds_counts"] = request_kinds_counts
    context["response_kinds_counts"] = response_kinds_counts
    context["num_dvm_request_events"] = num_dvm_request_events
    context["num_dvm_response_events"] = num_dvm_response_events
    context["dvm_job_results"] = {
        k: v for k, v in dvm_job_results_names.items() if v > 100
    }
    context["dvm_pub_keys"] = len(list(dvm_job_results.keys()))
    context["dvm_nip_89s"] = len(list(dvm_nip89_profiles.keys()))

    most_popular_dvm_npub = max(dvm_job_results, key=dvm_job_results.get)
    if (
        most_popular_dvm_npub in dvm_nip89_profiles
        and "name" in dvm_nip89_profiles[most_popular_dvm_npub]
    ):
        context["most_popular_dvm"] = dvm_nip89_profiles[most_popular_dvm_npub]["name"]

    context["most_popular_kind"] = max(
        request_kinds_counts, key=request_kinds_counts.get
    )

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
            labels_to_pubkeys[dvm_nip89_profiles[pub_key]["name"]] = pub_key
        else:
            top_dvm_job_requests_via_name[pub_key[:6]] = count
            labels_to_pubkeys[pub_key[:6]] = pub_key

    context["dvm_job_requests"] = top_dvm_job_requests_via_name
    context["labels_to_pubkeys"] = json.dumps(labels_to_pubkeys).replace("'", "")

    for kind, count in request_kinds_counts.items():
        print(f"\tKind {kind} has {count} instances")

    print(f"Setting var num_dvm_kinds to {context['num_dvm_kinds']}")

    template = loader.get_template("monitor/overview.html")
    return HttpResponse(template.render(context, request))


def dvm(request, pub_key=""):
    print(f"Calling dvm with dvm_pub_key: {pub_key}")
    context = {}

    if pub_key == "":
        # get all dvm pub keys
        # TODO - update this to ignore bad dvm event kinds
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

    context["num_dvm_events"] = num_dvm_events
    context["dvm_pub_key"] = pub_key
    context["num_events_per_day"] = num_events_per_day

    template = loader.get_template("monitor/dvm.html")
    return HttpResponse(template.render(context, request))


def kind(request, kind_num=""):
    print(f"Calling kind with kind_num: {kind_num}")
    context = {}

    if kind_num == "":
        # get all kinds
        kinds = list(db.events.distinct("kind"))

        context["kinds"] = kinds

        template = loader.get_template("monitor/kind.html")
        return HttpResponse(template.render(context, request))

    # get all events of this kind
    kind_events = list(db.events.find({"kind": int(kind_num)}))

    # get all unique dvms that have this kind of event, and get the counts for number of events per dvm
    # TODO - fix this
    # dvm_pub_keys = list(db.events.distinct("pubkey", {"kind": int(kind_num)}))

    memory_usage = sys.getsizeof(kind_events)
    print(f"Memory usage of kind_events: {memory_usage}")

    num_kind_events = len(kind_events)

    context["kind"] = kind_num
    context["num_kind_events"] = num_kind_events
    context["kind_num"] = kind_num

    template = loader.get_template("monitor/kind.html")
    return HttpResponse(template.render(context, request))


def see_event(request, event_id=""):
    print(f"Calling see_event with event_id: {event_id}")
    context = {}

    if event_id == "":
        # show a 404 page with a link back to the homepage
        template = loader.get_template("monitor/404.html")
        context[
            "message"
        ] = f"You have given a blank event ID. Please go back or go back to the homepage."
        return HttpResponseNotFound(template.render(context, request))

    # get the event with this id
    event = db.events.find_one({"id": event_id})

    if not event:
        # If no event is found, show a 404 page
        template = loader.get_template("monitor/404.html")
        context["message"] = f"Event with ID {event_id} was not found in our database."
        return HttpResponseNotFound(template.render(context, request))

    # Remove the '_id' field from the event dictionary
    event.pop("_id", None)

    # Convert the event to a JSON string using json_util to handle ObjectId
    # and process tags to convert 'p' tags to links
    event_str = json_util.dumps(event, indent=2)

    # Process the JSON string to convert 'p' tags to links
    event_data = json.loads(event_str)
    for tag in event_data.get("tags", []):
        if tag[0] == "e":
            tag[1] = f'<a href="/event/{tag[1]}/">{tag[1]}</a>'
        elif tag[0] == "p":
            tag[1] = f'<a href="/npub/{tag[1]}/">{tag[1]}</a>'
        elif tag[0] == "request":
            request_data = tag[1]
            print("Raw request data: ", request_data)
            request_as_json = json.loads(request_data)

            print(f"Request as json: {request_as_json}")

            if "kind" in request_as_json:
                request_as_json[
                    "kind"
                ] = f'<a href="/kind/{request_as_json["kind"]}/">{request_as_json["kind"]}</a>'

            if "id" in request_as_json:
                request_as_json[
                    "id"
                ] = f'<a href="/event/{request_as_json["id"]}/">{request_as_json["id"]}</a>'

            if "pubkey" in request_as_json:
                request_as_json[
                    "pubkey"
                ] = f'<a href="/npub/{request_as_json["pubkey"]}/">{request_as_json["pubkey"]}</a>'

            for sub_tag in request_as_json.get("tags", []):
                if sub_tag[0] == "e":
                    sub_tag[1] = f'<a href="/event/{sub_tag[1]}/">{sub_tag[1]}</a>'
                elif sub_tag[0] == "p":
                    sub_tag[1] = f'<a href="/npub/{sub_tag[1]}/">{sub_tag[1]}</a>'

            tag[1] = tag[1] = mark_safe(json.dumps(request_as_json, indent=8))

    if "pubkey" in event_data:
        event_data[
            "pubkey"
        ] = f'<a href="/npub/{event_data["pubkey"]}/">{event_data["pubkey"]}</a>'

        # event_data["request"] = request_as_json

    # Humanize the created_at timestamp
    created_at = datetime.fromtimestamp(event_data.get("created_at"))
    created_at_aware = timezone.make_aware(created_at, timezone.get_current_timezone())
    humanized_date = timesince(created_at_aware, timezone.now())

    # Add a description to the context
    context["event_description"] = (
        f"This is a KIND {event_data.get('kind')} event "
        f"created on {created_at_aware.strftime('%Y-%m-%d %H:%M:%S')} ({humanized_date} ago)."
    )

    # Convert the processed data back to a JSON string
    context["event"] = (
        json.dumps(event_data, indent=2).replace('\\"', '"').replace("\\n", "\n")
    )

    template = loader.get_template("monitor/event.html")
    return HttpResponse(template.render(context, request))


def see_npub(request, npub=""):
    print(f"Calling see_npub with npub: {npub}")
    context = {}

    if npub == "":
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render({"message": "Sorry, no npub was provided."}, request)
        )

    # see if we can get a nip-89 profile for this npub
    nip89_profile = db.events.find_one({"kind": 31990, "pubkey": npub})
    if nip89_profile:
        print("About to redirect with pub_key: ", npub)
        return redirect("dvm_with_pub_key", pub_key=npub)

    context["npub"] = npub

    # get the npub details (assuming `db.events` is your collection for npub data)
    npub_data_cursor = (
        db.events.find({"pubkey": npub}).sort("created_at", -1).limit(20)
    )  # -1 for descending order, limit to 20

    if not npub_data_cursor:
        # If no npub is found, show a 404 page with a custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {"message": "Sorry, this npub isn't in our database."}, request
            )
        )

    npub_data = list(npub_data_cursor)  # Convert the cursor to a list

    # Process the event data to include human-readable timestamps
    for event in npub_data:
        if isinstance(event["created_at"], (int, float)):
            event["created_at"] = datetime.fromtimestamp(event["created_at"])

    context["npub_events"] = npub_data

    template = loader.get_template("monitor/npub.html")
    return HttpResponse(template.render(context, request))


def recent(request):
    context = {}
    recent_requests = list(
        db.events.find(
            {
                "kind": {
                    "$gte": 5000,
                    "$lte": 5999,
                    "$nin": EventKind.get_bad_dvm_kinds(),
                }
            }
        )
        .limit(1000)
        .sort("created_at", -1)
    )

    print(f"Found {len(recent_requests)} recent requests")

    # recent requests per kind
    recent_requests_per_kind = {}
    recent_request_events = []
    kinds_already_filled = []  # make it faster
    for request_event in recent_requests:
        kind = request_event["kind"]
        if kind in kinds_already_filled:
            continue

        # make it readable on the frontend
        request_event["created_at"] = datetime.fromtimestamp(
            request_event["created_at"]
        )

        if kind in recent_requests_per_kind:
            if recent_requests_per_kind[kind] < 2:
                recent_requests_per_kind[kind] += 1
                recent_request_events.append(request_event)
            else:
                kinds_already_filled.append(kind)
        else:
            recent_requests_per_kind[kind] = 1
            recent_request_events.append(request_event)

    print(f"Found {len(recent_request_events)} recent requests (filtered)")

    # Convert the result to a list of dictionaries
    context["recent_dvm_events"] = recent_request_events

    print(f"context['recent_dvm_events'][0] = {context['recent_dvm_events'][0]}")

    template = loader.get_template("monitor/recent.html")
    return HttpResponse(template.render(context, request))


def debug(request, event_id=""):
    context = {}

    if event_id == "":
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render({"message": "Sorry, no event ID was provided."}, request)
        )

    # get the event with this id
    event = list(db.events.find_one({"id": event_id}))[0]

    if "kind" in event and event["kind"] not in [5000, 5999]:
        # show a 404 page with a link back to the homepage and custom message
        print(f"Event kind {event['kind']} is not supported for debugging")
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {
                    "message": "Sorry, only DVM requests in the range 5000-5999 are supported for now"
                },
                request,
            )
        )

    context["event_id"] = event["id"]

    # now call neo 4j to get the graph data

    template = loader.get_template("monitor/debug.html")
    return HttpResponse(template.render(context, request))


def custom_404(
    request,
    exception=None,
    message="Sorry, the page you are looking for does not exist.",
):
    context = {"message": message}
    return render(request, "monitor/404.html", context, status=404)


def get_graph_data(request):
    """
    Note this is for the api endpoint /graph/ for neoviz.js, not to render a django template
    """
    query = "MATCH p=()-[:CREATED_FOR]->() RETURN p LIMIT 25"
    data = neo4j_service.run_query(query)
    return JsonResponse(data, safe=False)

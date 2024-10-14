import time

from django.shortcuts import render
from pymongo import MongoClient, DESCENDING
import os
import sys
import ast
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
from shared.dvm import EventKind
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


if os.getenv("USE_MONGITA", "False") != "False":  # use a local mongo db, like sqlite
    print("Using mongita")
    from mongita import MongitaClientDisk

    mongo_client = MongitaClientDisk()
    db = mongo_client.dvmdash
    print("Connected to local mongo db using MONGITA")
else:
    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"))
    db = mongo_client["dvmdash"]

    try:
        result = db["prod_events"].count_documents({})
        print(f"There are {result} documents in prod_events collection")
    except Exception as e:
        print("Could not count documents in db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo db")


def metrics(request):
    # get the latest stats doc from the stats collection
    most_recent_stats = db.global_stats.find_one(sort=[("timestamp", -1)])

    try:
        latest_timestamp = most_recent_stats["timestamp"]

        # get all the stats on all the dvms
        pipeline = [
            # Match documents with the latest timestamp
            {"$match": {"timestamp": latest_timestamp}},
            # Sort by number of jobs completed in descending order
            {"$sort": {"number_jobs_completed": -1}},
        ]

        # Execute the aggregation pipeline
        dvm_docs = list(db.dvm_stats.aggregate(pipeline))

        most_popular_dvm = dvm_docs[0]

        if "profile" in most_popular_dvm and "name" in most_popular_dvm["profile"]:
            most_recent_stats["most_popular_dvm_name"] = most_popular_dvm["profile"][
                "name"
            ]
        else:
            most_recent_stats["most_popular_dvm_name"] = most_popular_dvm["metadata"][
                "dvm_npub_hex"
            ]

        if len(most_recent_stats["most_popular_dvm_name"]) > 50:
            most_recent_stats["most_popular_dvm_name"] = (
                most_recent_stats["most_popular_dvm_name"][:10]
                + "..."
                + most_recent_stats["most_popular_dvm_name"][-10:]
            )

        most_recent_stats["most_popular_dvm_npub"] = most_popular_dvm["metadata"][
            "dvm_npub_hex"
        ]

    except Exception as e:
        logger.warning(f"Could not get dvm stats from db: {e}")
        pass

    template = loader.get_template("monitor/metrics.html")
    return HttpResponse(template.render(most_recent_stats, request))


def dvm(request, pub_key=""):
    print(f"Calling dvm with dvm_pub_key: {pub_key}")
    context = {}

    # Get the most recent global stats document
    try:
        global_stats_doc = db.global_stats.find_one(sort=[("timestamp", DESCENDING)])
        if global_stats_doc:
            latest_timestamp = global_stats_doc["timestamp"]
            logger.warning(
                f"Got a latest_timestamp from global_stats of {latest_timestamp}"
            )
        else:
            raise ValueError("No global stats document found")
    except Exception as e:
        logger.error(
            f"Failed to get latest_timestamp from global stats, error: {str(e)}"
        )
        logger.error(traceback.format_exc())
        return HttpResponse(
            "Apologies, you have found a bug, "
            "would you mind sending an email to dustin@dvmdash.live and include the current url?"
            " This will help us fix it asap.",
            status=500,
        )

    # get all the stats on all the dvms
    pipeline = [
        # Match documents with the latest timestamp
        {"$match": {"timestamp": latest_timestamp}},
        # Sort by number of jobs completed in descending order
        {"$sort": {"number_jobs_completed": -1}},
    ]

    # Execute the aggregation pipeline
    dvm_docs = list(db.dvm_stats.aggregate(pipeline))

    context["dvm_stat_docs"] = dvm_docs

    if len(pub_key) > 0:
        print(f"len of pub_key is: {len(pub_key)}")
        dvm_events = list(
            db.prod_events.find({"pubkey": pub_key}).sort("created_at", -1).limit(100)
        )

        # compute the number of results
        memory_usage = sys.getsizeof(dvm_events)
        print(f"Memory usage of dvm_events: {memory_usage}")

        # Convert Unix timestamps to datetime objects
        for event in dvm_events:
            event["created_at"] = timezone.make_aware(
                datetime.fromtimestamp(int(event["created_at"]))
            )
            if "kind" in event and 6000 <= event["kind"] <= 7000:
                if "tags" in event:
                    for tag in event["tags"]:
                        if tag[0] == "e":
                            event["debug_event_id"] = tag[1]
                            break
            if "debug_event_id" not in event:
                event["debug_event_id"] = "Missing 'e' tag"

        context["dvm_pub_key"] = pub_key
        context["recent_dvm_events"] = dvm_events
        most_recent_stats = None
        try:
            for dvm_stat in dvm_docs:
                dvm_doc_metadata = dvm_stat["metadata"]
                dvm_doc_pub_key_hex = dvm_doc_metadata["dvm_npub_hex"]
                if dvm_doc_pub_key_hex == pub_key:
                    most_recent_stats = dvm_stat
                    break

            if most_recent_stats:
                context.update(most_recent_stats)
        except:
            print(f"Could not find pub_key {pub_key} in recent dvm_stats")

    template = loader.get_template("monitor/dvm.html")
    return HttpResponse(template.render(context, request))


def kind(request, kind_num=""):
    print(f"Calling kind with kind_num: {kind_num}")
    context = {}

    # Get the most recent global stats document
    try:
        global_stats_doc = db.global_stats.find_one(sort=[("timestamp", DESCENDING)])
        if global_stats_doc:
            latest_timestamp = global_stats_doc["timestamp"]
            logger.warning(
                f"Got a latest_timestamp from global_stats of {latest_timestamp}"
            )
        else:
            raise ValueError("No global stats document found")
    except Exception as e:
        logger.error(
            f"Failed to get latest_timestamp from global stats, error: {str(e)}"
        )
        logger.error(traceback.format_exc())
        return HttpResponse(
            "Apologies, you have found a bug, "
            "would you mind sending an email to dustin@dvmdash.live and include the current url?"
            " This will help us fix it asap.",
            status=500,
        )

    pipeline = [
        # Match documents with the latest timestamp
        {"$match": {"timestamp": latest_timestamp}},
        # Sort by number of jobs completed in descending order
        {"$sort": {"total_jobs_requested": -1}},
    ]

    # Execute the aggregation pipeline
    kind_stat_docs = list(db.kind_stats.aggregate(pipeline))

    context["kind_stat_docs"] = kind_stat_docs
    context["kinds"] = [doc["metadata"]["kind_number"] for doc in kind_stat_docs]

    if len(kind_num) > 0:
        # load the data for this specific kind
        kind_num = int(kind_num)

        if 6000 <= kind_num <= 6999:
            kind_num = kind_num - 1000

        context["kind"] = kind_num

        most_recent_stats = None
        try:
            for kind_stat in kind_stat_docs:
                kind_stat_metadata = kind_stat["metadata"]
                kind_num_in_doc = kind_stat_metadata["kind_number"]
                if kind_num == kind_num_in_doc:
                    most_recent_stats = kind_stat
                    break

            if most_recent_stats:
                # Sort data_per_dvm by jobs_performed
                if "data_per_dvm" in most_recent_stats:
                    sorted_data_per_dvm = sorted(
                        most_recent_stats["data_per_dvm"].items(),
                        key=lambda x: x[1]["jobs_performed"],
                        reverse=True,
                    )
                    most_recent_stats[
                        "sorted_data_per_dvm"
                    ] = sorted_data_per_dvm  # New key for sorted data

                context.update(most_recent_stats)
        except:
            print(f"Could not find pub_key {kind_num} in recent dvm_stats")

        context.update(most_recent_stats)

        # get most recent events
        recent_events = list(
            db.prod_events.find({"kind": int(kind_num)})
            .sort("created_at", -1)
            .limit(100)
        )

        # compute the number of results
        memory_usage = sys.getsizeof(recent_events)
        print(f"Memory usage of dvm_events: {memory_usage}")

        # Convert Unix timestamps to datetime objects
        for event in recent_events:
            event["created_at"] = timezone.make_aware(
                datetime.fromtimestamp(int(event["created_at"]))
            )

        context["recent_events"] = recent_events

        print(f"recent_events has {len(recent_events)}")

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
    event = db.prod_events.find_one({"id": event_id})

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

    debug_event_id = None

    kind_num = None
    if "kind" in event_data:
        kind_num = event_data["kind"]
        if 6000 <= kind_num <= 6999:
            event_data["kind"] = f'<a href="/kind/{kind_num-1000}">{kind_num}</a>'
        elif 5000 <= kind_num <= 5999:
            event_data["kind"] = f'<a href="/kind/{kind_num}">{kind_num}</a>'
            debug_event_id = event_data["id"]
        else:
            # we don't have any page for a kind number outside 5000-6999
            pass

    for tag in event_data.get("tags", []):
        if tag[0] == "e":
            if 6000 <= kind_num <= 7000:
                debug_event_id = tag[1]
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
        if 6000 <= kind_num <= 7000:
            event_data[
                "pubkey"
            ] = f'<a href="/dvm/{event_data["pubkey"]}/">{event_data["pubkey"]}</a>'
        else:
            event_data[
                "pubkey"
            ] = f'<a href="/npub/{event_data["pubkey"]}/">{event_data["pubkey"]}</a>'

        # event_data["request"] = request_as_json

    # Humanize the created_at timestamp
    created_at = datetime.fromtimestamp(event_data.get("created_at"))
    created_at_aware = timezone.make_aware(created_at, timezone.get_current_timezone())
    humanized_date = timesince(created_at_aware, timezone.now())

    created_at_aware_formatted = created_at_aware.strftime("%Y-%m-%d %H:%M:%S")

    # Add a description to the context
    context["event_description"] = (
        f"This is a KIND {kind_num} event "
        f"created on {created_at_aware_formatted} ({humanized_date} ago)."
    )

    context["debug_event_id"] = debug_event_id

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
    nip89_profile = db.prod_events.find_one({"kind": 31990, "pubkey": npub})
    if nip89_profile:
        print("About to redirect with pub_key: ", npub)
        return redirect("dvm_with_pub_key", pub_key=npub)

    context["npub"] = npub

    # get the npub details (assuming `db.events` is your collection for npub data)
    npub_data_cursor = (
        db.prod_events.find({"pubkey": npub}).sort("created_at", -1).limit(20)
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
    num_events_to_lookback = 2000
    num_events_to_show_per_kind = 3
    context = {}
    recent_requests = list(
        db.prod_events.find(
            {
                "kind": {
                    "$gte": 5000,
                    "$lte": 5999,
                    "$nin": EventKind.get_bad_dvm_kinds(),
                }
            }
        )
        .limit(num_events_to_lookback)
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
            if recent_requests_per_kind[kind] < num_events_to_show_per_kind:
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
        num_events_to_lookback = 200
        recent_events = list(
            db.prod_events.find(
                {
                    "kind": {
                        "$gte": 5000,
                        "$lte": 7000,
                        "$nin": EventKind.get_bad_dvm_kinds(),
                    }
                }
            )
            .limit(num_events_to_lookback)
            .sort("created_at", -1)
        )

        for recent_event in recent_events:
            # make it readable on the frontend
            recent_event["created_at"] = datetime.fromtimestamp(
                recent_event["created_at"]
            )
            if "kind" in recent_event and 6000 <= recent_event["kind"] <= 7000:
                if "tags" in recent_event:
                    for tag in recent_event["tags"]:
                        if tag[0] == "e":
                            recent_event["debug_event_id"] = tag[1]
                            break
            else:
                recent_event["debug_event_id"] = recent_event["id"]

        context["recent_events"] = recent_events

        template = loader.get_template("monitor/debug.html")
        return HttpResponse(template.render(context, request))

    # get the event with this id
    event = None
    events = list(db.prod_events.find({"id": event_id}))
    # print(f"events are {events}")
    if events:
        event = events[0]

    if not event:
        # show a 404 page with a link back to the homepage and custom message
        template = loader.get_template("monitor/404.html")
        return HttpResponseNotFound(
            template.render(
                {"message": f"Event with ID {event_id} was not found in our database."},
                request,
            )
        )

    if "kind" in event and event["kind"] not in list(range(5000, 6000)):
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

    template = loader.get_template("monitor/debug.html")
    return HttpResponse(template.render(context, request))


def about(request):
    context = {}
    template = loader.get_template("monitor/about.html")
    return HttpResponse(template.render(context, request))


def custom_404(
    request,
    exception=None,
    message="Sorry, the page you are looking for does not exist.",
):
    context = {"message": message}
    return render(request, "monitor/404.html", context, status=404)


def custom_500(request):
    return render(request, "monitor/500.html", status=500)


def _get_row_data_from_event_dict(event_dict):
    """
    Helper function to parse results from neo4j

    Adds a 'quick_details' field to the event_dict if it doesn't already exist

    Returns the event id followed by the full event
    """

    if "id" not in event_dict:
        return None, event_dict

    already_processed_quick_details = False

    if "Encrypted" in event_dict["labels"]:
        already_processed_quick_details = True
        event_dict["quick_details"] = "This an encrypted event"

    # if the kind is 7000, use the status field
    if (
        not already_processed_quick_details
        and "kind" in event_dict
        and event_dict["kind"] == 7000
    ):
        tags_str = event_dict["tags"]
        try:
            tags = ast.literal_eval(tags_str)
            for tag in tags:
                # print(f"Looking at tag: {tag}")
                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "status":
                    event_dict["quick_details"] = "status: " + tag[-1]
                    already_processed_quick_details = True
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {event_dict['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one
            pass

    # use "content" field if it exists
    if not already_processed_quick_details:
        if "content" in event_dict and len(event_dict["content"]) > 0:
            event_dict["quick_details"] = event_dict["content"]
            already_processed_quick_details = True

    # as a last resort, try the 'i' tag
    if not already_processed_quick_details and "tags" in event_dict:
        tags_str = event_dict["tags"]
        try:
            tags = ast.literal_eval(tags_str)
            for tag in tags:
                # print(f"Looking at tag: {tag}")
                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "i":
                    event_dict["quick_details"] = tag[1]
                    already_processed_quick_details = True
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {event_dict['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one
            pass

    # if no 'i' tag or 'content', try the 'alt' tag
    if not already_processed_quick_details and "tags" in event_dict:
        tags_str = event_dict["tags"]
        try:
            tags = ast.literal_eval(tags_str)
            for tag in tags:
                if isinstance(tag, list) and len(tag) >= 2 and tag[0] == "alt":
                    event_dict["quick_details"] = tag[1]
                    already_processed_quick_details = True
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {event_dict['id']}")
            pass

    # for invoices, use a message with the amount and a clickable lighting invoice for quick details
    if (
        not already_processed_quick_details
        and "amount" in event_dict
        and "Invoice" in event_dict["labels"]
        and "creator_pubkey" in event_dict
    ):
        amount_millisats = int(event_dict["amount"])
        invoice_str = event_dict["id"]
        creator_pubkey_str = event_dict["creator_pubkey"]
        event_dict["pubkey"] = creator_pubkey_str

        event_dict[
            "quick_details"
        ] = f'Invoice for {amount_millisats / 1000 :.2f} sats (<a href="lightning:${invoice_str}">Click to Pay</a>)'
        already_processed_quick_details = True

    if already_processed_quick_details:
        # check to see if the value is a link and if so, make a url
        if event_dict["quick_details"].startswith("http"):
            event_dict[
                "quick_details"
            ] = f'<a href="{event_dict["quick_details"]}">Link</a>'

    # if the quick_details get too big, cut them
    if "quick_details" in event_dict and len(event_dict["quick_details"]) > 200:
        event_dict["quick_details"] = (
            event_dict["quick_details"][:50]
            + "......"
            + event_dict["quick_details"][-50:]
        )

    return event_dict["id"], event_dict


def get_graph_data(request, request_event_id=""):
    """
    Note this is for the api endpoint /graph/ for neoviz.js, not to render a django template
    """
    logger.warning(f"get_graph_data called with request_event_id: {request_event_id}")
    # Log connection details (be careful not to log sensitive information)
    # Log the type of AUTH, not its contents

    query = """
        MATCH (req:Event {id: $request_event_id})
        OPTIONAL MATCH path = (n)-[r*]->(req)
        UNWIND relationships(path) AS rel
        RETURN 
          {
            startNode: {
              labels: labels(startNode(rel)),
              properties: properties(startNode(rel))
            },
            relationship: {
              type: type(rel),
              properties: properties(rel)
            },
            endNode: {
              labels: labels(endNode(rel)),
              properties: properties(endNode(rel))
            }
          } AS relationData, req
    """
    new_query = query.replace("$request_event_id", f"'{request_event_id}'")
    logger.warning(f"Querying neo4j with query: {new_query}")
    # logger.warning(f"Actual query sent to neo4j is still: {query}")

    params = {"request_event_id": request_event_id}

    try:
        start_time = time.time()
        data = neo4j_service.run_query(query, params)
        end_time = time.time()
        logger.warning(f"Query execution time: {end_time - start_time} seconds")
        # logger.warning(f"data from neo4j is {data} ")
    except Exception as e:
        logger.error(f"Error running Neo4j query: {str(e)}")
        return JsonResponse({"error": "Database query failed"}, status=500)

    if not data:
        logger.warning("No data returned from Neo4j query")
        return JsonResponse({"error": "No data found"}, status=404)

    node_relations = []
    event_nodes = {}

    original_request_node = None

    for record in data:
        if "req" not in record:
            logger.warning(f"'req' not in record: {record}")
            continue

        if original_request_node is None:
            original_request_node = record["req"]

            if "labels" not in original_request_node:
                original_request_node["labels"] = ["DVMRequest"]

            # Process the req node
            req_event_id, req_event_data = _get_row_data_from_event_dict(
                original_request_node
            )

            if req_event_id not in event_nodes:
                event_nodes[req_event_id] = req_event_data

        # Process related nodes
        relation_data = record["relationData"]
        relationship = relation_data["relationship"]["type"]
        start_node = relation_data["startNode"]
        end_node = relation_data["endNode"]

        start_node_final = start_node["properties"]
        start_node_final["labels"] = start_node["labels"]

        end_node_final = end_node["properties"]
        end_node_final["labels"] = end_node["labels"]

        start_node_id, start_node_data = _get_row_data_from_event_dict(start_node_final)
        end_node_id, end_node_data = _get_row_data_from_event_dict(end_node_final)

        if start_node_id not in event_nodes:
            event_nodes[start_node_id] = start_node_data

        if end_node_id not in event_nodes:
            event_nodes[end_node_id] = end_node_data

        node_relations.append(
            {
                "source_node": start_node_data,
                "target_node": end_node_data,
                "relation": relationship,
            }
        )

    response_data = {
        "data": data,
        "event_nodes": list(event_nodes.values()),
        "node_relations": node_relations,
    }

    logger.warning(
        f"Processed {len(event_nodes)} event nodes and {len(node_relations)} relations"
    )
    logger.warning(f"Response data size: {len(str(response_data))} bytes")

    return JsonResponse(response_data, safe=False)


def playground(request):
    context = {}
    template = loader.get_template("monitor/playground.html")
    return HttpResponse(template.render(context, request))

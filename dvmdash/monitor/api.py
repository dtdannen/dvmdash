from django.shortcuts import HttpResponse
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from pymongo import MongoClient
import os


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
        result = db["events"].count_documents({})
        print(f"There are {result} documents in events collection")
    except Exception as e:
        print("Could not count documents in db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo db")


def get_payment_request_total_metric(request):
    """
    Get the total number, amount, average, median of all payment requests
    """

    query = {
        "kind": 7000,
        "tags": {
            "$all": [["status", "payment-required"]],
        },
    }

    payment_requests = list(db.events.find(query))

    total_number_of_payments_requests = len(payment_requests)
    total_amount_millisats = 0
    average_amount_millisats = 0

    for payment_request in payment_requests:
        try:
            tags = payment_request["tags"]
            for tag in tags:
                if tag[0] == "amount":
                    total_amount_millisats += int(tag[1])
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {payment_request['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one

    if total_number_of_payments_requests > 0:
        average_amount_millisats = (
            total_amount_millisats / total_number_of_payments_requests
        )

    total_amount_sats = total_amount_millisats / 1000
    average_amount_sats = average_amount_millisats / 1000

    print(f"Total number of payment requests: {total_number_of_payments_requests}")
    print(f"Total amount (sats): {total_amount_sats}")
    print(f"Average amount (sats): {average_amount_sats}")

    response_data = {
        "total_number_of_payments_requests": total_number_of_payments_requests,
        "total_amount_sats": total_amount_sats,
        "average_amount_sats": average_amount_sats,
    }

    return response_data


def get_payment_request_total(request):
    data = get_payment_request_total_metric(request)

    print(f"Data: {data}")

    metric = request.GET.get("metric")
    if metric == "total_requests":
        return HttpResponse(
            f"""
            <h5 class="card-title">Total Payment Requests</h5>
            <p class="card-text display-4">{data['total_number_of_payments_requests']}</p>
        """
        )
    elif metric == "total_amount":
        return HttpResponse(
            f"""
            <h5 class="card-title">Total Amount (Sats)</h5>
            <p class="card-text display-4">{data['total_amount_sats']:.2f}</p>
        """
        )
    elif metric == "average_amount":
        return HttpResponse(
            f"""
            <h5 class="card-title">Average Amount (Sats)</h5>
            <p class="card-text display-4">{data['average_amount_sats']:.2f}</p>
        """
        )

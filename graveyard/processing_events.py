"""
Putting code here to bury it, just in case I want to dig it up later
"""

import re
import json


def process_zap_receipts(
    zap_receipts, feedback_event_lnbc_invoice_strs, bolt11_invoice_amount_regex_pattern
):
    missing_invoice = 0
    missing_preimage = 0
    missing_amount = 0
    zap_receipts_to_a_dvm_invoice = 0
    total_amount_paid_millisats = 0
    total_number_of_payment_receipts = 0
    zap_receipts_not_to_a_dvm = 0
    zap_receipts_with_parsing_errors = 0

    for zap_receipt in zap_receipts:
        try:
            tags = zap_receipt["tags"]
            has_bolt11_invoice = False
            bolt11_invoice_str = ""
            amount_millisats = -1
            amount_from_bolt_invoice = -1
            has_preimage = False
            original_feedback_event_id = None
            dvm_authoring_feedback_with_invoice = None

            for tag in tags:
                # check that the tag has a bolt11 invoice
                # print(f"tag is {tag}")
                if tag[0] == "bolt11":
                    if tag[1] in feedback_event_lnbc_invoice_strs:
                        has_bolt11_invoice = True

                        bolt11_invoice_str = tag[1]
                        print("invoice_str", bolt11_invoice_str)

                        # get the amount from the bolt 11 invoice:
                        match = re.search(
                            bolt11_invoice_amount_regex_pattern, bolt11_invoice_str
                        )
                        if match:
                            amount = match.group(1)
                            print(f"amount is {amount}")
                            amount_from_bolt_invoice = int(str(amount))
                            print(
                                f"Amount from bolt invoice: {amount_from_bolt_invoice}"
                            )
                elif tag[0] == "description":
                    # this should point to a new event that is the zap request
                    zap_request = None
                    try:
                        zap_request = json.loads(tag[1], strict=False)
                    except Exception as e:
                        print(f"Failed to parse {tag[1]}")
                        print(f"tag[1]={tag[1]}")
                        if "kind" in tag[1]:
                            print(
                                f"...and that's because it's already been parsed! Kind is {tag[1]['kind']}"
                            )

                    if (
                        bolt11_invoice_str == ""
                        and zap_request
                        and "kind" in zap_request
                    ):
                        # print(f"Originating event has kind {zap_request['kind']}")
                        if zap_request["kind"] == 9734:
                            # this is a zap request
                            # check if the zap request has a bolt11 invoice
                            zap_request_tags = zap_request["tags"]
                            for zap_request_tag in zap_request_tags:
                                if (
                                    zap_request_tag[0] == "amount"
                                    and len(zap_request_tag) > 2
                                ):
                                    print(
                                        f"inner zap request tag has length {len(zap_request_tag)} and is: {zap_request_tag} "
                                    )
                                    amount_millisats = int(zap_request_tag[1])
                                    bolt11_invoice_str = zap_request_tag[2]
                                    print(
                                        "getting invoice from inner description event"
                                    )
                                    break
                elif tag[0] == "preimage":
                    has_preimage = True

            if not has_bolt11_invoice:
                # print(f"Zap receipt {zap_receipt['id']} does not have a bolt11 invoice")
                missing_invoice += 1
                continue

            if not has_preimage:
                # print(f"Zap receipt {zap_receipt['id']} does not have a preimage")
                missing_preimage += 1
                continue

            if amount_millisats < 0 and amount_from_bolt_invoice < 0:
                # print(
                #    f"Zap receipt {zap_receipt['id']} is missing amount or does not have a valid amount"
                # )
                missing_amount += 1
                continue

            # if we get here, we have a valid zap receipt
            print(f"Zap receipt {zap_receipt['id']} has a valid bolt11 invoice")
            if bolt11_invoice_str in feedback_event_lnbc_invoice_strs:
                zap_receipts_to_a_dvm_invoice += 1
                print(f"Zap receipt contains an invoice from a DVM Feedback 7000 event")
                if amount_from_bolt_invoice > 0:
                    total_amount_paid_millisats += amount_from_bolt_invoice * 100
                else:
                    total_amount_paid_millisats += amount_millisats
                total_number_of_payment_receipts += 1
            else:
                zap_receipts_not_to_a_dvm += 1

        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {zap_receipt['id']}: {str(e)}")
            import traceback

            print(f"Traceback: {traceback.format_exc()}")
            # Skip processing tags for this record and continue with the next one
            zap_receipts_with_parsing_errors += 1
        except Exception as e:
            print(f"Error processing zap receipt {zap_receipt['id']}: {str(e)}")
            import traceback

            print(f"Traceback: {traceback.format_exc()}")
            zap_receipts_with_parsing_errors += 1

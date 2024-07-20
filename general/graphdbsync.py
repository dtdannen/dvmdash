import json
import ast
import neo4j
import uuid
from general import helpers
from general.dvm import EventKind
from tqdm import tqdm


class GraphDBSync:
    def __init__(self, db, neo4j_driver, logger=None):
        self.MAX_FIELD_SIZE = 1000  # max size in bytes for any single json field
        self.mongo_db = db
        self.neo4j_driver = neo4j_driver
        self.logger = logger
        self.user_npubs = set()
        self.dvm_npubs = set()
        self.dvm_nip_89_profiles = {}
        self.request_events = {}  # key is event id, value is event
        self.feedback_events = {}  # key is event id, value is event
        self.response_events = {}  # key is event id, value is event
        self.feedback_event_invoices = (
            {}
        )  # key is a feedback event id, value is a json dict of invoice details
        self.invoices = (
            {}
        )  # key is the lnbc string, value is the json data excluding the lnbc string

    def get_all_dvm_nip89_profiles(self):
        """
        Get all DVM NIP-89 profiles from the MongoDB database.
        """
        self.logger.info("Loading DVM NIP-89 profiles from MongoDB...")
        for nip89_event in tqdm(self.mongo_db.events.find({"kind": 31990})):
            if "pubkey" in nip89_event:
                try:
                    self.dvm_nip_89_profiles[nip89_event["pubkey"]] = json.loads(
                        nip89_event["content"]
                    )
                except Exception as e:
                    self.logger.debug(
                        f"Error loading json from {nip89_event['content']}"
                    )
                    pass

    def get_all_dvm_npubs(self):
        self.logger.info("Getting all DVM npubs...")
        for event in tqdm(self.response_events.values()):
            if "pubkey" in event:
                self.dvm_npubs.add(event["pubkey"])

        # get all pub keys from nip-89 profiles
        for dvm_pubkey, profile in self.dvm_nip_89_profiles.items():
            self.dvm_npubs.add(dvm_pubkey)

    def get_all_request_events(self):
        self.logger.info("Getting all request events...")
        request_events_ls = list(
            self.mongo_db.events.find(
                {
                    "kind": {
                        "$gte": 5000,
                        "$lte": 5999,
                        "$nin": EventKind.get_bad_dvm_kinds(),
                    }
                }
            )
        )

        for event in tqdm(request_events_ls):
            self.request_events[event["id"]] = event

        self.logger.debug(
            f"Loaded {len(self.request_events)} dvm request events from mongo"
        )

    def get_all_feedback_events(self):
        self.logger.info("Getting all feedback events...")
        feedback_events_ls = list(self.mongo_db.events.find({"kind": 7000}))

        for event in tqdm(feedback_events_ls):
            self.feedback_events[event["id"]] = event

            # create an invoice node
            invoice_json_data = {}
            if "tags" in event:
                for tag in event["tags"]:
                    if tag[0] == "amount" and len(tag) >= 3:
                        if tag[2].startswith("lnbc"):
                            tag_data = tag
                            invoice_json_data["amount"] = tag[1]
                            invoice_json_data["invoice"] = tag[2]
                            # now add the author as an extra field too
                            invoice_json_data["creator_pubkey"] = event["pubkey"]
                            invoice_json_data["feedback_event_id"] = event["id"]

                            self.feedback_event_invoices[
                                event["id"]
                            ] = invoice_json_data

                            self.invoices[tag[2]] = invoice_json_data
                            break

        self.logger.debug(
            f"Loaded {len(self.feedback_events)} feedback events from mongo"
        )

    def get_all_response_events(self):
        self.logger.info("Getting all response events...")
        response_events_ls = list(
            self.mongo_db.events.find(
                {
                    "kind": {
                        "$gte": 6000,
                        "$lte": 6999,
                        "$nin": EventKind.get_bad_dvm_kinds(),
                    }
                }
            )
        )

        for event in tqdm(response_events_ls):
            self.response_events[event["id"]] = event

        self.logger.debug(
            f"Loaded {len(self.response_events)} response events from mongo"
        )

    def get_all_user_npubs(self):
        self.logger.info("Getting all user npubs...")
        # first get all dvm nodes
        if len(self.dvm_npubs) == 0:
            self.logger.warning(
                "No DVM npubs found, make sure to call get_all_dvm_npubs() first"
            )

        # get all user nodes
        for event in tqdm(self.request_events.values()):
            if "pubkey" in event and event["pubkey"] not in self.dvm_npubs:
                self.user_npubs.add(event["pubkey"])

    def create_dvm_nodes(self):
        self.logger.info("Creating DVM nodes...")
        with self.neo4j_driver.session() as session:
            for npub_hex in tqdm(self.dvm_npubs):
                npub = helpers.hex_to_npub(npub_hex)

                profile = None
                if npub_hex in self.dvm_nip_89_profiles:
                    profile = self.dvm_nip_89_profiles[npub_hex]

                node_data = {
                    "npub_hex": npub_hex,
                    "npub": npub,
                    "url": "https://dvmdash.live/dvm/" + npub,
                    "neo4j_node_type": "DVM",
                }

                # If a profile exists, add its properties to the JSON document
                if profile:
                    # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
                    # TODO - check if we can make this faster, probably inefficient
                    for k, v in profile.items():
                        if len(str(profile[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                            profile[
                                k
                            ] = '"<data not shown b/c too big, see original event>"'

                    node_data.update(profile)

                node_data = helpers.sanitize_json(node_data)

                json_string = json.dumps(node_data)

                query = """
                    MERGE (n:DVM {npub_hex: $npub_hex})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    RETURN n
                    """
                result = session.run(query, npub_hex=npub_hex, json=json_string)

                record = result.single()
                if record is None:
                    self.logger.error(
                        f"Failed to create or match node for npub_hex: {npub_hex}"
                    )
                else:
                    node = record["n"]
                    if "DVM" not in node.labels:
                        self.logger.warning(
                            f"Node {node.id} was created without the 'DVM' label for npub_hex: {npub_hex}"
                        )
                    else:
                        self.logger.debug(
                            f"Node {node.id} was created or matched with the 'DVM' label for npub_hex: {npub_hex}"
                        )

    def create_user_nodes(self):
        self.logger.info("Creating User nodes...")
        with self.neo4j_driver.session() as session:
            for user_npub_hex in tqdm(self.user_npubs):
                npub = helpers.hex_to_npub(user_npub_hex)
                profile = None

                # TODO - get user_profile data from kind 0's
                node_data = {
                    "npub_hex": user_npub_hex,
                    "npub": npub,
                    "url": "https://dvmdash.live/npub/" + npub,
                    "neo4j_node_type": "User",
                }

                if profile:
                    # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
                    # TODO - check if we can make this faster, probably inefficient
                    for k, v in profile.items():
                        if len(str(profile[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                            profile[
                                k
                            ] = '"<data not shown b/c too big, see original event>"'

                    node_data.update(profile)  # TODO - add attempt to get profile data

                json_string = json.dumps(node_data)

                query = """
                MERGE (n:User {npub_hex: $npub_hex})
                ON CREATE SET n = apoc.convert.fromJsonMap($json)
                ON MATCH SET n += apoc.convert.fromJsonMap($json)
                RETURN n
                """
                # TODO - figure this out
                # ON CREATE SET n = apoc.convert.fromJsonMap($json)
                result = session.run(query, npub_hex=user_npub_hex, json=json_string)

                record = result.single()
                if record is None:
                    self.logger.error(
                        f"Failed to create or match node for npub_hex: {user_npub_hex}"
                    )
                else:
                    node = record["n"]
                    if "User" not in node.labels:
                        self.logger.warning(
                            f"Node {node.id} was created without the 'User' label for npub_hex: {user_npub_hex}"
                        )
                    else:
                        self.logger.debug(
                            f"Node {node.id} was created or matched with the 'User' label for npub_hex: {user_npub_hex}"
                        )

    def _create_event_node(self, session, original_event):
        # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
        # TODO - check if we can make this faster, probably inefficient
        neo4j_event = {"neo4j_node_type": "Event"}

        # start checking special cases
        has_encrypted_tag = next(
            (tag[0] for tag in original_event["tags"] if tag[0] == "encrypted"), None
        )

        if has_encrypted_tag is not None:
            # TODO - support encrypted events
            self.logger.debug(f"Skipping encrypted event: {original_event['id']}")
            return False

        content = None
        if "content" in original_event:
            content = original_event["content"]
        else:
            # get the i tag
            content = next(
                (tag[1] for tag in original_event["tags"] if tag[0] == "i"),
                None,
            )

        if content is None:
            self.logger.debug(
                f"Event {original_event['id']} for kind {original_event['kind']} does not have content field or i tag"
            )
            return False

        # now check if any field is big so we can replace with a short message
        for k, v in original_event.items():
            if k == "_id":
                # this is the mongo id, we don't need this
                continue

            if len(str(original_event[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                neo4j_event[k] = '"<data not shown b/c too big, see original event>"'
            else:
                neo4j_event[k] = original_event[k]

        # add debugging url
        neo4j_event["url"] = f"https://dvmdash.live/event/{neo4j_event['id']}"

        # sanitize it by only keeping top level values as fields
        neo4j_event = helpers.sanitize_json(neo4j_event)

        json_string = json.dumps(neo4j_event)

        # create different events based on the kind
        additional_event_labels = []
        if 5000 <= neo4j_event["kind"] < 6000:
            additional_event_labels = ["DVMRequest"]
        elif 6000 <= neo4j_event["kind"] < 6999:
            additional_event_labels = ["DVMResult"]
        elif neo4j_event["kind"] == 7000:
            # print("event is kind 7000")
            additional_event_labels.append("Feedback")
            # check the tags
            if "tags" in neo4j_event:
                tags = ast.literal_eval(neo4j_event["tags"])
                for tag in tags:
                    # print(f"\ttag is {tag}")
                    if (
                        tag[0] == "status"
                        and len(tag) > 1
                        and tag[1] == "payment-required"
                    ):
                        additional_event_labels.append("FeedbackPaymentRequest")
                        # print("\tadding the label FeedbackPaymentRequest")

        if additional_event_labels:
            # create the event node
            query = (
                """
            MERGE (n:Event:"""
                + ":".join(additional_event_labels)
                + """ {id: $event_id})
            ON CREATE SET n = apoc.convert.fromJsonMap($json)
            ON MATCH SET n += apoc.convert.fromJsonMap($json)
            RETURN n
            """
            )
        else:
            # create the event node
            query = """
            MERGE (n:Event {id: $event_id})
            ON CREATE SET n = apoc.convert.fromJsonMap($json)
            ON MATCH SET n += apoc.convert.fromJsonMap($json)
            RETURN n
            """

        result = session.run(query, event_id=neo4j_event["id"], json=json_string)

        # Check if the created node has the expected label
        node = result.single()["n"]
        if "Event" not in node.labels:
            self.logger.warning(
                f"Node {node.id} was created !without! the 'Event' label for npub_hex: {original_event['pubkey']}"
            )
        else:
            self.logger.debug(
                f"Node {node.id} was created with the 'Event' label for npub_hex: {original_event['pubkey']}"
            )

        return True

    def create_invoice_nodes(self):
        self.logger.info("Creating User nodes...")
        with self.neo4j_driver.session() as session:
            for invoice_lnbc_str, json_data in tqdm(self.invoices.items()):
                # add debugging url
                json_data["url"] = f"https://dvmdash.live/event/{invoice_lnbc_str}"

                self._create_invoice_node(session, invoice_lnbc_str, json_data)

    def _create_invoice_node(self, session, lnbc_str, invoice_json_data):
        # create the invoice node
        # create a uuid for neo4j
        assert lnbc_str == invoice_json_data["invoice"]

        query = """
        MERGE (n:Invoice {id: $lnbc_str})
        ON CREATE SET n += apoc.convert.fromJsonMap($json)
        ON MATCH SET n += apoc.convert.fromJsonMap($json)
        RETURN n
        """

        json_string = json.dumps(invoice_json_data)

        params = {
            "lnbc_str": lnbc_str,
            "json": json_string,
        }

        # Execute the query
        result = session.run(query, params)

        # Check if the created node has the expected label
        node = result.single()["n"]
        if "Invoice" not in node.labels:
            self.logger.warning(
                f"Node {node.id} was created !without! the 'Invoice' label for invoice: {lnbc_str}"
            )
        else:
            self.logger.debug(
                f"Node {node.id} was created with the 'Invoice' label for invoice: {lnbc_str}"
            )

        return True

    def create_user_request_relations(self):
        self.logger.info(
            "Creating MADE_EVENT relationships between Users and Request events..."
        )
        with self.neo4j_driver.session() as session:
            for event in tqdm(self.request_events.values()):
                # get the user's npub_hex
                user_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the user and the event node
                query = """
                    MATCH (n:User {npub_hex: $npub_hex})
                    MATCH (r:Event {id: $event_id})
                    MERGE (n)-[rel:MADE_EVENT]->(r)
                    RETURN rel
                    """

                try:
                    result = session.run(
                        query, npub_hex=user_npub_hex, event_id=event["id"]
                    )

                    record = result.single()
                    if record is None:
                        self.logger.error(
                            f"Failed to create MADE_EVENT relationship between User {user_npub_hex} and Request event {event['id']}. "
                            "One or both nodes may not exist."
                        )
                    else:
                        relationship = record["rel"]
                        self.logger.debug(
                            f"Created MADE_EVENT relationship between User {user_npub_hex} and Request event {event['id']}"
                        )
                except neo4j.exceptions.Neo4jError as e:
                    self.logger.error(
                        f"Error occurred while creating MADE_EVENT relationship between User {user_npub_hex} and Request event {event['id']}: {str(e)}"
                    )

    def create_dvm_feedback_relations(self):
        with self.neo4j_driver.session() as session:
            for event in tqdm(self.feedback_events.values()):
                # get the dvm's npub_hex
                dvm_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the dvm and the feedback node
                query = """
                   MATCH (n:DVM {npub_hex: $npub_hex})
                   MATCH (r:Event {id: $event_id})
                   MERGE (n)-[rel:MADE_EVENT]->(r)
                   RETURN rel
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

                record = result.single()
                if record is None:
                    self.logger.error(
                        f"Failed to create MADE_EVENT relationship between DVM {dvm_npub_hex} and Feedback event {event['id']}"
                    )

                self.logger.debug(
                    f"Result {result} from creating MADE_EVENT relationship"
                    f" between DVM {dvm_npub_hex} and Request event {event['id']}"
                )

                # now get the original request event that the feedback is for to make the
                # FEEDBACK_FOR relation
                request_orig_event_id = next(
                    (tag[1] for tag in event["tags"] if tag[0] == "e"),
                    None,
                )
                if request_orig_event_id is None:
                    self.logger.debug(
                        f"feedback event id {event['id']} is missing a tag pointing to the original"
                        f" request"
                    )
                    continue

                if request_orig_event_id not in self.request_events.keys():
                    self.logger.debug(
                        f"We are missing the request event {request_orig_event_id} that a feedback event is trying to reference"
                    )
                    continue

                # create the relationship between the feedback and the original request node
                query = """
                   MATCH (feedback:Event {id: $feedback_event_id})
                   MATCH (request:Event {id: $request_event_id})
                   MERGE (feedback)-[rel:FEEDBACK_FOR]->(request)
                   RETURN rel
                   """

                result = session.run(
                    query,
                    feedback_event_id=event["id"],
                    request_event_id=request_orig_event_id,
                )

                record = result.single()

                if record is None:
                    self.logger.error(
                        f"Failed to create FEEDBACK_FOR relationship between Feedback {event['id']} and Request event {request_orig_event_id}"
                    )

                self.logger.debug(
                    f"Feedback {event['id']} successfully has a FEEDBACK_FOR relationship"
                    f" for Request event {request_orig_event_id}"
                )

                # next, create relationship form invoice to feedback, if the feedback has an invoice
                if event["id"] in self.feedback_event_invoices:
                    invoice_data = self.feedback_event_invoices[event["id"]]
                    invoice_id = invoice_data["invoice"]
                    query = """
                        MATCH (i:Invoice {id: $invoice_id})
                        MATCH (f:Event {id: $event_id})
                        MERGE (i)-[rel:INVOICE_FROM]->(f)
                        RETURN rel
                    """

                    result = session.run(
                        query, invoice_id=invoice_id, event_id=event["id"]
                    )
                    record = result.single()

                    if record is None:
                        self.logger.error(
                            f"Failed to create INVOICE_FROM relationship between"
                            f" Feedback {event['id']} and Request event {invoice_id}"
                        )

                    self.logger.debug(
                        f"Invoice {invoice_id} successfully has a INVOICE_FROM relationship"
                        f" for Feedback event {event['id']}"
                    )

    def create_dvm_response_relations(self):
        with self.neo4j_driver.session() as session:
            for event in tqdm(self.response_events.values()):
                # get the dvm's npub_hex
                dvm_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the dvm and the response event node
                query = """
                   MATCH (n:DVM {npub_hex: $npub_hex})
                   MATCH (r:Event {id: $event_id})
                   MERGE (n)-[rel:MADE_EVENT]->(r)
                   RETURN rel
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

                record = result.single()

                if record is None:
                    self.logger.error(
                        f"Failed to create MADE_EVENT relationship between DVM {dvm_npub_hex} and Response event {event['id']}"
                    )

                self.logger.debug(
                    f"Result {result} from creating MADE_EVENT relationship"
                    f" between DVM {dvm_npub_hex} and Request event {event['id']}"
                )

                # create the relationship between the response and the original request node
                # TODO - double check a few real response events and the nip docs to make sure this is right
                request_orig_event_id = next(
                    (tag[1] for tag in event["tags"] if tag[0] == "e"),
                    None,
                )
                if request_orig_event_id is None:
                    self.logger.debug(
                        f"response event id {event['id']} is missing a tag pointing to the original"
                        f" request"
                    )
                    continue

                if request_orig_event_id not in self.request_events.keys():
                    self.logger.debug(
                        f"We are missing the request event {request_orig_event_id} that a response event is trying to reference"
                    )
                    continue

                query = """
                   MATCH (response:Event {id: $response_event_id})
                   MATCH (request:Event {id: $request_event_id})
                   MERGE (response)-[rel:RESULT_FOR]->(request)
                   RETURN rel
                   """

                result = session.run(
                    query,
                    response_event_id=event["id"],
                    request_event_id=request_orig_event_id,
                )

                record = result.single()

                if record is None:
                    self.logger.error(
                        f"Failed to create RESULT_FOR relationship between Response {event['id']} and Request event {request_orig_event_id}"
                    )

                self.logger.debug(
                    f"response {event['id']} successfully has a RESULT_FOR relationship"
                    f" for Request event {request_orig_event_id}"
                )

    def run(self):
        # first get events
        self.logger.info("Reading events from mongo db... ")
        self.get_all_dvm_nip89_profiles()
        self.get_all_request_events()
        self.get_all_response_events()
        self.get_all_feedback_events()

        # then start creating nodes
        self.logger.info("Creating user and dvm nodes...")
        self.get_all_dvm_npubs()
        self.get_all_user_npubs()
        self.create_dvm_nodes()
        self.create_user_nodes()
        self.create_invoice_nodes()

        # start creating relations
        self.logger.info("Creating relations...")
        self.create_user_request_relations()
        self.create_dvm_feedback_relations()
        self.create_dvm_response_relations()

    def delete_all_neo4j_relationships(self):
        """
        Delete all relationships in the Neo4j database.

        Parameters:
        neo4j_driver (GraphDatabase.driver): The Neo4j driver instance.

        Returns:
        None
        """
        with self.neo4j_driver.session() as session:
            session.run("MATCH ()-[r]->() DELETE r")
            self.logger.info("Deleted all relationships in Neo4j")

    def delete_all_nodes(self):
        """
        Delete all nodes in the Neo4j database.

        Parameters:
        neo4j_driver (GraphDatabase.driver): The Neo4j driver instance.

        Returns:
        None
        """
        with self.neo4j_driver.session() as session:
            session.run("MATCH (n) DELETE n")
            self.logger.info("Deleted all nodes in Neo4j")

    def clear(self):
        self.delete_all_neo4j_relationships()
        self.delete_all_nodes()

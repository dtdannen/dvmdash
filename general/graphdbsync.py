import json

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

    def get_all_dvm_nip89_profiles(self):
        """
        Get all DVM NIP-89 profiles from the MongoDB database.
        """
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
        for event in tqdm(self.response_events.values()):
            if "pubkey" in event:
                self.dvm_npubs.add(event["pubkey"])

        # get all pub keys from nip-89 profiles
        for dvm_pubkey, profile in self.dvm_nip_89_profiles.items():
            self.dvm_npubs.add(dvm_pubkey)

    def get_all_request_events(self):
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
        feedback_events_ls = list(self.mongo_db.events.find({"kind": 7000}))

        for event in tqdm(feedback_events_ls):
            self.feedback_events[event["id"]] = event

        self.logger.debug(
            f"Loaded {len(self.feedback_events)} feedback events from mongo"
        )

    def get_all_response_events(self):
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
                }

                # If a profile exists, add its properties to the JSON document
                if profile:
                    # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
                    # TODO - check if we can make this faster, probably inefficient
                    for k, v in profile.items():
                        if len(str(profile[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                            profile[
                                k
                            ] = "<data not shown b/c too big, see original event>"

                    node_data.update(profile)

                node_data = helpers.sanitize_json(node_data)

                json_string = json.dumps(node_data)

                query = """
                    MERGE (n:DVM {npub_hex: $npub_hex})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    """
                result = session.run(query, npub_hex=npub_hex, json=json_string)

                self.logger.debug(f"Result {result} from creating DVM node: {npub_hex}")

    def create_user_nodes(self):
        with self.neo4j_driver.session() as session:
            for user_npub_hex in tqdm(self.user_npubs):
                npub = helpers.hex_to_npub(user_npub_hex)
                profile = None

                # TODO - get user_profile data from kind 0's
                node_data = {
                    "npub_hex": user_npub_hex,
                    "npub": npub,
                    "url": "https://dvmdash.live/npub/" + npub,
                }

                if profile:
                    # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
                    # TODO - check if we can make this faster, probably inefficient
                    for k, v in profile.items():
                        if len(str(profile[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                            profile[
                                k
                            ] = "<data not shown b/c too big, see original event>"

                    node_data.update(profile)  # TODO - add attempt to get profile data

                json_string = json.dumps(node_data)

                query = """
                MERGE (n:User {npub_hex: $npub_hex})
                """
                # TODO - figure this out
                # ON CREATE SET n = apoc.convert.fromJsonMap($json)
                result = session.run(query, npub_hex=user_npub_hex, json=json_string)

                self.logger.debug(
                    f"Result {result} from creating User node: {user_npub_hex}"
                )

    def _create_event_node(self, session, original_event):
        # replace any fields that are too big with a "<data not shown b/c too big, see original event>"
        # TODO - check if we can make this faster, probably inefficient
        neo4j_event = {}

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
                neo4j_event[k] = "<data not shown b/c too big, see original event>"
            else:
                neo4j_event[k] = original_event[k]

        # add debugging url
        neo4j_event["url"] = f"https://dvmdash.live/event/{neo4j_event['id']}"

        # sanitize it by only keeping top level values as fields
        neo4j_event = helpers.sanitize_json(neo4j_event)

        json_string = json.dumps(neo4j_event)

        # create the event node
        # TODO - see if we can have an "event" type of Node and have sub nodes of "Request, Feedback, Response"
        query = """
        MERGE (n:Event {id: $event_id})
        ON CREATE SET n = apoc.convert.fromJsonMap($json)
        """

        result = session.run(query, event_id=neo4j_event["id"], json=json_string)

        self.logger.debug(
            f"Result {result} from creating request node: {neo4j_event['id']}"
        )

        return True

    def create_user_request_relations(self):
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
                   MERGE (n)-[:MADE_EVENT]->(r)
                   """

                result = session.run(
                    query, npub_hex=user_npub_hex, event_id=event["id"]
                )

                self.logger.debug(
                    f"Result {result} from creating MADE_EVENT relationship"
                    f" between User {user_npub_hex} and Request event {event['id']}"
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
                   MERGE (n)-[:MADE_EVENT]->(r)
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

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
                   MERGE (feedback)-[:FEEDBACK_FOR]->(request)
                   """

                result = session.run(
                    query,
                    feedback_event_id=event["id"],
                    request_event_id=request_orig_event_id,
                )

                self.logger.debug(
                    f"Feedback {event['id']} successfully has a FEEDBACK_FOR relationship"
                    f" for Request event {request_orig_event_id}"
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
                   MERGE (n)-[:MADE_EVENT]->(r)
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

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
                   MERGE (response)-[:RESULT_FOR]->(request)
                   """

                result = session.run(
                    query,
                    response_event_id=event["id"],
                    request_event_id=request_orig_event_id,
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

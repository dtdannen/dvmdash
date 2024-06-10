import json

from general import helpers
from general.dvm import EventKind


class GraphDBSync:
    def __init__(self, db, neo4j_driver, logger=None):
        self.MAX_FIELD_SIZE = 1000  # max size in bytes for any single json field
        self.mongo_db = db
        self.neo4j_driver = neo4j_driver
        self.logger = logger
        self.user_npubs = set()
        self.dvm_npubs = set()
        self.dvm_nip_89_profiles = {}
        self.request_events = []
        self.feedback_events = []
        self.response_events = []

    def get_all_dvm_nip89_profiles(self):
        """
        Get all DVM NIP-89 profiles from the MongoDB database.
        """
        for nip89_event in self.mongo_db.events.find({"kind": 31990}):
            if "pubkey" in nip89_event:
                try:
                    self.dvm_nip_89_profiles[nip89_event["pubkey"]] = json.loads(
                        nip89_event["content"]
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Error loading json from {nip89_event['content']}"
                    )
                    pass

    def get_all_dvm_npubs(self):
        for event in self.response_events:
            if "pubkey" in event:
                self.dvm_npubs.add(event["pubkey"])

        # get all pub keys from nip-89 profiles
        for dvm_pubkey, profile in self.dvm_nip_89_profiles.items():
            self.dvm_npubs.add(dvm_pubkey)

    def get_all_request_events(self):
        self.request_events = list(
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

        self.logger.debug(
            f"Loaded {len(self.request_events)} dvm request events from mongo"
        )

    def get_all_feedback_events(self):
        self.feedback_events = list(self.mongo_db.events.find({"kind": 7000}))

        self.logger.debug(
            f"Loaded {len(self.feedback_events)} feedback events from mongo"
        )

    def get_all_response_events(self):
        self.response_events = list(
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
        for event in self.request_events:
            if "pubkey" in event and event["pubkey"] not in self.dvm_npubs:
                self.user_npubs.add(event["pubkey"])

    def create_dvm_nodes(self):
        with self.neo4j_driver.session() as session:
            for npub_hex in self.dvm_npubs:
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

                json_string = json.dumps(node_data)

                query = """
                    MERGE (n:DVM {npub_hex: $npub_hex})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    """

                result = session.run(query, npub_hex=npub_hex, json=json_string)

                self.logger.debug(f"Result {result} from creating DVM node: {npub_hex}")

    def create_user_nodes(self):
        with self.neo4j_driver.session() as session:
            for user_npub_hex in self.user_npubs:
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
                ON CREATE SET n = apoc.convert.fromJsonMap($json)
                """

                result = session.run(query, npub_hex=user_npub_hex, json=json_string)

                self.logger.debug(
                    f"Result {result} from creating DVM node: {user_npub_hex}"
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
            if len(str(original_event[k]).encode("utf-8")) > self.MAX_FIELD_SIZE:
                neo4j_event[k] = "<data not shown b/c too big, see original event>"
            else:
                neo4j_event[k] = original_event[k]

        # add debuging url
        neo4j_event["url"] = f"https://dvmdash.live/event/{neo4j_event['id']}"

        # create the event node
        # TODO - see if we can have an "event" type of Node and have sub nodes of "Request, Feedback, Response"
        query = """
        MERGE (n:Event {event_id: $event_id})
        ON CREATE SET n = apoc.convert.fromJsonMap($json)
        """

        json_string = json.dumps(neo4j_event)

        result = session.run(query, event_id=neo4j_event["id"], json=json_string)

        self.logger.debug(
            f"Result {result} from creating request node: {neo4j_event['id']}"
        )

        return True

    def create_user_request_relations(self):
        with self.neo4j_driver.session() as session:
            for event in self.request_events:
                # get the user's npub_hex
                user_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the user and the event node
                query = """
                   MATCH (n:User {npub_hex: $npub_hex})
                   MATCH (r:Event {event_id: $event_id})
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
            for event in self.feedback_events:
                # get the dvm's npub_hex
                dvm_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the dvm and the feedback node
                query = """
                   MATCH (n:DVM {npub_hex: $npub_hex})
                   MATCH (r:Event {event_id: $event_id})
                   MERGE (n)-[:MADE_EVENT]->(r)
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

                self.logger.debug(
                    f"Result {result} from creating MADE_EVENT relationship"
                    f" between DVM {dvm_npub_hex} and Request event {event['id']}"
                )

                # now get the original request event that the feedback is for to make the
                # FEEDBACK_FOR relation

    def create_dvm_response_relations(self):
        with self.neo4j_driver.session() as session:
            for event in self.response_events:
                # get the dvm's npub_hex
                dvm_npub_hex = event["pubkey"]

                # create the event node
                node_creation_success = self._create_event_node(session, event)
                if not node_creation_success:
                    continue

                # create the relationship between the user and the event node
                query = """
                   MATCH (n:DVM {npub_hex: $npub_hex})
                   MATCH (r:Event {event_id: $event_id})
                   MERGE (n)-[:MADE_EVENT]->(r)
                   """

                result = session.run(query, npub_hex=dvm_npub_hex, event_id=event["id"])

                self.logger.debug(
                    f"Result {result} from creating MADE_EVENT relationship"
                    f" between DVM {dvm_npub_hex} and Request event {event['id']}"
                )

    def create_content(
        tx, content: str, content_orig_event_id: str, max_size: int = 1000
    ) -> None:
        """
        Create a node in the Neo4j database with label 'Content' using a hash of the content to prevent duplicates.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        content (str): The content string.
        content_orig_event_id (str): The id of the event that has the content
        max_size (int): The maximum allowed size for the content in bytes.

        Returns:
        None
        """
        # Measure the size of the content in bytes
        byte_size = len(content.encode("utf-8"))

        # TODO - put all data into the node properties like this:
        #   Define the Cypher query to create a node with properties from the JSON document
        #   query = """
        #   MERGE (n:NPub {npub_hex: $npub_hex})
        #   ON CREATE SET n = apoc.convert.fromJsonMap($json)
        #   """
        #   and then make sure to pass the json object as a parameter

        # Check if the content size is within the allowed limit
        if byte_size <= max_size:
            # Define the Cypher query to create a node with the given properties only if it does not exist
            query = """
            MERGE (c:Content {n_id: $content_orig_event_id})
            ON CREATE SET c.content = $content, c.url = "https://dvmdash.live/event/" + $content_orig_event_id
            """
            tx.run(query, content_orig_event_id=content_orig_event_id, content=content)
            # print(f"Content node created or already exists: {content_orig_event_id}")
        else:
            # Define the Cypher query to create a node with the given properties only if it does not exist
            query = """
                    MERGE (c:Content {n_id: $content_orig_event_id})
                    ON CREATE SET c.content = $content, c.url = "https://dvmdash.live/event/" + $content_orig_event_id
                    """
            content = "<content too large, see original event>"
            tx.run(query, content_orig_event_id=content_orig_event_id, content=content)
            # print(f"Content node created or already exists: {content_orig_event_id}")

    def create_npub(tx, npub_hex: str, npub: str, name: str = "") -> None:
        """
        Create a node in the Neo4j database with label 'NPub'.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        npub_hex (str): The hexadecimal representation of the public key.
        npub (str): The public key.
        name (str): The name of the person. Defaults to the first 8 characters of npub if not provided.

        Returns:
        None
        """
        # If name is not provided, use the first 8 characters of npub as the name
        if not name:
            name = npub[:8]

        # Define the Cypher query to create a node with the given properties only if it does not exist
        query = """
        MERGE (n:NPub {npub_hex: $npub_hex})
        ON CREATE SET n.npub = $npub, n.name = $name, n.url = "https://dvmdash.live/npub/" + $npub
        """

        # Execute the query with the provided parameters
        tx.run(query, npub_hex=npub_hex, npub=npub, name=name)

    # Function to create a content node if it does not already exist

    def create_request(
        tx, content: str, request_orig_event_id: str, max_size: int = 1000
    ) -> None:
        """
        Create a node in the Neo4j database with label 'Request' using a hash of the content to prevent duplicates.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        content (str): The content string.
        request_orig_event_id (str): The id of the event that has the content.
        max_size (int): The maximum allowed size for the content in bytes.

        Returns:
        None
        """
        # Measure the size of the content in bytes
        byte_size = len(content.encode("utf-8"))

        # Check if the content size is within the allowed limit
        if byte_size <= max_size:
            # Define the Cypher query to create a node with the given properties only if it does not exist
            query = """
            MERGE (r:Request {n_id: $request_orig_event_id})
            ON CREATE SET r.content = $content, r.url = "https://dvmdash.live/event/" + $request_orig_event_id
            """
            tx.run(query, request_orig_event_id=request_orig_event_id, content=content)
            # print(f"Request node created or already exists: {request_orig_event_id}")
        else:
            # Define the Cypher query to create a node with the given properties only if it does not exist
            query = """
                    MERGE (r:Request {n_id: $request_orig_event_id})
                    ON CREATE SET r.content = $content, r.url = "https://dvmdash.live/event/" + $request_orig_event_id
                    """
            content = "<content too large, see original event>"
            tx.run(query, request_orig_event_id=request_orig_event_id, content=content)
            # print(f"Content too large to create node: size: {byte_size} bytes")

    def create_feedback(
        tx, content: str, feedback_orig_event_id: str, max_size: int = 1000
    ):
        """
        Create a node in the Neo4j database with label 'Feedback' using a hash of the content to prevent duplicates.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        content (str): The content string.
        feedback_orig_event_id (str): The id of the event that has the content.
        max_size (int): The maximum allowed size for the content in bytes.

        Returns:
        None
        """
        # Measure the size of the content in bytes
        byte_size = len(content.encode("utf-8"))

        # Check if the content size is within the allowed limit
        if byte_size <= max_size:
            # Define the Cypher query to create a node with the given properties only if it does not exist
            query = """
            MERGE (f:Feedback {feedback_id: $feedback_orig_event_id})
            ON CREATE SET f.content = $content, f.url = "https://dvmdash.live/event/" + $feedback_orig_event_id
            """
            tx.run(
                query, feedback_orig_event_id=feedback_orig_event_id, content=content
            )
            # print(f"Feedback node created or already exists: {feedback_orig_event_id}")
        else:
            query = """
                    MERGE (f:Feedback {feedback_id: $feedback_orig_event_id})
                    ON CREATE SET f.content = $content, f.url = "https://dvmdash.live/event/" + $feedback_orig_event_id
                    """
            content = "<content too large, see original event>"
            tx.run(
                query, feedback_orig_event_id=feedback_orig_event_id, content=content
            )
            # print(f"Content too large to create node: size: {byte_size} bytes")

    def create_requested_relationship(
        tx, npub_hex: str, request_orig_event_id: str
    ) -> None:
        """
        Create a relationship in the Neo4j database between an NPub node and a Request node.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        npub_hex (str): The hexadecimal representation of the public key.
        content_orig_event_id (str): The id of the event that has the content

        Returns:
        None
        """
        #
        query = """
        MATCH (n:NPub {npub_hex: $npub_hex})
        MATCH (r:Request {n_id: $request_orig_event_id})
        MERGE (n)-[:REQUESTED]->(r)
        """

        tx.run(query, npub_hex=npub_hex, request_orig_event_id=request_orig_event_id)

    def create_created_for_relationship(
        tx, npub_hex: str, content_orig_event_id: str
    ) -> None:
        """
        Create a relationship in the Neo4j database between an NPub node and a Content node.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        npub_hex (str): The hexadecimal representation of the public key.
        content_orig_event_id (str): The id of the event that has the content

        Returns:
        None
        """
        # Define the Cypher query to create a relationship between the NPub and Content nodes
        query = """
        MATCH (n:NPub {npub_hex: $npub_hex})
        MATCH (c:Content {n_id: $content_orig_event_id})
        MERGE (c)-[:CREATED_FOR]->(n)
        """

        # Execute the query with the provided parameters
        tx.run(query, npub_hex=npub_hex, content_orig_event_id=content_orig_event_id)

    def create_made_relationship(
        tx, event_id: str, npub_hex: str, dest_node="request"
    ) -> None:
        """
        Create a relationship in the Neo4j database between an NPub node and a Request or Content node.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        event_id (str): The id of the event that has the content.
        npub_hex (str): The hexadecimal representation of the public key.
        dest_node (str): The destination node type. Defaults to 'request'.

        Returns:
        None
        """

        if dest_node not in ["request", "content"]:
            raise ValueError("dest_node must be either 'request' or 'content'")

        # Define the Cypher query to create a relationship between the NPub and Request or Content nodes
        query = f"""
        MATCH (n:NPub {{npub_hex: $npub_hex}})
        MATCH (c:{dest_node.capitalize()} {{n_id: $event_id}})
        MERGE (n)-[:MADE]->(c)
        """

        # Execute the query with the provided parameters
        tx.run(query, npub_hex=npub_hex, event_id=event_id)

    def created_result_for_relationship(
        tx, request_orig_event_id: str, content_orig_event_id: str
    ) -> None:
        """
        Create a relationship in the Neo4j database between a Request node and a Content node.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        request_orig_event_id (str): The id of the event that has the request content.
        content_orig_event_id (str): The id of the event that has the response content.

        Returns:
        None
        """
        # Define the Cypher query to create a relationship between the Request and Content nodes
        query = """
        MATCH (r:Request {n_id: $request_orig_event_id})
        MATCH (c:Content {n_id: $content_orig_event_id})
        MERGE (c)-[:RESULT_FOR]->(r)
        """

        # Execute the query with the provided parameters
        tx.run(
            query,
            request_orig_event_id=request_orig_event_id,
            content_orig_event_id=content_orig_event_id,
        )

    def created_feedback_for_relationship(
        tx, request_orig_event_id: str, feedback_orig_event_id: str
    ) -> None:
        """
        Create a relationship in the Neo4j database between a Request node and a Feedback node.

        Parameters:
        tx (Transaction): The Neo4j transaction context.
        request_orig_event_id (str): The id of the event that has the request content.
        feedback_orig_event_id (str): The id of the event that has the feedback content.

        Returns:
        None
        """
        # Define the Cypher query to create a relationship between the Request and Feedback nodes
        query = """
        MATCH (r:Request {n_id: $request_orig_event_id})
        MATCH (f:Feedback {feedback_id: $feedback_orig_event_id})
        MERGE (f)-[:FEEDBACK_FOR]->(r)
        """

        # Execute the query with the provided parameters
        tx.run(
            query,
            request_orig_event_id=request_orig_event_id,
            feedback_orig_event_id=feedback_orig_event_id,
        )

    def run(self):
        # first get events
        self.get_all_dvm_nip89_profiles()
        self.get_all_request_events()
        self.get_all_response_events()
        self.get_all_feedback_events()

        # then start creating nodes
        self.get_all_dvm_npubs()
        self.get_all_user_npubs()
        self.create_dvm_nodes()
        self.create_user_nodes()

        # start creating relations
        self.create_user_request_relations()
        self.create_dvm_feedback_relations()
        self.create_dvm_response_relations()

    def process_notes_into_neo4j(mongo_db, neo4j_driver):
        all_dvm_request_events = list(
            mongo_db.events.find({"kind": {"$gte": 5000, "$lte": 5999}})
        )

        all_dvm_request_events = [
            event
            for event in all_dvm_request_events
            if event["kind"] not in EventKind.get_bad_dvm_kinds()
        ]
        logger.info(
            f"Loaded {len(all_dvm_request_events)} dvm request events from mongo"
        )

        all_dvm_response_events = list(
            mongo_db.events.find({"kind": {"$gte": 6000, "$lte": 6999}})
        )

        all_dvm_response_events = [
            event
            for event in all_dvm_response_events
            if event["kind"] not in EventKind.get_bad_dvm_kinds()
        ]

        logger.info(
            f"Loaded {len(all_dvm_response_events)} dvm response events from mongo"
        )

        all_feedback_requests = list(mongo_db.events.find({"kind": 7000}))

        logger.info(
            f"Loaded {len(all_feedback_requests)} feedback request events from mongo"
        )

        dvm_nip89_profiles = get_all_dvm_nip89_profiles(mongo_db)
        logger.info(f"Loaded {len(dvm_nip89_profiles)} dvm nip89 profiles")

        with neo4j_driver.session() as session:
            # # first, create all nodes for all npubs
            for event in tqdm(all_dvm_request_events + all_dvm_response_events):
                npub_hex = event["pubkey"]
                npub = helpers.hex_to_npub(npub_hex)

                name = ""
                if npub_hex in dvm_nip89_profiles:
                    name = dvm_nip89_profiles[npub_hex].get("name", "")

                create_npub(session, npub_hex, npub, name)

        with neo4j_driver.session() as session:
            # second, create request nodes for all DVM request events and create relationship between
            for event in tqdm(all_dvm_request_events):
                has_encrypted_tag = next(
                    (tag[0] for tag in event["tags"] if tag[0] == "encrypted"), None
                )

                if has_encrypted_tag is not None:
                    print(f"Skipping encrypted request: {has_encrypted_tag}")
                    continue

                # print("event.keys()")
                if "content" in event:
                    content = event["content"]
                else:
                    # get the i tag
                    content = next(
                        (tag[1] for tag in event["tags"] if tag[0] == "i"),
                        None,
                    )

                if content is None:
                    logger.warning(
                        f"Event {event['id']} for kind {event['kind']} does not have content field or i tag"
                    )
                    logger.warning(f"Full event: {event}")
                    continue

                content_payload_str = event["content"]
                request_orig_event_id = event["id"].strip()

                create_request(session, content_payload_str, request_orig_event_id)

                customer_npub_hex = event.get("pubkey", None)

                if customer_npub_hex is not None:
                    create_requested_relationship(
                        session,
                        customer_npub_hex,
                        request_orig_event_id,
                    )
                    # logger.info(
                    #     f"A relationship was created between {helpers.hex_to_npub(customer_npub_hex)} and {request_orig_event_id}"
                    # )
                    # print("Run this query to see if the request and the npubs exist")
                    # print(
                    #     'MATCH (r:Request {n_id: "',
                    #     request_orig_event_id,
                    #     '"}) RETURN r',
                    # )
                    # print('MATCH (n:NPub {npub_hex: "', customer_npub_hex, '"}) RETURN n')
                    # print("Sleeping to enable time for debugging")

                    # time.sleep(200)
                else:
                    logger.warning(
                        f"Could not find customer npub for request event {request_orig_event_id}"
                    )
        #
        # with neo4j_driver.session() as session:
        #     # third, create content nodes for all DVM response events and create relationship between
        #     for event in tqdm(all_dvm_response_events):
        #         if "content" not in event:
        #             logger.warning(
        #                 f"Event {event['id']} for kind {event['kind']} does not have content field"
        #             )
        #             continue
        #
        #         content_payload_str = event["content"]
        #         content_orig_event_id = event["id"]
        #
        #         create_content(session, content_payload_str, content_orig_event_id)
        #
        #         request_orig_event_id = None
        #         # try getting request tag
        #         request_tag_content = next(
        #             (req_tag[1] for req_tag in event["tags"] if req_tag[0] == "request"),
        #             None,
        #         )
        #
        #         # get the request event id
        #         # try to get it from the request tag
        #         if request_tag_content:
        #             request_tag_content = json.loads(request_tag_content)
        #             if "id" in request_tag_content:
        #                 request_orig_event_id = request_tag_content["id"]
        #         else:
        #             request_orig_event_id = next(
        #                 (tag[1] for tag in event["tags"] if tag[0] == "e"),
        #                 None,
        #             )
        #
        #         if request_orig_event_id is not None:
        #             created_result_for_relationship(
        #                 session,
        #                 request_orig_event_id,
        #                 content_orig_event_id,
        #             )
        #             # logger.info(
        #             #     f"A relationship was created between {request_orig_event_id} and {content_orig_event_id}"
        #             # )
        #         else:
        #             logger.warning(
        #                 f"Could not find request event {request_orig_event_id} for response event {content_orig_event_id}"
        #             )
        #
        #         customer_npub_hex = next(
        #             (tag[1] for tag in event["tags"] if tag[0] == "p"), None
        #         )
        #
        #         if customer_npub_hex is None:
        #             if request_tag_content:
        #                 try:
        #                     request_tag_content = json.loads(request_tag_content)
        #                     if "pubkey" in request_tag_content:
        #                         customer_npub_hex = request_tag_content["pubkey"]
        #                         logger.warning(
        #                             "Got customer npub from request tag because it was not in the 'p' tag"
        #                         )
        #                 except Exception as e:
        #                     logger.warning(
        #                         f"Could not get customer npub from request tag content: {request_tag_content}"
        #                     )
        #                     logger.warning(e)
        #         else:
        #             # logger.info("Got customer npub from 'p' tag")
        #             pass
        #
        #         if customer_npub_hex is not None:
        #             create_created_for_relationship(
        #                 session,
        #                 customer_npub_hex,
        #                 content_orig_event_id,
        #             )
        #             # logger.info(
        #             #     f"A relationship was created between {helpers.hex_to_npub(customer_npub_hex)} and {content_orig_event_id}"
        #             # )
        #         else:
        #             logger.warning(
        #                 f"Could not find customer npub for response event {content_orig_event_id}"
        #             )

        # with neo4j_driver.session() as session:
        #     # fourth, create feedback nodes for all request events and create relationship between
        #     for event in tqdm(all_feedback_requests):
        #         if "content" not in event:
        #             logger.warning(
        #                 f"Event {event['id']} for kind {event['kind']} does not have content field"
        #             )
        #             continue
        #
        #         content_payload_str = event["content"]
        #         feedback_orig_event_id = event["id"]
        #
        #         create_feedback(session, content_payload_str, feedback_orig_event_id)
        #
        #         request_orig_event_id = next(
        #             (tag[1] for tag in event["tags"] if tag[0] == "e"),
        #             None,
        #         )
        #
        #         if request_orig_event_id is not None:
        #             created_feedback_for_relationship(
        #                 session,
        #                 request_orig_event_id,
        #                 feedback_orig_event_id,
        #             )
        #             # logger.info(
        #             #     f"A relationship was created between {request_orig_event_id} and {feedback_orig_event_id}"
        #             # )
        #         else:
        #             logger.warning(
        #                 f"Could not find request event {request_orig_event_id} for feedback event {feedback_orig_event_id}"
        #             )

    def delete_all_relationships(neo4j_driver):
        """
        Delete all relationships in the Neo4j database.

        Parameters:
        neo4j_driver (GraphDatabase.driver): The Neo4j driver instance.

        Returns:
        None
        """
        with neo4j_driver.session() as session:
            session.run("MATCH ()-[r]->() DELETE r")
            logger.info("Deleted all relationships in Neo4j")

    def delete_all_nodes(neo4j_driver):
        """
        Delete all nodes in the Neo4j database.

        Parameters:
        neo4j_driver (GraphDatabase.driver): The Neo4j driver instance.

        Returns:
        None
        """
        with neo4j_driver.session() as session:
            session.run("MATCH (n) DELETE n")
            logger.info("Deleted all nodes in Neo4j")

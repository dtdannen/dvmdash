from enum import Enum
from pymongo.database import Database


class SummaryType(Enum):
    GLOBAL = auto_increment()
    DVM = auto_increment()
    KIND = auto_increment()


class Summary:
    def __init__(self, summary_type: SummaryType, db: Database):
        self.summary_type = summary_type
        self.db = db
        self.summary_data = (
            {}
        )  # this is the data that gets passed to a django template, for example

    def get_data_from_db(self):
        """
        Pulls data from the database
        """
        raise NotImplemented()

    def compute(self):
        """
        Performs computations over the data
        """
        raise NotImplemented()

    def get_summary_data(self):
        """
        Returns the summary_data
        """
        return self.summary_data

    def write_to_db(self):
        """
        Writes the results to the database
        """
        raise NotImplemented()


class GlobalSummary(Summary):
    def __init__(self, db: Database):
        super().__init__(SummaryType.GLOBAL, db)

    def compute(self):
        """
        Pulls data from the database and computes data needed
        """
        # pull data from the database
        all_dvm_events = list(
            self.db.events.find({"kind": {"$gte": 5000, "$lte": 6999}})
        )

    def write_to_db(self):
        """
        Writes the results to the database
        """
        # write the results to the database
        pass

from dvm import EventKind
import os
import loguru
import sys


def setup_logging():
    # Create a logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure the logger to use the DEBUG level
    loguru.logger.remove()  # Remove the default logger
    loguru.logger.add(sys.stderr, level="DEBUG")

    return loguru.logger


# set up logging

LOGGER = setup_logging()
LOGGER.info("Starting up in current directory: ", os.getcwd())


class GlobalStats:
    dvm_requests = 0  # k
    dvm_results = 0  # k
    dvm_requests_24_hrs = 0  # k
    dvm_results_24_hrs = 0  # k
    dvm_requests_1_week = 0  # k
    dvm_results_1_week = 0  # k
    dvm_requests_1_month = 0  # k
    dvm_results_1_month = 0  # k
    unique_users = 0  # k
    most_popular_kind = -2  # k
    most_popular_dvm = None  # k

    num_request_kinds = -1
    num_result_kinds = -1
    total_amount_paid_to_dvm_millisats = -1

    num_nip89_profiles = -1

    @classmethod
    def compute_stats(cls):
        stats = {
            "dvm_requests_all_time": GlobalStats.dvm_requests,
            "dvm_results_all_time": GlobalStats.dvm_results,
            "dvm_requests_24_hrs": GlobalStats.dvm_requests_24_hrs,
            "dvm_results_24_hrs": GlobalStats.dvm_results_24_hrs,
            "dvm_requests_1_week": GlobalStats.dvm_requests_1_week,
            "dvm_results_1_week": GlobalStats.dvm_results_1_week,
            "num_dvm_request_kinds": GlobalStats.num_request_kinds,
            "num_dvm_result_kinds": GlobalStats.num_result_kinds,
            "dvm_nip_89s": GlobalStats.num_nip89_profiles,
            "dvm_pub_keys": len(DVMStats.instances),
            "total_amount_paid_to_dvm_sats": int(
                GlobalStats.total_amount_paid_to_dvm_millisats / 1000
            ),
            "most_popular_kind": GlobalStats.most_popular_kind,
            "most_popular_dvm_npub": GlobalStats.most_popular_dvm.npub_hex,
            "unique_dvm_users": GlobalStats.unique_users,
        }

        try:
            stats[
                "most_popular_dvm_name"
            ] = GlobalStats.most_popular_dvm.nip_89_profile["name"]
        except:
            stats[
                "most_popular_dvm_name"
            ] = f"{GlobalStats.most_popular_dvm.npub_hex[:8]}...{GlobalStats.most_popular_dvm.npub_hex[:-4]}"

        return stats

    @classmethod
    def reset(cls):
        cls.dvm_requests = 0  # k
        cls.dvm_results = 0  # k
        cls.dvm_requests_24_hrs = 0  # k
        cls.dvm_results_24_hrs = 0  # k
        cls.dvm_requests_1_week = 0  # k
        cls.dvm_results_1_week = 0  # k
        cls.dvm_requests_1_month = 0  # k
        cls.dvm_results_1_month = 0  # k
        cls.unique_users = 0  # k
        cls.most_popular_kind = -2  # k
        cls.most_popular_dvm = None  # k

        cls.num_request_kinds = -1
        cls.num_result_kinds = -1
        cls.total_amount_paid_to_dvm_millisats = -1

        cls.num_nip89_profiles = -1


# use this class to track all stats for a given DVM
class DVMStats:
    instances = {}

    def __init__(self, npub_hex):
        self.npub_hex = npub_hex
        self.jobs_completed_from_mongo = 0  # k
        self.avg_response_time_per_kind_from_neo4j = {}  # k
        self.number_of_jobs_per_kind_from_neo4j = {}  # k
        self.total_millisats_earned_per_kind_from_neo4j = {}  # k
        self.nip_89_profile = None  # k
        self.profile_created_at = None  # k

        DVMStats.instances[npub_hex] = self

    def add_nip89_profile(self, profile, created_at):
        if (
            self.nip_89_profile
            and self.profile_created_at
            and self.profile_created_at > created_at
        ):
            # do nothing because we already have a more recent nip89 profile
            return

        self.nip_89_profile = profile
        self.profile_created_at = created_at

    def compute_stats(self):
        stats = {
            "total_sats_received": int(
                sum(v for v in self.total_millisats_earned_per_kind_from_neo4j.values())
                / 1000
            ),
            "number_jobs_completed": sum(
                v for v in self.number_of_jobs_per_kind_from_neo4j.values()
            ),
        }

        kind_stats = {}
        for kind in set(
            list(self.avg_response_time_per_kind_from_neo4j.keys())
            + list(self.number_of_jobs_per_kind_from_neo4j.keys())
            + list(self.total_millisats_earned_per_kind_from_neo4j.keys())
        ):
            kind_details = {}
            if kind in self.avg_response_time_per_kind_from_neo4j.keys():
                kind_details[
                    "avg_response_time"
                ] = self.avg_response_time_per_kind_from_neo4j[kind]
            if kind in self.total_millisats_earned_per_kind_from_neo4j.keys():
                kind_details["total_sats_earned"] = int(
                    self.total_millisats_earned_per_kind_from_neo4j[kind] / 1000
                )
            if kind in self.number_of_jobs_per_kind_from_neo4j.keys():
                kind_details[
                    "number_of_jobs"
                ] = self.number_of_jobs_per_kind_from_neo4j[kind]
            kind_stats[str(kind)] = kind_details

        stats["kind_stats"] = kind_stats

        if self.nip_89_profile:
            stats["profile"] = self.nip_89_profile

        return stats

    @classmethod
    def get_instance(cls, npub_hex):
        if npub_hex not in cls.instances:
            cls.instances[npub_hex] = cls(npub_hex)
        return cls.instances.get(npub_hex)

    @classmethod
    def get_all_stats(cls):
        return {
            npub_hex: dvm.compute_stats() for npub_hex, dvm in cls.instances.items()
        }

    @classmethod
    def reset(cls):
        cls.instances = {}


class KindStats:
    instances = {}

    def __init__(self, kind_number: int):
        self.kind_number = kind_number
        self.unique_users = 0  # k
        self.count_from_mongo = 0  # k
        self.average_response_time_per_dvm = {}
        self.dvm_npubs = []  # k
        self.millisats_earned_per_dvm = {}
        self.job_count_per_dvm = {}
        self.request_count = -1
        self.result_count = -1
        self.data_per_dvm = (
            {}
        )  # key is dvm_npub_hex, value is the sats, response time, and job count for each

        KindStats.instances[kind_number] = self

    def add_dvm_npub_earnings_and_response_time(
        self,
        dvm_npub: str,
        millisats_earned: int,
        jobs_performed: int,
        avg_response_time: float,
    ):
        # LOGGER.warning(
        #     f"dvm npub is {dvm_npub} and dvm.npubs is {self.dvm_npubs} and is it inside it? {dvm_npub in self.dvm_npubs}"
        # )
        if dvm_npub not in self.dvm_npubs:
            self.dvm_npubs.append(dvm_npub)
            self.millisats_earned_per_dvm[dvm_npub] = millisats_earned
            self.job_count_per_dvm[dvm_npub] = jobs_performed
            self.average_response_time_per_dvm[dvm_npub] = avg_response_time
            self.data_per_dvm[dvm_npub] = {
                "sats_earned": int(millisats_earned / 1000),
                "jobs_performed": jobs_performed,
                "avg_response_time": avg_response_time,
            }
            # if the dvm has a name, then add the name too
            if DVMStats.get_instance(dvm_npub).nip_89_profile:
                if "display_name" in DVMStats.get_instance(dvm_npub).nip_89_profile:
                    dvm_name = DVMStats.get_instance(dvm_npub).nip_89_profile[
                        "display_name"
                    ]
                    self.data_per_dvm[dvm_npub]["name"] = dvm_name

        else:
            LOGGER.error(
                "DVM npub already exists for this kind, error in db processing"
            )

    def compute_stats(self):
        stats = {
            "total_jobs_requested": self.request_count,
            "total_jobs_performed": self.result_count,
            "number_of_dvms": len(self.dvm_npubs),
            "total_sats_paid_to_dvms": int(
                sum(v for v in self.millisats_earned_per_dvm.values()) / 1000
            ),
            "dvm_npubs": self.dvm_npubs,
            "data_per_dvm": self.data_per_dvm,
        }

        return stats

    @classmethod
    def get_instance(cls, kind_number):
        # we will use the request kind number for all data related to the request and the result
        if (
            EventKind.DVM_RESULT_RANGE_START.value
            <= kind_number
            <= EventKind.DVM_RESULT_RANGE_END.value
        ):
            kind_number = kind_number - 1000  # this gives us the request kind number
        if kind_number not in cls.instances:
            cls.instances[kind_number] = cls(kind_number)
        return cls.instances.get(kind_number)

    @classmethod
    def get_all_stats(cls):
        return {
            kind_number: kind.compute_stats()
            for kind_number, kind in cls.instances.items()
        }

    @classmethod
    def reset(cls):
        cls.instances = {}

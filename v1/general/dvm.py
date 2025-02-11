from enum import Enum
from nostr_sdk import Kind


class EventKind(Enum):
    DM = 4
    ZAP = 9735
    DVM_NIP89_ANNOUNCEMENT = 31990
    DVM_FEEDBACK = 7000

    DVM_REQUEST_RANGE_START = 5000
    DVM_REQUEST_RANGE_END = 5999
    DVM_RESULT_RANGE_START = 6000
    DVM_RESULT_RANGE_END = 6999

    @staticmethod
    def get_bad_dvm_kinds():
        """
        For some reason, these kinds are not DVM events and should be ignored.
        """

        bad_kinds = [5666, 6666, 5969, 6969]

        return bad_kinds

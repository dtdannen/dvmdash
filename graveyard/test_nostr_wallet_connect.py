import asyncio
from dotenv import load_dotenv
import os

from nostr_sdk import (
    init_logger,
    LogLevel,
    NostrWalletConnectUri,
    Nwc,
    MakeInvoiceRequestParams,
)

load_dotenv()

nostr_wallet_connect_uri = NostrWalletConnectUri.parse(os.getenv("NWC_URI"))


async def main():
    # Init logger
    init_logger(LogLevel.INFO)

    # Initialize NWC client
    nwc = Nwc(nostr_wallet_connect_uri)

    invoice_request_params = MakeInvoiceRequestParams(
        amount=3000, description="test payment", description_hash="test", expiry=10000
    )

    invoice = await nwc.make_invoice(invoice_request_params)
    print(invoice.invoice)


if __name__ == "__main__":
    asyncio.run(main())

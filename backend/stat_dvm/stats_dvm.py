from ezdvm import EZDVM


class StatsDVM(EZDVM):
    def __init__(self):
        # choose the job request kinds you will listen and respond to
        super().__init__(kinds=[5050])

    async def do_work(self, event):
        return "Hello World!"


if __name__ == "__main__":
    hello_world_dvm = HelloWorldDVM()
    hello_world_dvm.add_relay("wss://relay.damus.io")
    hello_world_dvm.add_relay("wss://relay.primal.net")
    hello_world_dvm.add_relay("wss://nos.lol")
    hello_world_dvm.add_relay("wss://nostr-pub.wellorder.net")
    hello_world_dvm.start()

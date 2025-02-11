from ezdvm import EZDVM


class StatsDVM(EZDVM):
    def __init__(self):
        # choose the job request kinds you will listen and respond to
        super().__init__(kinds=[5050])

    async def do_work(self, event):
        return


if __name__ == "__main__":
    hello_world_dvm = StatsDVM()
    hello_world_dvm.add_relay("wss://localhost:8081")
    hello_world_dvm.start()

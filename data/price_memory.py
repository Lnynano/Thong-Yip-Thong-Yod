price_memory = []

MAX_MEMORY = 60


def add_price(price):

    global price_memory

    price_memory.append(price)

    if len(price_memory) > MAX_MEMORY:

        price_memory.pop(0)


def get_price_history():

    return price_memory.copy()


def split_history():

    history = get_price_history()

    if len(history) < 60:

        return history, []

    past_40 = history[:40]

    recent_20 = history[40:]

    return past_40, recent_20
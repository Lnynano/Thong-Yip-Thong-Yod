price_memory = []

MAX_MEMORY = 30


def add_price(price):

    global price_memory

    price_memory.append(price)

    if len(price_memory) > MAX_MEMORY:

        price_memory.pop(0)


def get_price_history():

    return price_memory.copy()


def split_history():

    history = get_price_history()

    if len(history) < 30:
        return history, []

    past_20 = history[:20]

    recent_10 = history[20:]

    return past_20, recent_10
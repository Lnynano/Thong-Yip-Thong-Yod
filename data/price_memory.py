price_memory = []

MAX_MEMORY = 120


def add_price(price):

    global price_memory

    price_memory.append(price)

    if len(price_memory) > MAX_MEMORY:

        price_memory.pop(0)


def get_price_history():

    return price_memory.copy()


def split_history():

    history = get_price_history()

    if len(history) < 40:

        return [], []

    if len(history) < 120:

        return history[:-20], history[-20:]

    past = history[:-40]

    recent = history[-40:]

    return past, recent
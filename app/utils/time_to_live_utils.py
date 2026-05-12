import random

def random_one_week():
    one_week_seconds = 7 * 24 * 60 * 60
    extra_random = random.randint(0, 21600)  # Thêm 0-6h ngẫu nhiên
    return one_week_seconds + extra_random

def random_one_day():
    one_day_seconds = 24 * 60 * 60
    extra_random = random.randint(0, 21600)
    return one_day_seconds + extra_random
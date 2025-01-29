total_seconds = 3665

def seconds_to_time(seconds):
    hours = seconds // 3600  # Получаем часы
    minutes = (seconds % 3600) // 60  # Получаем минуты
    seconds = seconds % 60  # Получаем секунды

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

if __name__ == "__main__":
    print(seconds_to_time(total_seconds))

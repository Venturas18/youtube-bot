# channel_graphics.py

import matplotlib.pyplot as plt
import io
import numpy as np

# Настройка Matplotlib для работы без графического интерфейса
import matplotlib

matplotlib.use('Agg')


def create_activity_graphs(views_list: list, likes_list: list, comments_list: list) -> io.BytesIO | None:
    """
    Рисует 2 графика (Просмотры и Вовлеченность) для 10 последних видео.
    Возвращает буфер с PNG изображением.
    """
    if not views_list:
        return None

    # Номер видео (от 1 до 10) для оси X
    video_numbers = range(1, len(views_list) + 1)
    labels = [f"Видео {i}" for i in video_numbers]

    # Создаем 2 графика (один над другим)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    # --- График 1: Просмотры (Столбчатая диаграмма) ---
    ax1.bar(labels, views_list, color='skyblue')
    ax1.set_title('Просмотры 10 последних видео', fontsize=16)
    ax1.set_ylabel('Кол-во просмотров', fontsize=12)
    ax1.grid(axis='y', linestyle='--', alpha=0.7)

    # Добавляем цифры над столбцами
    for i, v in enumerate(views_list):
        ax1.text(i, v + (max(views_list) * 0.01), f"{v:,}".replace(',', '.'), ha='center', color='black')

    # --- График 2: Вовлеченность (Лайки и Комментарии) ---
    width = 0.35  # ширина столбцов
    x = np.arange(len(labels))  # координаты X

    rects1 = ax2.bar(x - width / 2, likes_list, width, label='Лайки', color='green')
    rects2 = ax2.bar(x + width / 2, comments_list, width, label='Комментарии', color='orange')

    ax2.set_title('Вовлеченность (Лайки и Комментарии)', fontsize=16)
    ax2.set_ylabel('Количество', fontsize=12)
    ax2.set_xticks(x, labels)  # Устанавливаем метки X
    ax2.legend()
    ax2.grid(axis='y', linestyle='--', alpha=0.7)

    # Улучшаем читаемость (поворачиваем метки X, если их много)
    if len(labels) > 5:
        plt.setp(ax1.get_xticklabels(), rotation=15, ha="right")
        plt.setp(ax2.get_xticklabels(), rotation=15, ha="right")

    fig.tight_layout()

    # Сохраняем в буфер памяти
    image_buffer = io.BytesIO()
    plt.savefig(image_buffer, format='png', bbox_inches='tight')
    plt.close(fig)  # Очищаем фигуру
    image_buffer.seek(0)

    return image_buffer


# ⭐️⭐️⭐️ ВОЗВРАЩЕННАЯ ВЕРСИЯ (СВЕТЛАЯ) ⭐️⭐️⭐️
def create_heatmap_graph(grid_data: np.ndarray) -> io.BytesIO | None:
    """
    Рисует теплокарту (heatmap) 7x24 на основе сетки данных.
    (Светлая тема, зеленая палитра)
    """
    if grid_data is None:
        return None

    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    hours = [f"{h:02d}" for h in range(24)]

    # ⭐️ ВОЗВРАЩАЕМ СТАНДАРТНЫЙ СТИЛЬ
    plt.style.use('default')

    fig, ax = plt.subplots(figsize=(16, 6))

    # ⭐️ ВОЗВРАЩАЕМ ЗЕЛЕНУЮ ПАЛИТРУ
    im = ax.imshow(grid_data, cmap="Greens")

    # Настраиваем оси
    ax.set_xticks(np.arange(len(hours)))
    ax.set_yticks(np.arange(len(days)))
    ax.set_xticklabels(hours)
    ax.set_yticklabels(days)

    # Добавляем цифры в ячейки
    for i in range(len(days)):
        for j in range(len(hours)):
            count = grid_data[i, j]
            if count > 0:
                # Меняем цвет текста на белый для темных ячеек
                color = "white" if count > grid_data.max() / 2 else "black"
                ax.text(j, i, int(count), ha="center", va="center", color=color)

    ax.set_title("Теплокарта публикаций (по 50 последним видео)")
    ax.set_xlabel("Время суток (UTC)")
    fig.colorbar(im, ax=ax, label="Кол-во видео")
    fig.tight_layout()

    # Сохраняем в буфер
    image_buffer = io.BytesIO()
    plt.savefig(image_buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    image_buffer.seek(0)

    return image_buffer
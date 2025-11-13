# trends_analyzer.py

import asyncio
from pytrends.request import TrendReq
import matplotlib.pyplot as plt
import io  # Для работы с файлами в памяти

# Настройка Matplotlib для работы без графического интерфейса (важно для серверов)
import matplotlib

matplotlib.use('Agg')


async def analyze_google_trends(keyword: str) -> dict:
    """
    Анализирует запрос в Google Trends, строит график и ищет похожие запросы.
    """
    try:
        # 1. Запускаем pytrends в асинхронном режиме (чтобы не блокировать бота)
        pytrends = TrendReq(hl='en-US', tz=360)

        loop = asyncio.get_event_loop()

        # 2. Создаем "полезную нагрузку" (payload)
        await loop.run_in_executor(
            None,  # Используем стандартный ThreadPoolExecutor
            lambda: pytrends.build_payload(
                kw_list=[keyword],
                timeframe='today 3-m',  # "today 3-m" = "Последние 90 дней"
                geo='',  # "Весь мир"
                gprop='youtube'  # Искать только на YouTube
            )
        )

        # 3. Получаем данные для графика (Interest Over Time)
        data = await loop.run_in_executor(None, pytrends.interest_over_time)

        if data.empty:
            return {"error": "По этому запросу нет данных о трендах на YouTube."}

        # 4. Получаем данные по регионам
        regions_data = await loop.run_in_executor(
            None,
            lambda: pytrends.interest_by_region(resolution='COUNTRY')
        )
        # Сортируем и берем топ-1
        top_country = regions_data[keyword].idxmax() if not regions_data.empty else "N/A"

        # 5. Получаем похожие запросы
        related_queries_data = await loop.run_in_executor(None, pytrends.related_queries)
        related_queries_raw = related_queries_data[keyword].get('top', None)

        related_queries = []
        if related_queries_raw is not None:
            # Берем первые 5
            related_queries = list(related_queries_raw['query'].head(5))

        # 6. Рисуем график
        plt.figure(figsize=(10, 5))
        plt.plot(data[keyword], label=f'Интерес к "{keyword}" на YouTube')
        plt.title('Динамика популярности за 90 дней')
        plt.xlabel('Дата')
        plt.ylabel('Интерес (0-100)')
        plt.legend()
        plt.grid(True)

        # 7. Сохраняем график в буфер памяти (вместо файла)
        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format='png', bbox_inches='tight')
        plt.close()  # Очищаем фигуру

        image_buffer.seek(0)  # "Перематываем" буфер в начало

        return {
            "image": image_buffer,
            "top_country": top_country,
            "related_queries": related_queries
        }

    except Exception as e:
        # ⬇️ --- ИСПРАВЛЕНИЕ ЗДЕСЬ --- ⬇️
        # Pytrends может выдать ошибку, если запросов слишком много
        # Ищем '429' в тексте ошибки, а не 'response 429'
        if "429" in str(e):
            return {"error": "Слишком много запросов к Google Trends. Пожалуйста, попробуйте через 5-10 минут."}
        # ⬆️ --- КОНЕЦ ИСПРАВЛЕНИЯ --- ⬆️
        return {"error": f"Неизвестная ошибка при анализе трендов: {e}"}
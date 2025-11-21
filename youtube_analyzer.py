# youtube_analyzer.py

import re
import datetime
import asyncio
import numpy as np  # ⭐️ НОВЫЙ ИМПОРТ
from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY
import httpx


class YouTubeAnalyzer:
    """
    Класс для взаимодействия с YouTube Data API v3
    и сторонним API 'Return YouTube Dislike'.
    """

    def __init__(self):
        # Инициализация сервиса YouTube API
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

        # Клиент для API Return YouTube Dislike
        self.ryd_client = httpx.AsyncClient(
            base_url="https://returnyoutubedislikeapi.com",
            timeout=5.0
        )

    # --- Утилитарные функции для извлечения ID ---

    def _extract_video_id(self, url: str) -> str | None:
        match_standard = re.search(r'(?<=v=)[a-zA-Z0-9_-]+', url)
        if match_standard: return match_standard.group(0)
        match_short = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', url)
        if match_short: return match_short.group(1)
        match_shorts = re.search(r'/shorts/([a-zA-Z0-9_-]+)', url)
        if match_shorts: return match_shorts.group(1)
        return None

    def _extract_channel_info(self, text_input: str) -> dict | None:
        match_raw_handle = re.fullmatch(r'@([a-zA-Z0-9_.-]+)', text_input.strip())
        if match_raw_handle: return {'type': 'search_query', 'value': match_raw_handle.group(1)}
        match_id = re.search(r'/channel/([a-zA-Z0-9_-]+)', text_input)
        if match_id: return {'type': 'id', 'value': match_id.group(1)}
        match_user = re.search(r'/user/([a-zA-Z0-9_-]+)', text_input)
        if match_user: return {'type': 'username', 'value': match_user.group(1)}
        match_handle = re.search(r'/@([a-zA-Z0-9_.-]+)', text_input)
        if match_handle: return {'type': 'search_query', 'value': match_handle.group(1)}
        match_custom = re.search(r'/c/([a-zA-Z0-9_.-]+)', text_input)
        if match_custom: return {'type': 'search_query', 'value': match_custom.group(1)}
        if not (text_input.startswith('http') or text_input.startswith('www.') or '/' in text_input):
            clean_input = text_input.replace('@', '').strip()
            if clean_input: return {'type': 'search_query', 'value': clean_input}
        return None

    # --- Функционал "Аналитика видео" --- (Без изменений)

    async def _get_ryd_dislikes(self, video_id: str) -> str:
        try:
            response = await self.ryd_client.get(f"/votes?videoId={video_id}")
            response.raise_for_status()
            data = response.json()
            dislikes = data.get('dislikes', 'N/A')
            return str(dislikes) if isinstance(dislikes, int) else 'N/A'
        except Exception:
            return 'N/A'

    async def _get_category_name(self, category_id: str) -> str:
        try:
            request = self.youtube.videoCategories().list(part="snippet", regionCode="US")
            response = request.execute()
            for item in response['items']:
                if item['id'] == category_id: return item['snippet']['title']
            return "Неизвестно"
        except Exception:
            return "Ошибка загрузки категории"

    def _get_best_thumbnail_url(self, thumbnails: dict) -> str | None:
        if 'maxres' in thumbnails: return thumbnails['maxres']['url']
        if 'standard' in thumbnails: return thumbnails['standard']['url']
        if 'high' in thumbnails: return thumbnails['high']['url']
        if 'medium' in thumbnails: return thumbnails['medium']['url']
        if 'default' in thumbnails: return thumbnails['default']['url']
        return None

    async def get_video_data_by_id(self, video_id: str) -> dict | None:
        if not video_id: return {"error": "Неверный ID видео."}
        try:
            request = self.youtube.videos().list(part="snippet,statistics", id=video_id)
            response = request.execute()
            if not response['items']: return {"error": "Видео не найдено или недоступно."}
            item = response['items'][0]
            snippet = item['snippet']
            stats = item.get('statistics', {})
            geo_info = snippet.get('countryCode', 'N/A')
            dislike_count = await self._get_ryd_dislikes(video_id)
            thumbnail_url = self._get_best_thumbnail_url(snippet.get('thumbnails', {}))
            data = {
                "title": snippet['title'], "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": snippet['publishedAt'], "category_id": snippet['categoryId'],
                "description": snippet['description'], "tags": snippet.get('tags', []),
                "geo_code": geo_info, "views": stats.get('viewCount', '0'),
                "likes": stats.get('likeCount', '0'), "dislikes": dislike_count,
                "comments": stats.get('commentCount', '0'), "thumbnail_url": thumbnail_url
            }
            category_name = await self._get_category_name(data['category_id'])
            data['category_name'] = category_name
            return data
        except Exception as e:
            return {"error": f"Ошибка при обращении к YouTube API: {e}"}

    async def analyze_video(self, video_url: str) -> dict | None:
        video_id = self._extract_video_id(video_url)
        if not video_id: return {"error": "Не удалось найти ID видео в ссылке. Проверьте формат."}
        return await self.get_video_data_by_id(video_id)

    # --- "Аналитика канала" ---

    async def _get_channel_id_by_search(self, query: str) -> str | None:
        try:
            request = self.youtube.search().list(part="snippet", q=query, type="channel", maxResults=1)
            response = request.execute()
            if response.get('items'): return response['items'][0]['snippet']['channelId']
            return None
        except Exception:
            return None

    async def _get_uploads_playlist_id(self, channel_id: str) -> str | None:
        """Вспомогательная функция для получения ID плейлиста 'Uploads'."""
        try:
            request_details = self.youtube.channels().list(
                part="contentDetails",
                id=channel_id
            )
            response_details = request_details.execute()
            if not response_details.get('items'):
                return None
            return response_details['items'][0]['contentDetails'].get('relatedPlaylists', {}).get('uploads')
        except Exception:
            return None

    async def get_recent_video_stats(self, channel_id: str) -> dict:
        """
        Собирает статистику (просмотры, лайки, комменты)
        по 10 последним видео для "Здоровья канала".
        """
        uploads_playlist_id = await self._get_uploads_playlist_id(channel_id)
        if not uploads_playlist_id:
            return {"error": "У канала нет плейлиста загрузок."}

        request_videos = self.youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=10
        )
        response_videos = request_videos.execute()
        video_ids = [item['contentDetails']['videoId'] for item in response_videos.get('items', [])]

        if not video_ids: return {"error": "На канале нет недавних видео."}

        request_stats = self.youtube.videos().list(part="statistics", id=",".join(video_ids))
        response_stats = request_stats.execute()

        views_list, likes_list, comments_list = [], [], []
        for video_stat in response_stats.get('items', []):
            stats = video_stat.get('statistics', {})
            views_list.append(int(stats.get('viewCount', 0)))
            likes_list.append(int(stats.get('likeCount', 0)))
            comments_list.append(int(stats.get('commentCount', 0)))

        if not views_list: return {"error": "Не удалось собрать статистику по видео."}

        return {"views_list": views_list, "likes_list": likes_list, "comments_list": comments_list}

    async def analyze_channel(self, channel_input: str) -> dict | None:
        """
        Получает и обрабатывает ГЛУБОКУЮ статистику для конкретного канала.
        """
        channel_info = self._extract_channel_info(channel_input)
        if not channel_info:
            return {
                "error": "Не удалось распознать формат. Введите ссылку на канал, псевдоним (@vdud) или просто название."}

        try:
            request_args = {"part": "snippet,statistics"}
            channel_id = None
            if channel_info['type'] == 'id':
                request_args['id'] = channel_info['value']
                channel_id = channel_info['value']
            elif channel_info['type'] == 'username':
                request_args['forUsername'] = channel_info['value']
            elif channel_info['type'] == 'search_query':
                channel_id = await self._get_channel_id_by_search(channel_info['value'])
                if not channel_id:
                    return {"error": f"Не удалось найти канал по имени '{channel_info['value']}'."}
                request_args['id'] = channel_id

            request = self.youtube.channels().list(**request_args)
            response = request.execute()
            if not response.get('items'): return {"error": "Канал не найден или недоступен."}

            item = response['items'][0]
            snippet, stats = item['snippet'], item.get('statistics', {})
            if not channel_id: channel_id = item['id']

            data = {
                "channel_id": channel_id, "title": snippet['title'],
                "url": f"https://www.youtube.com/channel/{channel_id}",
                "published_at": snippet['publishedAt'],
                "video_count": stats.get('videoCount', '0'),
                "view_count": stats.get('viewCount', '0'),
                "subscriber_count": stats.get('subscriberCount', '0')
            }

            health_data = await self.get_recent_video_stats(channel_id)

            if 'error' not in health_data:
                num_videos = len(health_data['views_list'])
                total_views = sum(health_data['views_list'])
                total_likes = sum(health_data['likes_list'])
                total_comments = sum(health_data['comments_list'])
                data['avg_views'] = int(total_views / num_videos)
                data['avg_likes'] = int(total_likes / num_videos)
                data['avg_comments'] = int(total_comments / num_videos)
                data[
                    'er'] = f"{((total_likes + total_comments) / total_views) * 100:.2f}" if total_views > 0 else "0.00"

            return data

        except Exception as e:
            return {"error": f"Ошибка при обращении к YouTube API: {e}"}

    # ⭐️⭐️⭐️ НОВАЯ ФУНКЦИЯ ДЛЯ ТЕПЛОКАРТЫ ⭐️⭐️⭐️
    async def get_publication_heatmap_data(self, channel_id: str) -> dict:
        """
        Собирает данные о времени публикаций 50 последних видео
        для построения теплокарты.
        """
        try:
            # 1. Найти плейлист "Uploads"
            uploads_playlist_id = await self._get_uploads_playlist_id(channel_id)
            if not uploads_playlist_id:
                return {"error": "У канала нет плейлиста загрузок."}

            # 2. Получить 50 последних видео
            request_videos = self.youtube.playlistItems().list(
                part="snippet",  # Нам нужен 'snippet' для 'publishedAt'
                playlistId=uploads_playlist_id,
                maxResults=50  # API отдает до 50 за раз
            )
            response_videos = request_videos.execute()

            items = response_videos.get('items', [])
            if not items:
                return {"error": "На канале нет недавних видео."}

            # 3. Создать сетку 7x24
            # (7 дней, 0=Пн ... 6=Вс; 24 часа, 0-23)
            grid = np.zeros((7, 24), dtype=int)

            day_map = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

            # 4. Заполнить сетку
            for item in items:
                pub_str = item['snippet']['publishedAt']
                # Конвертируем в datetime (с учетом UTC)
                dt = datetime.datetime.fromisoformat(pub_str.replace('Z', '+00:00'))

                weekday = dt.weekday()  # 0 = Понедельник
                hour = dt.hour  # 0 = 00:00 - 00:59

                grid[weekday, hour] += 1

            # 5. Найти самый "горячий" слот
            max_idx = np.unravel_index(np.argmax(grid), grid.shape)
            report_day = day_map[max_idx[0]]
            report_hour = f"{max_idx[1]:02d}:00 - {max_idx[1] + 1:02d}:00"

            report = (
                f"<b>Отчет по 50 последним видео:</b>\n"
                f"├ <b>Самый частый день:</b> {report_day}\n"
                f"└ <b>Самое \"горячее\" время (UTC):</b> {report_hour}"
            )

            return {
                "grid": grid,
                "report": report
            }

        except Exception as e:
            return {"error": f"Ошибка при сборе данных для теплокарты: {e}"}

    # ⭐️⭐️⭐️ ФУНКЦИЯ ДЛЯ EXCEL ⭐️⭐️⭐️
    async def get_most_popular_video_in_range(self, channel_id: str, days_ago: int) -> str:
        try:
            start_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
            published_after = start_date.isoformat()
            request = self.youtube.search().list(
                part="snippet", channelId=channel_id,
                publishedAfter=published_after, order="viewCount",
                type="video", maxResults=1
            )
            response = request.execute()
            if response.get('items'):
                video_id = response['items'][0]['id']['videoId']
                return f"https://youtu.be/{video_id}"
            else:
                return "N/A"
        except Exception:

            return "Ошибка API"

# ⭐️⭐️⭐️ НОВАЯ ФУНКЦИЯ: СБОР ВСЕХ НАЗВАНИЙ ⭐️⭐️⭐️
    async def get_all_video_titles(self, channel_input: str) -> dict:
        """
        Собирает названия ВСЕХ видео с канала через пагинацию.
        Возвращает список строк (названий).
        """
        # 1. Получаем ID канала
        channel_info = self._extract_channel_info(channel_input)
        if not channel_info:
            return {"error": "Неверная ссылка или ID канала."}
        
        # Если это username или search query, нужно сначала найти ID канала
        channel_id = None
        if channel_info['type'] == 'id':
            channel_id = channel_info['value']
        else:
            # Используем уже существующий метод для поиска ID
            try:
                # Здесь немного дублируем логику analyze_channel для получения ID
                if channel_info['type'] == 'username':
                    req = self.youtube.channels().list(part="id", forUsername=channel_info['value'])
                else: # search_query
                    channel_id = await self._get_channel_id_by_search(channel_info['value'])
                    # Если нашли через поиск, запрос ниже не нужен
                
                if not channel_id and channel_info['type'] == 'username':
                    resp = req.execute()
                    if resp.get('items'):
                        channel_id = resp['items'][0]['id']
            except Exception as e:
                return {"error": f"Ошибка поиска канала: {e}"}

        if not channel_id:
            return {"error": "Канал не найден."}

        # 2. Получаем ID плейлиста "Uploads"
        uploads_id = await self._get_uploads_playlist_id(channel_id)
        if not uploads_id:
            return {"error": "Не удалось найти плейлист загрузок."}

        # 3. Цикл по всем страницам (Pagination)
        all_titles = []
        next_page_token = None
        
        try:
            while True:
                request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_id,
                    maxResults=50, # Максимум за 1 запрос
                    pageToken=next_page_token
                )
                response = request.execute()
                
                items = response.get('items', [])
                if not items:
                    break

                for item in items:
                    title = item['snippet']['title']
                    # Можно добавить дату или ссылку, если нужно:
                    # video_id = item['snippet']['resourceId']['videoId']
                    all_titles.append(title)

                next_page_token = response.get('nextPageToken')
                
                # Если токена следующей страницы нет, значит мы дошли до конца
                if not next_page_token:
                    break
                    
                # Маленькая пауза, чтобы не заблокировать бота намертво при 10к видео
                await asyncio.sleep(0.05)

            return {
                "channel_title": f"Channel_{channel_id}", # Или получить реальное имя отдельным запросом
                "titles": all_titles
            }

        except Exception as e:
            return {"error": f"Ошибка при сборе видео: {e}"}

# ⭐️⭐️⭐️ НОВАЯ ФУНКЦИЯ: СБОР ВСЕХ НАЗВАНИЙ ⭐️⭐️⭐️
    async def get_all_video_titles(self, channel_input: str) -> dict:
        """
        Собирает названия ВСЕХ видео с канала через пагинацию.
        Возвращает список строк (названий).
        """
        # 1. Получаем ID канала
        channel_info = self._extract_channel_info(channel_input)
        if not channel_info:
            return {"error": "Неверная ссылка или ID канала."}
        
        # Если это username или search query, нужно сначала найти ID канала
        channel_id = None
        if channel_info['type'] == 'id':
            channel_id = channel_info['value']
        else:
            # Используем уже существующий метод для поиска ID
            try:
                # Здесь немного дублируем логику analyze_channel для получения ID
                if channel_info['type'] == 'username':
                    req = self.youtube.channels().list(part="id", forUsername=channel_info['value'])
                else: # search_query
                    channel_id = await self._get_channel_id_by_search(channel_info['value'])
                    # Если нашли через поиск, запрос ниже не нужен
                
                if not channel_id and channel_info['type'] == 'username':
                    resp = req.execute()
                    if resp.get('items'):
                        channel_id = resp['items'][0]['id']
            except Exception as e:
                return {"error": f"Ошибка поиска канала: {e}"}

        if not channel_id:
            return {"error": "Канал не найден."}

        # 2. Получаем ID плейлиста "Uploads"
        uploads_id = await self._get_uploads_playlist_id(channel_id)
        if not uploads_id:
            return {"error": "Не удалось найти плейлист загрузок."}

        # 3. Цикл по всем страницам (Pagination)
        all_titles = []
        next_page_token = None
        
        try:
            while True:
                request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_id,
                    maxResults=50, # Максимум за 1 запрос
                    pageToken=next_page_token
                )
                response = request.execute()
                
                items = response.get('items', [])
                if not items:
                    break

                for item in items:
                    title = item['snippet']['title']
                    # Можно добавить дату или ссылку, если нужно:
                    # video_id = item['snippet']['resourceId']['videoId']
                    all_titles.append(title)

                next_page_token = response.get('nextPageToken')
                
                # Если токена следующей страницы нет, значит мы дошли до конца
                if not next_page_token:
                    break
                    
                # Маленькая пауза, чтобы не заблокировать бота намертво при 10к видео
                await asyncio.sleep(0.05)

            return {
                "channel_title": f"Channel_{channel_id}", # Или получить реальное имя отдельным запросом
                "titles": all_titles
            }

        except Exception as e:
            return {"error": f"Ошибка при сборе видео: {e}"}

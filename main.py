# main.py

import logging
import html
import io
import os
import asyncio 
from aiohttp import web  
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from config import TELEGRAM_BOT_TOKEN
from youtube_analyzer import YouTubeAnalyzer
from trends_analyzer import analyze_google_trends
from excel_generator import ExcelGenerator
from channel_graphics import create_activity_graphs, create_heatmap_graph
from datetime import datetime
import httpx
import numpy as np

logging.basicConfig(level=logging.INFO)

# 🤖 Инициализация
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
youtube_analyzer = YouTubeAnalyzer()


# 📝 Определяем состояния для FSM
class UserStates(StatesGroup):
    waiting_for_video_link = State()
    waiting_for_channel_link = State()
    waiting_for_trends_query = State()
    waiting_for_niche_name = State()
    niche_analysis = State()
    waiting_for_all_titles_link = State() # 👈 НОВОЕ СОСТОЯНИЕ


# 🎛️ Функция для создания клавиатуры главного меню
def get_main_keyboard():
    buttons = [
        [types.InlineKeyboardButton(text="🎥 Аналитика видео", callback_data="analyze_video")],
        [types.InlineKeyboardButton(text="🔗 Аналитика канала", callback_data="analyze_channel")],
        # 👇 НОВАЯ КНОПКА 👇
        [types.InlineKeyboardButton(text="📑 Все названия видео", callback_data="get_all_titles")],
        [
            types.InlineKeyboardButton(text="📈 Google Trends", callback_data="cmd_trends"),
            types.InlineKeyboardButton(text="📊 Анализ ниши (Excel)", callback_data="cmd_excel")
        ]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


# 🎛️ Клавиатура для режима EXCEL
def get_niche_analysis_keyboard():
    buttons = [
        [KeyboardButton(text="💾 Готово и Скачать")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)
    return keyboard


def pluralize_canal(count: int) -> str:
    """Возвращает правильную форму слова 'канал'."""
    if count % 10 == 1 and count % 100 != 11:
        return "канал"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return "канала"
    else:
        return "каналов"


def format_number(num_str: str) -> str:
    """Превращает '1234567' в '1.234.567'."""
    try:
        num_int = int(num_str)
        return f"{num_int:,}".replace(',', '.')
    except (ValueError, TypeError):
        return str(num_str)


# --- 🟢 ОБРАБОТЧИКИ КОМАНД И МЕНЮ ---

@dp.message(Command("start"))
async def command_start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🙋 <b>Привет!</b>\n"
        "<b>Отправь ссылку на видео/канал для анализа.</b>\n\n"
        "<blockquote><b>👇Ниже список моих команд</b></blockquote>\n"
        "<code>/analyze_video</code> — (анализ видео)\n"
        "<code>/analyze_channel</code> — (анализ канала)\n"
        "<code>/get_titles</code> — (все названия)\n"
        "<code>/google_trends</code> — (тренд-запросы)\n"
        "<code>/excel</code> — (сбор в Excel)\n"
        "<code>/cancel</code> — (отмена)\n\n"
        "<blockquote><b>👇 Можешь выбрать действие кнопками ниже 👇</b></blockquote>"
    )
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )
    msg_to_delete = await message.answer(".", reply_markup=ReplyKeyboardRemove())
    await msg_to_delete.delete()


@dp.message(Command("cancel"))
async def command_cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Вы не в каком-либо режиме.")
        return
    await state.clear()
    await message.answer(
        "Действие отменено. Возвращаю в главное меню.",
        reply_markup=get_main_keyboard()
    )
    msg_to_delete = await message.answer(".", reply_markup=ReplyKeyboardRemove())
    await msg_to_delete.delete()


# --- Обработчики команд ---

@dp.message(Command("analyze_video"))
async def command_analyze_video(message: types.Message, state: FSMContext):
    await message.answer("🔗 <b>Вставьте ссылку видео</b>", parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_video_link)


@dp.message(Command("analyze_channel"))
async def command_analyze_channel(message: types.Message, state: FSMContext):
    await message.answer(
        "🔗 <b>Отправьте ссылку на канал, <code>@псевдоним</code> или название</b>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_for_channel_link)


@dp.callback_query(F.data == "analyze_video")
async def analyze_video_callback_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("🔗 <b>Вставьте ссылку видео</b>", parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_video_link)
    await callback_query.answer()


@dp.callback_query(F.data == "analyze_channel")
async def analyze_channel_callback_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer(
        "🔗 <b>Отправьте ссылку на канал, <code>@псевдоним</code> или название</b>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_for_channel_link)
    await callback_query.answer()


# --- 📑 СБОР ВСЕХ НАЗВАНИЙ (НОВЫЙ ФУНКЦИОНАЛ) ---

@dp.message(Command("get_titles"))
async def command_get_titles(message: types.Message, state: FSMContext):
    await message.answer("🔗 <b>Отправьте ссылку на канал для выгрузки ВСЕХ названий видео:</b>", parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_all_titles_link)


@dp.callback_query(F.data == "get_all_titles")
async def callback_get_titles(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("🔗 <b>Отправьте ссылку на канал для выгрузки ВСЕХ названий видео:</b>", parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_all_titles_link)
    await callback_query.answer()


@dp.message(UserStates.waiting_for_all_titles_link)
async def process_get_all_titles(message: types.Message, state: FSMContext):
    channel_input = message.text
    msg = await message.answer("⏳ Начинаю сбор всех названий... Это может занять время (зависит от кол-ва видео).")
    
    # Вызываем новую функцию
    result = await youtube_analyzer.get_all_video_titles(channel_input)
    
    if result.get("error"):
        await msg.edit_text(f"❌ Ошибка: {result['error']}")
        # Не сбрасываем состояние сразу, вдруг юзер ошибся ссылкой
        return

    titles = result['titles']
    count = len(titles)
    
    if count == 0:
        await msg.edit_text("На канале не найдено видео.")
        await state.clear()
        return

    # Формируем текст файла
    file_text = f"Список видео канала (Всего: {count})\n\n" + "\n".join(titles)
    
    # Создаем файл в памяти
    file_buffer = io.BytesIO(file_text.encode('utf-8'))
    # Используем безопасное имя файла
    safe_name = result.get('channel_title', 'channel').replace(' ', '_')
    file_name = f"titles_{safe_name}.txt"
    
    input_file = BufferedInputFile(file_buffer.getvalue(), filename=file_name)
    
    await msg.delete()
    await message.answer_document(
        input_file, 
        caption=f"✅ Готово! Собрано названий: <b>{count}</b>"
    )
    await state.clear()


# --- 📈 GOOGLE TRENDS ---

@dp.message(Command("google_trends"))
async def command_google_trends_handler(message: types.Message, state: FSMContext):
    await message.answer("Введите название (запрос для анализа):")
    await state.set_state(UserStates.waiting_for_trends_query)


@dp.callback_query(F.data == "cmd_trends")
async def trends_callback_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.answer("Введите название (запрос для анализа):")
    await state.set_state(UserStates.waiting_for_trends_query)
    await callback_query.answer()


@dp.message(UserStates.waiting_for_trends_query)
async def process_trends_query(message: types.Message, state: FSMContext):
    query = message.text
    msg = await message.answer(f"📈 Анализирую тренд для '{query}'... Это может занять до 30 секунд.")
    analysis_result = await analyze_google_trends(query)
    if analysis_result.get("error"):
        await msg.edit_text(f"❌ Ошибка: {analysis_result['error']}")
        await state.clear()
        return
    image_buffer = analysis_result["image"]
    top_country = analysis_result["top_country"]
    related_queries = analysis_result["related_queries"]
    photo = BufferedInputFile(image_buffer.getvalue(), filename=f"{query}_trend.png")
    related_list = "\n".join([f"• <code>{q}</code>" for q in related_queries])
    if not related_list:
        related_list = "Похожие запросы не найдены."
    caption = (f"🌍 <b>Страна, где запрос наиболее популярен:</b> {top_country}\n\n"
               f"🔥 <b>5 похожих запросов:</b>\n{related_list}")
    await msg.delete()
    await message.answer_photo(photo, caption=caption, parse_mode="HTML")
    await state.clear()


# --- 📊 EXCEL АНАЛИЗ НИШИ ---

@dp.message(Command("excel"))
async def start_excel_analysis_command(message: types.Message, state: FSMContext):
    text = ("📊 <b>Запущена excel сессия</b>\n\n"
            "<b><i>Введите названия файла (например хоррор истории)</i></b>")
    await message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_niche_name)


@dp.callback_query(F.data == "cmd_excel")
async def start_excel_analysis_button(callback_query: types.CallbackQuery, state: FSMContext):
    text = ("📊 <b>Запущена excel сессия</b>\n\n"
            "<b><i>Введите названия файла (например хоррор истории)</i></b>")
    await callback_query.message.answer(text, parse_mode="HTML")
    await state.set_state(UserStates.waiting_for_niche_name)
    await callback_query.answer()


@dp.message(UserStates.waiting_for_niche_name)
async def process_niche_name(message: types.Message, state: FSMContext):
    niche_name = message.text
    await state.update_data(niche_name=niche_name, channels=[])
    response_text = (
        f"✅ Файл <b>{html.escape(niche_name)}.xlsx</b> успешно создан.\n\n"
        f"Теперь отправляйте названия каналов, ссылки или <code>@псевдонимы</code> — я сохраню их в таблицу автоматически.\n\n"
        f"<blockquote><b>Когда закончите, нажмите кнопку 💾 Готово и скачать внизу 👇</b></blockquote>"
    )
    await message.answer(
        response_text,
        parse_mode="HTML",
        reply_markup=get_niche_analysis_keyboard()
    )
    await state.set_state(UserStates.niche_analysis)


@dp.message(UserStates.niche_analysis, F.text == "💾 Готово и Скачать")
async def finish_excel_analysis(message: types.Message, state: FSMContext):
    msg = await message.answer(
        "⏳ Завершаю анализ... Генерирую Excel-файл...",
        reply_markup=ReplyKeyboardRemove()
    )
    state_data = await state.get_data()
    niche_name = state_data.get('niche_name', 'Анализ')
    channels_list = state_data.get('channels', [])
    if not channels_list:
        await msg.edit_text(
            "Вы не добавили ни одного канала. Отправка файла отменена.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    generator = ExcelGenerator(niche_name)
    for channel_data in channels_list:
        generator.add_channel_data(channel_data['category'], channel_data)
    file_buffer = generator.save_to_buffer()
    file_to_send = BufferedInputFile(
        file_buffer.getvalue(),
        filename=f"{niche_name}.xlsx"
    )
    await msg.delete()
    await message.answer_document(
        file_to_send,
        caption=f"Ваш анализ ниши '{niche_name}' готов."
    )
    await state.clear()


@dp.message(UserStates.niche_analysis)
async def process_niche_channel_input(message: types.Message, state: FSMContext):
    channel_input = message.text
    msg = await message.answer(f"🔍 Анализирую '{channel_input}'... (Шаг 1/4: Получение данных канала)")
    channel_data = await youtube_analyzer.analyze_channel(channel_input)
    if channel_data.get("error"):
        await msg.edit_text(f"❌ Ошибка: {channel_data['error']}")
        return
    try:
        subs_count = int(channel_data.get('subscriber_count', 0))
    except ValueError:
        subs_count = 0
    if subs_count >= 100000:
        category_key, category_name = 'whales', "Киты"
    elif subs_count >= 1000:
        category_key, category_name = 'small', "Маленькие каналы"
    else:
        category_key, category_name = 'tiny', "Совсем маленькие"
    channel_id = channel_data['channel_id']
    await msg.edit_text(f"... (Шаг 2/4: Поиск топ-видео за 7 дней)")
    idea_7d = await youtube_analyzer.get_most_popular_video_in_range(channel_id, 7)
    await msg.edit_text(f"... (Шаг 3/4: Поиск топ-видео за 14 дней)")
    idea_14d = await youtube_analyzer.get_most_popular_video_in_range(channel_id, 14)
    await msg.edit_text(f"... (Шаг 4/4: Поиск топ-видео за 30 дней)")
    idea_30d = await youtube_analyzer.get_most_popular_video_in_range(channel_id, 30)
    state_data = await state.get_data()
    channels_list = state_data.get('channels', [])
    new_entry = {
        'category': category_key, 'name': channel_data['title'],
        'url': channel_data['url'], 'subs': subs_count,
        'views': int(channel_data.get('view_count', 0)),
        'idea_7d': idea_7d, 'idea_14d': idea_14d, 'idea_30d': idea_30d
    }
    channels_list.append(new_entry)
    await state.update_data(channels=channels_list)
    count = len(channels_list)
    canal_word = pluralize_canal(count)
    response_text = (
        f"✅ Канал {html.escape(channel_data['title'])} добавлен в категорию «{category_name}».\n\n"
        f"📌 Всего в файле: {count} {canal_word}.\n"
        f"Отправьте следующий канал\n\n"
        f"или нажмите 💾 Готово и скачать 👇"
    )
    await msg.edit_text(response_text, parse_mode="HTML")


# --- 🔎 ОСНОВНЫЕ ФУНКЦИИ АНАЛИЗА ---

async def get_country_info(code: str) -> str:
    if code == 'N/A':
        return ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"https://restcountries.com/v3.1/alpha/{code}")
            response.raise_for_status()
            data = response.json()[0]
            country_name = data['name']['common']
            flag_emoji = "".join([chr(0x1F1E6 + ord(char) - ord('A')) for char in code.upper()])
            return f"{flag_emoji} {country_name} ({code})"
    except Exception:
        return f"({code})"


def generate_metadata_content(data: dict) -> str:
    title = data.get('title', 'N/A')
    video_id = data.get('video_id', 'N/A')
    video_url = data.get('url', 'N/A')
    published_dt = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
    publish_date = published_dt.strftime("%Y-%m-%d %H:%M:%S")
    views = format_number(data.get('views', 'N/A'))
    category = data.get('category_name', 'N/A')
    tags = ", ".join(data.get('tags', []))
    description = data.get('description', '')
    content = (f"[TITLE]:       {title}\n[VIDEO ID]:    {video_id}\n[VIDEO URL]:   {video_url}\n"
               f"[PUBLISH DATE]: {publish_date}\n[VIEWS COUNT]: {views}\n[CATEGORY]:    {category}\n\n"
               f"[KEYWORDS (TAGS)]:\n{tags}\n\n[DESCRIPTION]:\n{description}\n")
    return content


async def run_video_analysis(message: types.Message, video_url: str, state: FSMContext):
    """
    Основная функция для анализа видео.
    """
    msg = await message.answer("🔍 Анализирую видео... Это может занять несколько секунд.")
    data = await youtube_analyzer.analyze_video(video_url)
    if data.get("error"):
        await msg.edit_text(f"❌ Ошибка анализа: {data['error']}")
        await state.clear()
        return
    video_id = data['video_id']
    published_dt = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
    formatted_date = published_dt.strftime("%d.%m.%Y %H:%M:%S")
    geo_info_text = await get_country_info(data['geo_code'])
    geo_line = f"├ ГЕО: {geo_info_text}" if geo_info_text else ""
    safe_title = html.escape(data['title'])
    safe_description = html.escape(data['description'])
    safe_tags = html.escape("\n".join(data['tags']))
    views_f = format_number(data['views'])
    likes_f = format_number(data['likes'])
    dislikes_f = format_number(data['dislikes'])
    comments_f = format_number(data['comments'])
    lines = [f"🎥 <b><a href='{data['url']}'>{safe_title}</a></b>",
             f"├ Время публикации: <code>{formatted_date}</code>",
             f"├ Категория: <code>{data['category_name']}</code>"]
    if geo_line:
        lines.append(geo_line)
    lines.append(
        f"└ ▶️: <code>{views_f}</code> │👍: <code>{likes_f}</code> │👎: <code>{dislikes_f}</code> 💬: <code>{comments_f}</code>")
    lines.extend(["", f"📝│<b>Описания</b>", f"<blockquote>{safe_description}</blockquote>", "", f"🏷│<b>Теги</b>",
                  f"<pre>{safe_tags}</pre>"])
    output_message = "\n".join(lines)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📤 Скачать метаданные", callback_data=f"download_meta:{video_id}"),
         types.InlineKeyboardButton(text="🖼️ Скачать превью", callback_data=f"download_thumb:{video_id}")]])
    await msg.delete()
    await message.answer(output_message, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)
    await state.clear()


async def run_channel_analysis(message: types.Message, channel_input: str, state: FSMContext):
    """
    Основная функция для анализа канала.
    """
    msg = await message.answer("🔍 Анализирую канал... (Шаг 1/4: Поиск канала)")
    data = await youtube_analyzer.analyze_channel(channel_input)
    if data.get("error"):
        await msg.edit_text(f"❌ Ошибка анализа: {data['error']}")
        await state.clear()
        return
    published_dt = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
    formatted_date = published_dt.strftime("%d.%m.%Y")
    safe_title = html.escape(data['title'])
    video_count_f = format_number(data.get('video_count', 'N/A'))
    view_count_f = format_number(data.get('view_count', 'N/A'))
    lines = [f"👤<b>Канал: <a href='{data['url']}'>{safe_title}</a></b>",
             f"├ Возраст канала: <code>{formatted_date}</code>",
             f"├ Общее кол-во видео: <code>{video_count_f}</code>",
             f"└ Общее кол-во просмотров: <code>{view_count_f}</code>"]

    buttons = []
    if 'avg_views' in data:
        avg_views_f = format_number(data['avg_views'])
        avg_likes_f = format_number(data['avg_likes'])
        avg_comments_f = format_number(data['avg_comments'])
        lines.append("\n❤️ <b>Здоровье канала (на основе 10 последних видео):</b>")
        lines.append(f"├ Средн. просмотров на видео: <code>{avg_views_f}</code>")
        lines.append(f"├ Средн. лайков на видео: <code>{avg_likes_f}</code>")
        lines.append(f"├ Средн. комментариев на видео: <code>{avg_comments_f}</code>")
        lines.append(f"└ <b>ER (Коэфф. вовлеченности):</b> <code>{data['er']} %</code>")

        buttons.append(
            types.InlineKeyboardButton(
                text="📊 Показать график",
                callback_data=f"show_graphs:{data['channel_id']}"
            )
        )
    else:
        lines.append("\n<i>Не удалось рассчитать 'здоровье канала' (возможно, нет недавних видео).</i>")

    buttons.append(
        types.InlineKeyboardButton(
            text="📅 Показать график публикаций",
            callback_data=f"show_heatmap:{data['channel_id']}"
        )
    )

    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None

    output_message = "\n".join(lines)
    await msg.edit_text(
        output_message,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )
    await state.clear()


# --- 🔎 ОБРАБОТЧИКИ СОСТОЯНИЙ ---

@dp.message(UserStates.waiting_for_video_link)
async def process_video_link(message: types.Message, state: FSMContext):
    await run_video_analysis(message, message.text, state)


@dp.message(UserStates.waiting_for_channel_link)
async def process_channel_link(message: types.Message, state: FSMContext):
    await run_channel_analysis(message, message.text, state)


# --- УМНЫЙ ОБРАБОТЧИК ---
@dp.message(F.text, StateFilter(None))
async def auto_detect_link_handler(message: types.Message, state: FSMContext):
    text = message.text.strip()
    video_id = youtube_analyzer._extract_video_id(text)
    if video_id:
        await run_video_analysis(message, text, state)
        return
    channel_info = youtube_analyzer._extract_channel_info(text)
    if channel_info:
        await run_channel_analysis(message, text, state)
        return
    await message.answer("Я не распознал ссылку. Попробуйте еще раз или используйте команду.")


# --- 📤 ОБРАБОТЧИКИ КНОПОК СКАЧИВАНИЯ ---

@dp.callback_query(F.data.startswith("download_meta:"))
async def download_metadata_handler(callback_query: types.CallbackQuery):
    video_id = callback_query.data.split(":")[-1]
    await callback_query.answer("⏳ Готовлю TXT файл...")
    data = await youtube_analyzer.get_video_data_by_id(video_id)
    if data.get("error"):
        await callback_query.message.answer(f"❌ Ошибка при получении данных для файла: {data['error']}")
        return
    content = generate_metadata_content(data)
    file_content = BufferedInputFile(content.encode('utf-8'), filename=f"{video_id}_metadata.txt")
    await callback_query.message.answer_document(file_content)


@dp.callback_query(F.data.startswith("download_thumb:"))
async def download_thumbnail_handler(callback_query: types.CallbackQuery):
    video_id = callback_query.data.split(":")[-1]
    await callback_query.answer("⏳ Загружаю превью...")
    data = await youtube_analyzer.get_video_data_by_id(video_id)
    if data.get("error"):
        await callback_query.message.answer(f"❌ Ошибка: {data['error']}")
        return
    thumb_url = data.get("thumbnail_url")
    if not thumb_url:
        await callback_query.message.answer(f"❌ Не удалось найти превью для этого видео.")
        return
    try:
        await callback_query.message.answer_photo(
            photo=thumb_url,
            caption=f"Превью для: {data['title']}"
        )
    except Exception as e:
        await callback_query.message.answer(f"❌ Не удалось отправить фото. Ошибка: {e}")


@dp.callback_query(F.data.startswith("show_graphs:"))
async def download_graphs_handler(callback_query: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Показать график активности".
    """
    channel_id = callback_query.data.split(":")[-1]
    await callback_query.answer("🎨 Рисую графики (это может занять 10-15 секунд)...")

    stats_data = await youtube_analyzer.get_recent_video_stats(channel_id)

    if stats_data.get("error"):
        await callback_query.message.answer(f"❌ Ошибка при сборе данных для графика: {stats_data['error']}")
        return

    image_buffer = create_activity_graphs(
        stats_data['views_list'],
        stats_data['likes_list'],
        stats_data['comments_list']
    )

    if not image_buffer:
        await callback_query.message.answer(f"❌ Не удалось создать график.")
        return

    photo = BufferedInputFile(image_buffer.getvalue(), filename=f"{channel_id}_activity.png")
    await callback_query.message.answer_photo(
        photo,
        caption="Графики активности по 10 последним видео."
    )


@dp.callback_query(F.data.startswith("show_heatmap:"))
async def download_heatmap_handler(callback_query: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Показать график публикаций".
    """
    channel_id = callback_query.data.split(":")[-1]
    await callback_query.answer("🔥 Анализирую 50 последних видео (это может занять 15-20 секунд)...")

    heatmap_data = await youtube_analyzer.get_publication_heatmap_data(channel_id)

    if heatmap_data.get("error"):
        await callback_query.message.answer(f"❌ Ошибка при сборе данных: {heatmap_data['error']}")
        return

    image_buffer = create_heatmap_graph(heatmap_data['grid'])

    if not image_buffer:
        await callback_query.message.answer(f"❌ Не удалось создать теплокарту.")
        return

    photo = BufferedInputFile(image_buffer.getvalue(), filename=f"{channel_id}_heatmap.png")
    await callback_query.message.answer_photo(
        photo,
        caption="Теплокарта публикаций (по 50 последним видео)."
    )
    await callback_query.message.answer(
        heatmap_data['report'],
        parse_mode="HTML"
    )


# --- 🌐 ФЕЙКОВЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ---

async def health_check(request):
    """Простой ответ 'OK' для проверки здоровья сервиса"""
    return web.Response(text="Bot is alive!")

async def start_web_server():
    """Запускает маленький веб-сервер на порту из окружения"""
    # Render передает порт через переменную окружения PORT
    port = int(os.getenv("PORT", 8000))
    
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"🌐 Fake web server started on port {port}")


# --- 🚀 ГЛАВНАЯ ФУНКЦИЯ ---

async def main():
    """
    Запуск бота в режиме Polling + Веб-сервер для Render.
    """
    logging.info("🚀 Бот запущен в режиме Polling")
    
    # 1. Сначала запускаем веб-сервер, чтобы Render увидел открытый порт
    await start_web_server()
    
    # 2. Удаляем вебхуки (на всякий случай)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # 3. Запускаем поллинг
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

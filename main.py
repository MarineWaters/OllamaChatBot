from config_reader import config
from openrouter import summarize_news_list
import asyncio
import json
from pathlib import Path
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from qdrant import insert_documents, clear_collection, get_existing_titles, get_available_dates, get_documents_by_date, insert_prices, get_prices_by_date, delete_old_price_points
from parser import parse_newest_pages, parse_valuables
from datetime import datetime, timedelta

last_daily_sent = None

async def background_task():
    global last_daily_sent, priced
    priced = False
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        today_str = now.strftime("%d.%m.%y")   
        try:
            if now.hour >= 23:
                clear_task()
                last_daily_sent = None
                priced = False
            if (7 <= now.hour < 23 and 
                last_daily_sent != today_str and 
                user_daily_summaries): 
                if not priced:
                    if pricing_task():
                        priced = True
                else:
                    await daily_summary_task()
                    last_daily_sent = today_str
                    logging.info(f"Daily summary sent for {today_str}")
            new_docs = None
            try:
                existing_titles = get_existing_titles()
                logging.info(f"Existing titles count: {len(existing_titles)}")
                new_docs = parse_newest_pages(stop_titles=existing_titles)
            except Exception as e:
                logging.error(f"Parser error: {e}")
                new_docs = None
            if new_docs:
                inserted_count = insert_documents((new_docs))
                logging.info(f"Inserted {inserted_count} new parsed documents.")
            else:
                logging.info("No new documents found by parser.")
        except Exception as e:
            logging.error(f"Encountered an error this cycle: {e}")
            continue

def clear_task():
    cleared = clear_collection()
    delete_old_price_points()
    logging.info(f"Collection cleared: {cleared}, price collection updated.")

def pricing_task():
    new_docs = parse_valuables()
    if new_docs:
        inserted_count = insert_prices((new_docs))
        if inserted_count:
            return True
        logging.info(f"Inserted {inserted_count} new parsed prices.")
    else:
        logging.info("No new prices found by parser.")
    return False

async def send_daily_summary(user_id: int):
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%y")
    points = get_documents_by_date(yesterday)
    if not points:
        logging.info(f"No news to send for user {user_id} on {yesterday}")
        return
    show_sources = user_show_sources.get(user_id, True)
    news_list = []
    for point in points:
        payload = point.payload or {}
        news_item = {
            "title": payload.get("title", ""),
            "content": payload.get("content", "")
        }
        if show_sources:
            news_item["source"] = payload.get("source", "")
        news_list.append(news_item)
    
    prices = get_prices_by_date(yesterday)
    valuables = ""
    cbr = ""
    selected_date = (datetime.now()).strftime("%d.%m.%y")
    if prices:
        for price in prices:
            payload = price.payload or {}
            valuables = payload.get("prices", "")
            cbr =  "и курс"
    summary = await summarize_news_list(news_list)
    
    try:
        await bot.send_message(user_id, f"<b>Сводка новостей {cbr} на {selected_date}:</b>\n\n{valuables}\n{summary}", reply_markup=menu_kb)
    except Exception as e:
        logging.error(f"Failed to send daily summary to {user_id}: {e}")
        raise e

async def daily_summary_task():
    for user_id, enabled in user_daily_summaries.items():
        if enabled:
            await send_daily_summary(user_id)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

menu_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Сводка по дням", callback_data="summary")],
])

class BotStates:
    WAIT_DATE = "wait_date",

user_states = {}
user_temp_data = {}
user_daily_summaries = {}
user_show_sources = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот с поиском по документам в SmartLab.\nВыбери действие:",
        reply_markup=menu_kb
    )

@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    current = user_daily_summaries.get(user_id, False)
    user_daily_summaries[user_id] = not current
    status = "включена" if user_daily_summaries[user_id] else "выключена"
    await message.answer(f"Ежедневная сводка новостей теперь {status}.")


@dp.message(Command("statechange"))
async def cmd_statechange(message: types.Message):
    user_id = message.from_user.id
    current_state = user_show_sources.get(user_id, True)
    user_show_sources[user_id] = not current_state
    state_str = "включено" if user_show_sources[user_id] else "выключено"
    await message.answer(f"Отображение источников в сводке новостей теперь {state_str}.")

@dp.callback_query()
async def callbacks_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    if data == "summary":
        dates = get_available_dates()
        if not dates:
            await callback.message.answer("Нет доступных дат для сводки новостей. Возможно, сейчас обновляется список новостей, подождите 5 минут.", reply_markup=menu_kb)
        else:
            user_states[user_id] = BotStates.WAIT_DATE
            
            today_str = (datetime.now()-timedelta(days=1)).strftime("%d.%m.%y")
            date_buttons = []
            for date in dates:
                button_text = "Сводка на сегодня!" if date == today_str else date
                date_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"date_{date}")])
            
            date_kb = InlineKeyboardMarkup(inline_keyboard=date_buttons)
            await callback.message.answer("Выберите дату сводки новостей:", reply_markup=date_kb)
        await callback.answer()
    elif data.startswith("date_") and user_states.get(user_id) == BotStates.WAIT_DATE:
        selected_date = data[len("date_"):]
        await callback.answer() 
        await callback.message.answer(f"Получаю новости за {selected_date} и формирую сводку...")
        points = get_documents_by_date(selected_date)
        if not points:
            await callback.message.answer(f"Новости за {selected_date} не найдены.", reply_markup=menu_kb)
            user_states.pop(user_id, None)
            return
        show_sources = user_show_sources.get(user_id, True)
        news_list = []
        for point in points:
            payload = point.payload or {}
            news_item = {
                "title": payload.get("title", ""),
                "content": payload.get("content", "")
            }
            if show_sources:
                news_item["source"] = payload.get("source", "")
            news_list.append(news_item)
        prices = get_prices_by_date(selected_date)
        valuables = ""
        cbr =  ""
        selected_date = (datetime.strptime(selected_date, "%d.%m.%y")+timedelta(days=1)).strftime("%d.%m.%y")
        if prices:
            for price in prices:
                payload = price.payload or {}
                valuables = payload.get("prices", "")
                cbr =  "и курс"
        summary = await summarize_news_list(news_list)
        await callback.message.answer(f"<b>Сводка новостей {cbr} на {selected_date}:</b>\n\n{valuables}\n{summary}", reply_markup=menu_kb)
        user_states.pop(user_id, None)
    else:
        await callback.answer()



@dp.message()
async def process_states(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    await message.answer("Используйте команды в меню чтобы начать работу.")

if __name__ == "__main__":
    async def main():
        while True:
            try:
                asyncio.create_task(background_task())
                await dp.start_polling(bot)
            except Exception as e:
                logging.error(f"Polling crashed: {e}")
                await asyncio.sleep(5)
    asyncio.run(main())
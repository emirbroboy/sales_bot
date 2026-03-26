"""
Telegram-бот для заполнения Google Sheets (Отдел продаж)
Авторизация: Service Account (JSON-ключ)
"""
import logging
import os
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────── НАСТРОЙКИ ───────────────
BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
SPREADSHEET_ID       = os.getenv("SPREADSHEET_ID", "1XcnUSEl0GxJppT6aKuc3pco81Q7aDRo-UQLbRJlkMDI")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
GROUP_CHAT_ID        = int(os.getenv("GROUP_CHAT_ID", "-1003739795027"))

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_STUDENTS = "Регистрация студентов"
SHEET_PAYMENTS = "Учет оплат"

# ─────────────── БЕЛЫЙ СПИСОК ───────────────
# Добавляйте Telegram user_id сюда вручную.
# Узнать свой ID можно у @userinfobot
_raw_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [int(i.strip()) for i in _raw_ids.split(",") if i.strip().isdigit()]

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS

# ─────────────── СПРАВОЧНИК ───────────────
MANAGERS = [
    "Азема Шаршеева", "Айгерим Рыскулова", "Амантур Турдубаев",
    "Нурмухаммад Нурматов", "Ширин Дюшенова", "Ырыскелди Нишанбаев",
    "Азимов Мухаммадюсуф", "Эрнисова Венера"
]
EXPERTS = [
    "Альбина Жанышбекова", "Амина Азимканова", "Жамиля Конушбаева",
    "Рустам Абдылдаев", "Тимур Ахмедов", "Эрнур Коконов",
    "Айзада Сша", "Акматова Сабина", "Джусупова Арууке"
]
PACKAGES = [
    "USA ELITE Ba", "USA ELITE MS", "USA standard Ba", "USA standard MS",
    "Italy ELITE Ba", "Italy ELITE MS", "Italy standard Ba", "Italy standard MS",
    "Transfer", "Reapply", "Malaysia ELITE", "Italy foundation",
    "Germany ELITE Ba", "Germany ELITE MS", "Poland ELITE Ba", "Визовая подготовка"
]
ACCOUNTS = [
    "АБ Бизнес Зеро", "МБанк", "МБизнес доллар", "МБизнес сом",
    "Наличка доллар", "Наличка сом", "О Бизнес", "О Деньги",
    "Оптима Бизнес", "Оптима доллар", "Оптима сом"
]
SEMESTERS    = ["Зима 26", "Весна 26", "Лето 26", "Осень 26", "Осень 27", "Зима27", "Осень 25"]
CITIES       = ["Бишкек", "ОШ", "Нарын", "Ыссык кол", "Баткен", "Чуй", "Джалала-абад", "Талас", "Рф"]
SEMINARS     = ["Семинар", "Не семинар", "акция малазия март 26"]
CERTIFICATES = ["3 мес", "1 мес инд"]
CONTRACT_STATUSES = ["Подписан", "Не подписан"]

# ─────────────── ТЕГИ БАНКОВ ───────────────
def bank_tag(bank_name: str) -> str:
    if not bank_name:
        return ""
    return "#" + bank_name.lower().replace(" ", "")

# ─────────────── СОСТОЯНИЯ ───────────────
(S_FIO, S_CONTRACT_DATE, S_PHONE, S_PACKAGE_COST, S_COURSE,
 S_COST_SOM_SHOW, S_MANAGER, S_CONTRACT, S_CONTRACT_PHOTO,
 S_EXPERT, S_PACKAGE, S_SEMESTER, S_CITY, S_SEMINAR, S_CERT, S_CONFIRM) = range(16)

(P_SEARCH, P_SELECT, P_DATE, P_AMOUNT, P_METHOD, P_NOTE, P_RECEIPT_PHOTO, P_CONFIRM) = range(100, 108)

MAIN_MENU = 200

# ─────────────── GOOGLE SHEETS ───────────────
def get_gspread_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def get_sheet(name: str):
    client = get_gspread_client()
    return client.open_by_key(SPREADSHEET_ID).worksheet(name)

def get_all_students():
    try:
        sheet = get_sheet(SHEET_STUDENTS)
        records = sheet.get_all_values()
        names = [row[0].strip() for row in records[1:] if row and row[0].strip()]
        return names
    except Exception as e:
        logger.error(f"Ошибка получения студентов: {e}")
        return []

def append_student(d: dict):
    sheet = get_sheet(SHEET_STUDENTS)
    row = [
        d.get("fio", ""),
        d.get("contract_date", ""),
        "",   # Дата поступления — убрана
        d.get("phone", ""),
        d.get("package_cost", ""),
        d.get("course", ""),
        "",   # Стоимость в сомах — формула
        "",   # Оплата в сомах — из учёта оплаты
        "",   # Остаток в долларах
        "",   # Остаток в сомах
        "",   # 87.5
        "",   # Факт с вычетом комиссии
        "",   # Проценты банков
        "",   # Банк — из учёта оплаты
        "",   # Банк 2
        d.get("manager", ""),
        d.get("contract", ""),
        "",   # Статус
        d.get("expert", ""),
        d.get("package", ""),
        d.get("semester", ""),
        d.get("city", ""),
        d.get("seminar", ""),
        d.get("certificate", ""),
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")

def append_payment(d: dict):
    sheet = get_sheet(SHEET_PAYMENTS)
    row = [
        d.get("fio", ""),
        d.get("date", ""),
        d.get("amount", ""),
        d.get("method", ""),
        d.get("note", ""),
        "",   # Дата договора — формула
        "",   # Эксперт — формула
        "",   # Пакет — формула
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")

# ─────────────── КЛАВИАТУРЫ ───────────────
def kb(options: list, cols: int = 2, skip: bool = False) -> ReplyKeyboardMarkup:
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    nav = ["⏭ Пропустить", "⬅️ Назад"] if skip else ["⬅️ Назад"]
    rows.append(nav + ["❌ Отмена"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def date_kb(back: bool = True) -> ReplyKeyboardMarkup:
    row1 = [f"📅 {datetime.now().strftime('%d.%m.%Y')}"]
    row2 = ["⬅️ Назад", "❌ Отмена"] if back else ["❌ Отмена"]
    return ReplyKeyboardMarkup([row1, row2], resize_keyboard=True)

def text_kb(back: bool = True, skip: bool = False) -> ReplyKeyboardMarkup:
    row = []
    if skip: row.append("⏭ Пропустить")
    if back: row.append("⬅️ Назад")
    row.append("❌ Отмена")
    return ReplyKeyboardMarkup([row], resize_keyboard=True)

def next_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["➡️ Далее"],
         ["⬅️ Назад", "❌ Отмена"]],
        resize_keyboard=True
    )

def photo_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["✅ Готово, продолжить"],
         ["⬅️ Назад", "❌ Отмена"]],
        resize_keyboard=True
    )

def photo_start_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["⬅️ Назад", "❌ Отмена"]],
        resize_keyboard=True
    )

# ── Главное меню ──
MAIN_KB = ReplyKeyboardMarkup(
    [
        ["📝 Регистрация студента"],
        ["💰 Учёт оплаты"],
    ],
    resize_keyboard=True
)

# ─────────────── РЕЗЮМЕ В БОТ ───────────────
def summary_student(d: dict) -> str:
    package_cost = d.get("package_cost", "")
    course = d.get("course", "")
    try:
        cost_som = f"{int(float(package_cost) * float(course)):,}".replace(",", " ")
    except Exception:
        cost_som = "—"
    cert = d.get("certificate", "")
    cert_str = f"✅ Сертификат выдан ({cert})" if cert else "❌ Сертификат не выдан"
    n_contract = len(d.get("contract_photo_ids", []))
    contract_status = d.get("contract", "—")
    contract_icon = "✅" if contract_status == "Подписан" else "⏳"
    return (
        "┌─────────────────────────\n"
        "│  📋 *РЕГИСТРАЦИЯ СТУДЕНТА*\n"
        "└─────────────────────────\n\n"
        f"👤 *ФИО:* {d.get('fio','—')}\n"
        f"📅 *Дата договора:* {d.get('contract_date','—')}\n"
        f"📞 *Телефон:* {d.get('phone','—')}\n\n"
        "💼 *Пакет и стоимость*\n"
        f"├ 📦 Пакет: {d.get('package','—')}\n"
        f"├ 💵 Стоимость: {package_cost}$\n"
        f"├ 📈 Курс: {course}\n"
        f"└ 💰 Итого в сомах: {cost_som} с\n\n"
        "🏫 *Обучение*\n"
        f"├ 🧑‍🏫 Эксперт: {d.get('expert','—')}\n"
        f"├ 👩‍💼 Менеджер: {d.get('manager','—')}\n"
        f"├ 🗓 Семестр: {d.get('semester','—')}\n"
        f"└ 🌆 Город: {d.get('city','—')}\n\n"
        "📄 *Документы*\n"
        f"├ {contract_icon} Договор: {contract_status}\n"
        f"├ 📸 Фото договора: {n_contract} шт.\n"
        f"├ 🎓 Семинар: {d.get('seminar','—') or '—'}\n"
        f"└ {cert_str}\n"
    )

def summary_payment(d: dict) -> str:
    n_receipt = len(d.get("receipt_photo_ids", []))
    return (
        "┌─────────────────────────\n"
        "│  💰 *УЧЁТ ОПЛАТЫ*\n"
        "└─────────────────────────\n\n"
        f"👤 *ФИО:* {d.get('fio','—')}\n"
        f"📅 *Дата оплаты:* {d.get('date','—')}\n\n"
        "💳 *Платёж*\n"
        f"├ 💵 Сумма: {d.get('amount','—')}\n"
        f"├ 🏦 Способ: {d.get('method','—')}\n"
        f"├ 📝 Примечание: {d.get('note','—') or '—'}\n"
        f"└ 🧾 Фото чека: {n_receipt} шт.\n"
    )

# ─────────────── СООБЩЕНИЯ В ГРУППУ ───────────────
def group_msg_contract(d: dict, sender: str) -> str:
    package_cost = d.get("package_cost", "")
    course = d.get("course", "")
    try:
        cost_som = f"{int(float(package_cost) * float(course)):,}".replace(",", " ")
        cost_str = f"{package_cost}$ / {cost_som} с (курс {course})"
    except Exception:
        cost_str = f"{package_cost}$"

    cert = d.get("certificate", "")
    cert_str = f"Сертификат выдан ({cert})" if cert else "Сертификат не выдан"

    lines = [
        sender,
        "#новыйчек",
        "",
        d.get("fio", ""),
        f"Пакет: {d.get('package', '')}",
        f"Стоимость: {cost_str}",
        f"Менеджер: {d.get('manager', '')}",
        f"Эксперт: {d.get('expert', '')}",
        f"Семестр: {d.get('semester', '')}",
        f"Регион: {d.get('city', '')}",
        f"Дата покупки: {d.get('contract_date', '')}",
        f"Телефон: {d.get('phone', '')}",
        f"Договор: {d.get('contract', '')}",
    ]
    if d.get("seminar"):
        lines.append(f"Семинар: {d.get('seminar')}")
    lines.append(cert_str)
    return "\n".join(lines)

def group_msg_receipt(d: dict, sender: str) -> str:
    lines = [
        sender,
        "#остаток",
        bank_tag(d.get("method", "")),
        "",
        d.get("fio", ""),
        f"Сумма: {d.get('amount', '')}",
        f"Способ: {d.get('method', '')}",
        f"Дата: {d.get('date', '')}",
    ]
    if d.get("note"):
        lines.append(f"Примечание: {d.get('note')}")
    return "\n".join(lines)

def sender_display(user) -> str:
    full_name = " ".join(filter(None, [user.first_name, user.last_name]))
    if user.username:
        return f'<a href="https://t.me/{user.username}">{full_name} (@{user.username})</a>'
    else:
        return f'<a href="tg://user?id={user.id}">{full_name}</a>'

# ─────────────── ОТПРАВКА МЕДИАГРУППЫ ───────────────
async def send_photo_group(bot, chat_id: int, photo_ids: list, caption: str):
    if not photo_ids:
        return
    if len(photo_ids) == 1:
        await bot.send_photo(chat_id=chat_id, photo=photo_ids[0], caption=caption, parse_mode="HTML")
    else:
        media = [InputMediaPhoto(media=photo_ids[0], caption=caption, parse_mode="HTML")]
        for pid in photo_ids[1:]:
            media.append(InputMediaPhoto(media=pid))
        await bot.send_media_group(chat_id=chat_id, media=media)

# ─────────────── ПРОВЕРКА ДОСТУПА ───────────────
async def check_access(update: Update) -> bool:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text(
            "⛔ *Нет доступа*\n\n"
            f"Ваш ID: <code>{user_id}</code>\n"
            "Передайте его администратору.",
            parse_mode="HTML"
        )
        return False
    return True

# ─────────────── СТАРТ / ОТМЕНА ───────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return ConversationHandler.END
    ctx.user_data.clear()
    name = update.effective_user.first_name or "👋"
    await update.message.reply_text(
        f"Привет, *{name}!* 👋\n\n"
        "🏢 *Отдел продаж* — выберите действие:",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )
    return MAIN_MENU

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ *Действие отменено.*\n\nВыберите действие из меню.",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )
    return MAIN_MENU

async def main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return ConversationHandler.END
    t = update.message.text
    if t == "📝 Регистрация студента":
        ctx.user_data["s"] = {}
        await update.message.reply_text(
            "📝 *Регистрация нового студента*\n\n"
            "Шаг 1️⃣ из 1️⃣4️⃣\n"
            "👤 Введите *ФИО* студента полностью:",
            parse_mode="Markdown",
            reply_markup=text_kb(back=False)
        )
        return S_FIO
    if t == "💰 Учёт оплаты":
        ctx.user_data["p"] = {}
        await update.message.reply_text(
            "💰 *Учёт оплаты*\n\n"
            "🔍 Введите имя студента для поиска:",
            parse_mode="Markdown",
            reply_markup=text_kb(back=False)
        )
        return P_SEARCH
    await update.message.reply_text("Выберите действие из меню.", reply_markup=MAIN_KB)
    return MAIN_MENU

# ════════════════════════════════════════════════════════
#  РЕГИСТРАЦИЯ СТУДЕНТОВ
# ════════════════════════════════════════════════════════
async def s_fio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["s"]["fio"] = update.message.text
    await update.message.reply_text(
        "Шаг 2️⃣ из 1️⃣4️⃣\n"
        "📅 Введите дату *заключения договора*\n"
        "или нажмите кнопку с сегодняшней датой:",
        parse_mode="Markdown",
        reply_markup=date_kb(back=False)
    )
    return S_CONTRACT_DATE

async def s_contract_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣ из 1️⃣4️⃣\n👤 Введите *ФИО* студента полностью:",
            parse_mode="Markdown", reply_markup=text_kb(back=False)
        )
        return S_FIO
    # Убираем префикс даты если нажали кнопку
    ctx.user_data["s"]["contract_date"] = t.replace("📅 ", "")
    await update.message.reply_text(
        "Шаг 3️⃣ из 1️⃣4️⃣\n"
        "📞 Введите *номер телефона* студента:",
        parse_mode="Markdown",
        reply_markup=text_kb()
    )
    return S_PHONE

async def s_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 2️⃣ из 1️⃣4️⃣\n📅 Дата заключения договора:",
            parse_mode="Markdown", reply_markup=date_kb(back=False)
        )
        return S_CONTRACT_DATE
    ctx.user_data["s"]["phone"] = update.message.text
    await update.message.reply_text(
        "Шаг 4️⃣ из 1️⃣4️⃣\n"
        "💵 Введите *стоимость пакета* в долларах ($):",
        parse_mode="Markdown",
        reply_markup=text_kb()
    )
    return S_PACKAGE_COST

async def s_package_cost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 3️⃣ из 1️⃣4️⃣\n📞 Номер телефона:",
            parse_mode="Markdown", reply_markup=text_kb()
        )
        return S_PHONE
    ctx.user_data["s"]["package_cost"] = update.message.text
    await update.message.reply_text(
        "Шаг 5️⃣ из 1️⃣4️⃣\n"
        "📈 Введите *курс* (например: 103.2):",
        parse_mode="Markdown",
        reply_markup=text_kb()
    )
    return S_COURSE

async def s_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 4️⃣ из 1️⃣4️⃣\n💵 Стоимость пакета ($):",
            parse_mode="Markdown", reply_markup=text_kb()
        )
        return S_PACKAGE_COST
    ctx.user_data["s"]["course"] = update.message.text
    package_cost = ctx.user_data["s"].get("package_cost", "")
    course = update.message.text
    try:
        cost_som = f"{int(float(package_cost) * float(course)):,}".replace(",", " ")
        msg = (
            "💰 *Расчёт стоимости*\n\n"
            f"📌 {package_cost}$ × {course} = *{cost_som} сом*\n\n"
            "Нажмите ➡️ *Далее* чтобы продолжить."
        )
    except Exception:
        msg = "⚠️ Не удалось рассчитать стоимость.\n\nНажмите ➡️ *Далее* чтобы продолжить."
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=next_kb())
    return S_COST_SOM_SHOW

async def s_cost_som_show(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 5️⃣ из 1️⃣4️⃣\n📈 Курс:",
            parse_mode="Markdown", reply_markup=text_kb()
        )
        return S_COURSE
    await update.message.reply_text(
        "Шаг 6️⃣ из 1️⃣4️⃣\n"
        "👩‍💼 Выберите *менеджера*:",
        parse_mode="Markdown",
        reply_markup=kb(MANAGERS, 1)
    )
    return S_MANAGER

async def s_manager(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        package_cost = ctx.user_data["s"].get("package_cost", "")
        course = ctx.user_data["s"].get("course", "")
        try:
            cost_som = f"{int(float(package_cost) * float(course)):,}".replace(",", " ")
            msg = (
                "💰 *Расчёт стоимости*\n\n"
                f"📌 {package_cost}$ × {course} = *{cost_som} сом*\n\n"
                "Нажмите ➡️ *Далее* чтобы продолжить."
            )
        except Exception:
            msg = "⚠️ Не удалось рассчитать стоимость.\n\nНажмите ➡️ *Далее* чтобы продолжить."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=next_kb())
        return S_COST_SOM_SHOW
    ctx.user_data["s"]["manager"] = update.message.text
    await update.message.reply_text(
        "Шаг 7️⃣ из 1️⃣4️⃣\n"
        "📝 Выберите статус *договора*:",
        parse_mode="Markdown",
        reply_markup=kb(CONTRACT_STATUSES, 2)
    )
    return S_CONTRACT

async def s_contract(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 6️⃣ из 1️⃣4️⃣\n👩‍💼 Выберите менеджера:",
            parse_mode="Markdown", reply_markup=kb(MANAGERS, 1)
        )
        return S_MANAGER
    ctx.user_data["s"]["contract"] = update.message.text
    ctx.user_data["s"]["contract_photo_ids"] = []
    await update.message.reply_text(
        "Шаг 8️⃣ из 1️⃣4️⃣\n"
        "📸 *Фото договора*\n\n"
        "Отправляйте фото по одному.\n"
        "Можно прикрепить несколько.\n"
        "Когда закончите — нажмите *✅ Готово, продолжить*.",
        parse_mode="Markdown",
        reply_markup=photo_start_kb()
    )
    return S_CONTRACT_PHOTO

async def s_contract_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        ctx.user_data["s"]["contract_photo_ids"] = []
        await update.message.reply_text(
            "Шаг 7️⃣ из 1️⃣4️⃣\n📝 Статус договора:",
            parse_mode="Markdown", reply_markup=kb(CONTRACT_STATUSES, 2)
        )
        return S_CONTRACT

    if update.message.text == "✅ Готово, продолжить":
        ids = ctx.user_data["s"].get("contract_photo_ids", [])
        if not ids:
            await update.message.reply_text(
                "⚠️ Отправьте хотя бы одно фото договора.",
                reply_markup=photo_start_kb()
            )
            return S_CONTRACT_PHOTO
        await update.message.reply_text(
            "Шаг 9️⃣ из 1️⃣4️⃣\n"
            "🧑‍🏫 Выберите *эксперта*:",
            parse_mode="Markdown", reply_markup=kb(EXPERTS, 1)
        )
        return S_EXPERT

    if update.message.photo:
        ids = ctx.user_data["s"].setdefault("contract_photo_ids", [])
        ids.append(update.message.photo[-1].file_id)
        count = len(ids)
        await update.message.reply_text(
            f"✅ Фото *{count}* принято!\n"
            "Отправьте ещё или нажмите *✅ Готово, продолжить*.",
            parse_mode="Markdown",
            reply_markup=photo_kb()
        )
        return S_CONTRACT_PHOTO

    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте *фото* (не файл).",
        parse_mode="Markdown",
        reply_markup=photo_kb() if ctx.user_data["s"].get("contract_photo_ids") else photo_start_kb()
    )
    return S_CONTRACT_PHOTO

async def s_expert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 8️⃣ из 1️⃣4️⃣\n📸 Фото договора:",
            parse_mode="Markdown",
            reply_markup=photo_kb() if ctx.user_data["s"].get("contract_photo_ids") else photo_start_kb()
        )
        return S_CONTRACT_PHOTO
    ctx.user_data["s"]["expert"] = update.message.text
    await update.message.reply_text(
        "Шаг 🔟 из 1️⃣4️⃣\n"
        "📦 Выберите *пакет*:",
        parse_mode="Markdown", reply_markup=kb(PACKAGES, 2)
    )
    return S_PACKAGE

async def s_package(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 9️⃣ из 1️⃣4️⃣\n🧑‍🏫 Выберите эксперта:",
            parse_mode="Markdown", reply_markup=kb(EXPERTS, 1)
        )
        return S_EXPERT
    ctx.user_data["s"]["package"] = update.message.text
    await update.message.reply_text(
        "Шаг 1️⃣1️⃣ из 1️⃣4️⃣\n"
        "🗓 Выберите *семестр*:",
        parse_mode="Markdown", reply_markup=kb(SEMESTERS, 2)
    )
    return S_SEMESTER

async def s_semester(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 🔟 из 1️⃣4️⃣\n📦 Выберите пакет:",
            parse_mode="Markdown", reply_markup=kb(PACKAGES, 2)
        )
        return S_PACKAGE
    ctx.user_data["s"]["semester"] = update.message.text
    await update.message.reply_text(
        "Шаг 1️⃣2️⃣ из 1️⃣4️⃣\n"
        "🌆 Выберите *город* проживания:",
        parse_mode="Markdown", reply_markup=kb(CITIES, 2)
    )
    return S_CITY

async def s_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣1️⃣ из 1️⃣4️⃣\n🗓 Выберите семестр:",
            parse_mode="Markdown", reply_markup=kb(SEMESTERS, 2)
        )
        return S_SEMESTER
    ctx.user_data["s"]["city"] = update.message.text
    await update.message.reply_text(
        "Шаг 1️⃣3️⃣ из 1️⃣4️⃣\n"
        "🎓 Выберите *семинар* (или пропустите):",
        parse_mode="Markdown", reply_markup=kb(SEMINARS, 1, skip=True)
    )
    return S_SEMINAR

async def s_seminar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣2️⃣ из 1️⃣4️⃣\n🌆 Выберите город:",
            parse_mode="Markdown", reply_markup=kb(CITIES, 2)
        )
        return S_CITY
    ctx.user_data["s"]["seminar"] = "" if update.message.text == "⏭ Пропустить" else update.message.text
    await update.message.reply_text(
        "Шаг 1️⃣4️⃣ из 1️⃣4️⃣\n"
        "📜 Выберите *сертификат* (или пропустите):",
        parse_mode="Markdown", reply_markup=kb(CERTIFICATES, 2, skip=True)
    )
    return S_CERT

async def s_cert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣3️⃣ из 1️⃣4️⃣\n🎓 Выберите семинар:",
            parse_mode="Markdown", reply_markup=kb(SEMINARS, 1, skip=True)
        )
        return S_SEMINAR
    ctx.user_data["s"]["certificate"] = "" if update.message.text == "⏭ Пропустить" else update.message.text
    await update.message.reply_text(
        summary_student(ctx.user_data["s"]) + "\n\n*Всё верно? Сохранить в таблицу?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Сохранить"], ["⬅️ Назад", "❌ Отмена"]],
            resize_keyboard=True
        )
    )
    return S_CONFIRM

async def s_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣4️⃣ из 1️⃣4️⃣\n📜 Выберите сертификат:",
            parse_mode="Markdown", reply_markup=kb(CERTIFICATES, 2, skip=True)
        )
        return S_CERT
    if update.message.text == "✅ Сохранить":
        try:
            append_student(ctx.user_data["s"])
            await update.message.reply_text(
                "🎉 *Студент успешно добавлен!*\n\nПереходим к учёту оплаты...",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка записи студента: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка:\n<code>{e}</code>", parse_mode="HTML", reply_markup=MAIN_KB)
            ctx.user_data.clear()
            return MAIN_MENU

        # Отправляем фото договора в группу
        photo_ids = ctx.user_data["s"].get("contract_photo_ids", [])
        if photo_ids:
            sender = sender_display(update.message.from_user)
            caption = group_msg_contract(ctx.user_data["s"], sender)
            try:
                await send_photo_group(update.get_bot(), GROUP_CHAT_ID, photo_ids, caption)
            except Exception as e:
                logger.error(f"Ошибка отправки договора в группу: {e}", exc_info=True)

        # Автоматический переход к учёту оплаты
        fio = ctx.user_data["s"].get("fio", "")
        ctx.user_data.clear()
        ctx.user_data["p"] = {"fio": fio}
        await update.message.reply_text(
            f"💰 *Учёт оплаты*\n\n"
            f"👤 Студент: *{fio}*\n\n"
            f"Шаг 1️⃣ из 4️⃣\n📅 Введите дату оплаты:",
            parse_mode="Markdown",
            reply_markup=date_kb(back=False)
        )
        return P_DATE
    return S_CONFIRM

# ════════════════════════════════════════════════════════
#  УЧЁТ ОПЛАТ
# ════════════════════════════════════════════════════════
async def p_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().lower()
    all_names = get_all_students()
    matches = [name for name in all_names if query in name.lower()]
    if not matches:
        await update.message.reply_text(
            f"😔 По запросу «*{update.message.text}*» ничего не найдено.\n\n"
            "Попробуйте ввести имя ещё раз:",
            parse_mode="Markdown",
            reply_markup=text_kb(back=False)
        )
        return P_SEARCH
    ctx.user_data["p_matches"] = matches
    rows = [[name] for name in matches[:20]] + [["🔍 Новый поиск", "❌ Отмена"]]
    await update.message.reply_text(
        f"🔎 Найдено *{len(matches)}* студент(ов).\nВыберите нужного:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )
    return P_SELECT

async def p_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "🔍 Новый поиск":
        await update.message.reply_text(
            "🔍 Введите имя студента для поиска:",
            reply_markup=text_kb(back=False)
        )
        return P_SEARCH
    matches = ctx.user_data.get("p_matches", [])
    if t not in matches:
        rows = [[name] for name in matches[:20]] + [["🔍 Новый поиск", "❌ Отмена"]]
        await update.message.reply_text(
            "⚠️ Пожалуйста, выберите студента из списка.",
            reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
        )
        return P_SELECT
    ctx.user_data["p"]["fio"] = t
    await update.message.reply_text(
        f"✅ Выбран: *{t}*\n\n"
        "Шаг 1️⃣ из 4️⃣\n📅 Введите дату оплаты:",
        parse_mode="Markdown", reply_markup=date_kb(back=False)
    )
    return P_DATE

async def p_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "🔍 Введите имя студента для поиска:",
            reply_markup=text_kb(back=False)
        )
        return P_SEARCH
    ctx.user_data["p"]["date"] = update.message.text.replace("📅 ", "")
    await update.message.reply_text(
        "Шаг 2️⃣ из 4️⃣\n💵 Введите *сумму* оплаты:",
        parse_mode="Markdown", reply_markup=text_kb()
    )
    return P_AMOUNT

async def p_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 1️⃣ из 4️⃣\n📅 Дата оплаты:",
            parse_mode="Markdown", reply_markup=date_kb(back=False)
        )
        return P_DATE
    ctx.user_data["p"]["amount"] = update.message.text
    await update.message.reply_text(
        "Шаг 3️⃣ из 4️⃣\n🏦 Выберите *способ* оплаты:",
        parse_mode="Markdown", reply_markup=kb(ACCOUNTS, 2)
    )
    return P_METHOD

async def p_method(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 2️⃣ из 4️⃣\n💵 Сумма оплаты:",
            parse_mode="Markdown", reply_markup=text_kb()
        )
        return P_AMOUNT
    ctx.user_data["p"]["method"] = update.message.text
    await update.message.reply_text(
        "Шаг 4️⃣ из 4️⃣\n📝 Добавьте *примечание* (или пропустите):",
        parse_mode="Markdown", reply_markup=text_kb(skip=True)
    )
    return P_NOTE

async def p_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "Шаг 3️⃣ из 4️⃣\n🏦 Способ оплаты:",
            parse_mode="Markdown", reply_markup=kb(ACCOUNTS, 2)
        )
        return P_METHOD
    ctx.user_data["p"]["note"] = "" if update.message.text == "⏭ Пропустить" else update.message.text
    ctx.user_data["p"]["receipt_photo_ids"] = []
    await update.message.reply_text(
        "🧾 *Фото чека*\n\n"
        "Отправляйте фото по одному.\n"
        "Можно прикрепить несколько.\n"
        "Когда закончите — нажмите *✅ Готово, продолжить*.",
        parse_mode="Markdown",
        reply_markup=photo_start_kb()
    )
    return P_RECEIPT_PHOTO

async def p_receipt_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        ctx.user_data["p"]["receipt_photo_ids"] = []
        await update.message.reply_text(
            "Шаг 4️⃣ из 4️⃣\n📝 Примечание:",
            parse_mode="Markdown", reply_markup=text_kb(skip=True)
        )
        return P_NOTE

    if update.message.text == "✅ Готово, продолжить":
        ids = ctx.user_data["p"].get("receipt_photo_ids", [])
        if not ids:
            await update.message.reply_text(
                "⚠️ Отправьте хотя бы одно фото чека.",
                reply_markup=photo_start_kb()
            )
            return P_RECEIPT_PHOTO
        await update.message.reply_text(
            summary_payment(ctx.user_data["p"]) + "\n\n*Всё верно? Сохранить в таблицу?*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["✅ Сохранить"], ["⬅️ Назад", "❌ Отмена"]],
                resize_keyboard=True
            )
        )
        return P_CONFIRM

    if update.message.photo:
        ids = ctx.user_data["p"].setdefault("receipt_photo_ids", [])
        ids.append(update.message.photo[-1].file_id)
        count = len(ids)
        await update.message.reply_text(
            f"✅ Фото *{count}* принято!\n"
            "Отправьте ещё или нажмите *✅ Готово, продолжить*.",
            parse_mode="Markdown",
            reply_markup=photo_kb()
        )
        return P_RECEIPT_PHOTO

    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте *фото* (не файл).",
        parse_mode="Markdown",
        reply_markup=photo_kb() if ctx.user_data["p"].get("receipt_photo_ids") else photo_start_kb()
    )
    return P_RECEIPT_PHOTO

async def p_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⬅️ Назад":
        await update.message.reply_text(
            "🧾 Фото чека:",
            parse_mode="Markdown",
            reply_markup=photo_kb() if ctx.user_data["p"].get("receipt_photo_ids") else photo_start_kb()
        )
        return P_RECEIPT_PHOTO

    if update.message.text == "✅ Сохранить":
        try:
            append_payment(ctx.user_data["p"])
            await update.message.reply_text(
                "🎉 *Оплата успешно добавлена в таблицу!*",
                parse_mode="Markdown", reply_markup=MAIN_KB
            )
        except Exception as e:
            logger.error(f"Ошибка записи оплаты: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка:\n<code>{e}</code>", parse_mode="HTML", reply_markup=MAIN_KB)
            ctx.user_data.clear()
            return MAIN_MENU

        # Отправляем фото чека в группу
        photo_ids = ctx.user_data["p"].get("receipt_photo_ids", [])
        if photo_ids:
            sender = sender_display(update.message.from_user)
            caption = group_msg_receipt(ctx.user_data["p"], sender)
            try:
                await send_photo_group(update.get_bot(), GROUP_CHAT_ID, photo_ids, caption)
            except Exception as e:
                logger.error(f"Ошибка отправки чека в группу: {e}", exc_info=True)

        ctx.user_data.clear()
        return MAIN_MENU
    return P_CONFIRM

# ─────────────── ЗАПУСК ───────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    CANCEL = MessageHandler(filters.Regex("^❌ Отмена$"), cancel)

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^📝 Регистрация студента$"), main_menu),
                MessageHandler(filters.Regex("^💰 Учёт оплаты$"), main_menu),
            ],
            S_FIO:            [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_fio)],
            S_CONTRACT_DATE:  [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_contract_date)],
            S_PHONE:          [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_phone)],
            S_PACKAGE_COST:   [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_package_cost)],
            S_COURSE:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_course)],
            S_COST_SOM_SHOW:  [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_cost_som_show)],
            S_MANAGER:        [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_manager)],
            S_CONTRACT:       [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_contract)],
            S_CONTRACT_PHOTO: [CANCEL, MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, s_contract_photo)],
            S_EXPERT:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_expert)],
            S_PACKAGE:        [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_package)],
            S_SEMESTER:       [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_semester)],
            S_CITY:           [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_city)],
            S_SEMINAR:        [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_seminar)],
            S_CERT:           [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_cert)],
            S_CONFIRM:        [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, s_confirm)],
            P_SEARCH:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_search)],
            P_SELECT:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_select)],
            P_DATE:           [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_date)],
            P_AMOUNT:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_amount)],
            P_METHOD:         [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_method)],
            P_NOTE:           [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_note)],
            P_RECEIPT_PHOTO:  [CANCEL, MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, p_receipt_photo)],
            P_CONFIRM:        [CANCEL, MessageHandler(filters.TEXT & ~filters.COMMAND, p_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start), CANCEL],
    )

    app.add_handler(conv)
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

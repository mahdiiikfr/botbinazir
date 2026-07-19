import asyncio
import logging
import sys
import random
import string
import html
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import Local Modules
import config
from bot_instance import bot
from database.db import (
    init_db,
    get_or_create_user,
    get_user,
    update_user_balance,
    get_setting,
    set_setting,
    add_vps_server,
    get_user_vps_servers,
    get_vps_server,
    delete_vps_server,
    create_transaction,
    get_transaction,
    update_transaction_status,
    add_reseller,
    get_user_resellers,
    add_outbound,
    get_user_outbounds,
    get_all_admins,
    get_pending_card_payments,
    get_all_users,
    get_all_vps_servers,
    update_vps_ip_and_status,
    update_vps_password
)
from services.openstack_service import (
    list_flavors,
    list_images,
    list_networks,
    create_server,
    get_server_status,
    start_server,
    stop_server,
    reboot_server,
    rebuild_server,
    change_server_password,
    delete_server,
    FLAVOR_PRICES_USD,
    DEFAULT_HOURLY_USD
)
from services.pasarguard_service import (
    create_reseller_operator,
    create_outbound_subscription
)
from services.exchange_service import get_current_dollar_rate
from services.zarinpal_service import request_zarinpal_payment, verify_zarinpal_payment
from services.billing_service import run_hourly_billing

# Logger Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# FSM States
class VPSStates(StatesGroup):
    selecting_flavor = State()
    selecting_image = State()
    selecting_network = State()
    inputting_name = State()
    inputting_password = State()
    confirming = State()

class WalletStates(StatesGroup):
    inputting_amount_zarinpal = State()
    inputting_amount_card = State()
    upload_receipt = State()

class AdminStates(StatesGroup):
    input_dollar_rate = State()
    input_card_number = State()
    input_card_owner = State()
    input_reseller_price = State()
    input_outbound_price = State()

# Initialize Dispatcher and Router
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- KEYBOARDS ---
def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="💻 خرید سرور مجازی (ساعتی)")],
        [KeyboardButton(text="🚀 خرید پنل نمایندگی PasarGuard"), KeyboardButton(text="🔌 خرید اشتراک اوتباند")],
        [KeyboardButton(text="💳 شارژ کیف پول"), KeyboardButton(text="📂 سرویس‌های من")],
        [KeyboardButton(text="ℹ️ راهنما و پشتیبانی")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ پنل مدیریت")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ انصراف")]], resize_keyboard=True)

# --- GENERAL HANDLERS ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    is_admin = bool(user["is_admin"])

    welcome_text = (
        f"سلام {html.escape(message.from_user.full_name)} عزیز! به ربات هوشمند خدمات ابری و پروکسی خوش آمدید.\n\n"
        f"💰 موجودی کیف پول شما: <b>{user['wallet_balance']:,} تومان</b>\n\n"
        f"میتوانید از دکمه‌های زیر جهت خرید سرورهای ابری ساعتی، پنل‌های پروکسی نمایندگی یا اشتراک‌های اوتباند استفاده کنید."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin), parse_mode="HTML")

@router.message(F.text == "❌ انصراف")
async def process_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    is_admin = bool(user["is_admin"]) if user else False
    await message.answer("عملیات لغو شد. به منوی اصلی بازگشتید.", reply_markup=get_main_keyboard(is_admin))

@router.message(F.text == "ℹ️ راهنما و پشتیبانی")
async def process_support(message: Message):
    support_text = (
        "💡 <b>راهنما و قوانین ربات:</b>\n\n"
        "۱. سرورهای مجازی به صورت <b>ساعتی</b> محاسبه میشوند و هزینه آن هر ۱ ساعت از کیف پول شما کسر میگردد.\n"
        "۲. در صورت اتمام موجودی کیف پول، سیستم جهت جلوگیری از ایجاد بدهی، سرور شما را به طور کامل حذف خواهد کرد.\n"
        "۳. تایید پرداخت‌های کارت‌به‌کارت توسط مدیریت بین ۵ دقیقه الی ۲ ساعت زمان میبرد.\n\n"
        "📞 <b>ارتباط با پشتیبانی:</b>\n"
        "جهت ارسال تیکت و راهنمایی بیشتر با آیدی پشتیبانی در ارتباط باشید:\n"
        "🗣 @CloudSupport_Admin"
    )
    await message.answer(support_text, parse_mode="HTML")

# --- VPS BUYING SYSTEM ---
@router.message(F.text == "💻 خرید سرور مجازی (ساعتی)")
async def buy_vps_start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user["wallet_balance"] < 10000:
        await message.answer(
            "❌ جهت خرید سرور مجازی، باید حداقل <b>۱۰,۰۰۰ تومان</b> در کیف پول خود موجودی داشته باشید.\n"
            "لطفاً ابتدا کیف پول خود را شارژ کنید.",
            parse_mode="HTML"
        )
        return

    await message.answer("درحال دریافت لیست پلن‌ها از OpenStack... لطفاً شکیبا باشید.")
    try:
        flavors = await list_flavors()
        if not flavors:
            await message.answer("❌ هیچ پلنی در حال حاضر در دسترس نیست.")
            return

        dollar_rate = await get_current_dollar_rate()
        profit_margin = float(await get_setting("profit_margin", "50"))
        profit_factor = 1.0 + (profit_margin / 100.0)

        text = "💻 <b>انتخاب پلن سرور مجازی:</b>\n\nلطفاً یکی از پلن‌های زیر را انتخاب کنید:\n\n"
        keyboard_buttons = []

        for idx, fl in enumerate(flavors):
            # Calculate dynamic price
            hourly_toman = int(fl["price_usd_hourly"] * dollar_rate * profit_factor)
            monthly_est = hourly_toman * 720

            text += (
                f"🔹 <b>{idx+1}. پلن {fl['name']}</b>\n"
                f"   🧠 رم: {fl['ram']} MB | 💿 هارد: {fl['disk']} GB | ⚙️ پردازنده: {fl['vcpus']} Core\n"
                f"   💰 هزینه: <b>{hourly_toman:,} تومان/ساعت</b> (~{monthly_est:,} تومان/ماه)\n\n"
            )

            # Inline button for selection
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"پلن {fl['name']} - {hourly_toman:,} ت/ساعت",
                    callback_data=f"vps_fl_{fl['id']}_{fl['name']}_{hourly_toman}"
                )
            ])

        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons), parse_mode="HTML")
        await state.set_state(VPSStates.selecting_flavor)

    except Exception as e:
        logger.error(f"Error listing flavors: {e}")
        await message.answer("❌ خطا در اتصال به OpenStack. لطفا بعداً تلاش کنید.")

@router.callback_query(VPSStates.selecting_flavor, F.data.startswith("vps_fl_"))
async def process_flavor(call: CallbackQuery, state: FSMContext):
    _, _, fl_id, fl_name, fl_price = call.data.split("_")
    await state.update_data(flavor_id=fl_id, flavor_name=fl_name, hourly_cost=float(fl_price))
    await call.answer()

    await call.message.edit_text("درحال دریافت لیست سیستم‌عامل‌ها... لطفاً شکیبا باشید.")
    try:
        images = await list_images()
        buttons = []
        for img in images:
            buttons.append([InlineKeyboardButton(text=img["name"], callback_data=f"vps_img_{img['id']}")])

        await call.message.answer(
            "💿 <b>سیستم‌عامل سرور را انتخاب کنید:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
        await state.set_state(VPSStates.selecting_image)
    except Exception as e:
        logger.error(f"Error listing images: {e}")
        await call.message.answer("❌ خطا در دریافت سیستم‌عامل‌ها.")

@router.callback_query(VPSStates.selecting_image, F.data.startswith("vps_img_"))
async def process_image(call: CallbackQuery, state: FSMContext):
    img_id = call.data.split("_")[2]
    await state.update_data(image_id=img_id)
    await call.answer()

    await call.message.edit_text("درحال دریافت شبکه‌ها... لطفاً منتظر بمانید.")
    try:
        networks = await list_networks()
        buttons = []
        for net in networks:
            buttons.append([InlineKeyboardButton(text=net["name"], callback_data=f"vps_net_{net['id']}")])

        await call.message.answer(
            "🔌 <b>شبکه مورد نظر را انتخاب کنید:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
        await state.set_state(VPSStates.selecting_network)
    except Exception as e:
        logger.error(f"Error listing networks: {e}")
        await call.message.answer("❌ خطا در دریافت شبکه‌ها.")

@router.callback_query(VPSStates.selecting_network, F.data.startswith("vps_net_"))
async def process_network(call: CallbackQuery, state: FSMContext):
    net_id = call.data.split("_")[2]
    await state.update_data(network_id=net_id)
    await call.answer()

    await call.message.answer(
        "📝 <b>یک نام برای سرور خود وارد کنید:</b>\n"
        "نام سرور باید فقط حروف انگلیسی و اعداد باشد (مثال: MyServer1).",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(VPSStates.inputting_name)

@router.message(VPSStates.inputting_name, F.text)
async def process_vps_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name.isalnum():
        await message.answer("❌ نام نامعتبر است. فقط حروف انگلیسی و اعداد مجاز هستند. مجدداً نامی وارد کنید:")
        return

    await state.update_data(server_name=name)
    await message.answer(
        "🔑 <b>رمز عبور روت (root) سرور را وارد کنید:</b>\n"
        "رمز باید حداقل ۸ کاراکتر و شامل حروف و اعداد باشد.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(VPSStates.inputting_password)

@router.message(VPSStates.inputting_password, F.text)
async def process_vps_password(message: Message, state: FSMContext):
    pwd = message.text.strip()
    if len(pwd) < 8:
        await message.answer("❌ رمز عبور ضعیف است. حداقل باید ۸ کاراکتر باشد. مجدداً وارد کنید:")
        return

    await state.update_data(root_password=pwd)
    data = await state.get_data()

    confirm_text = (
        f"🔍 <b>تایید نهایی ساخت سرور مجازی:</b>\n\n"
        f"🖥 نام سرور: {html.escape(data['server_name'])}\n"
        f"🔹 پلن: {html.escape(data['flavor_name'])}\n"
        f"💿 رمز روت: <code>{html.escape(data['root_password'])}</code>\n"
        f"💰 تعرفه ساعتی: <b>{int(data['hourly_cost']):,} تومان/ساعت</b>\n\n"
        f"آیا صحت اطلاعات بالا و کسر موجودی ساعتی را تایید میکنید؟"
    )

    buttons = [
        [InlineKeyboardButton(text="✅ بله، ساخته شود", callback_data="vps_confirm_yes")],
        [InlineKeyboardButton(text="❌ خیر، انصراف", callback_data="vps_confirm_no")]
    ]

    await message.answer(confirm_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await state.set_state(VPSStates.confirming)

@router.callback_query(VPSStates.confirming, F.data == "vps_confirm_no")
async def process_vps_cancel_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("ساخت سرور لغو شد.")
    user = await get_user(call.from_user.id)
    is_admin = bool(user["is_admin"]) if user else False
    await call.message.answer("عملیات ساخت سرور لغو شد.", reply_markup=get_main_keyboard(is_admin))

@router.callback_query(VPSStates.confirming, F.data == "vps_confirm_yes")
async def process_vps_confirm_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await call.answer()

    await call.message.edit_text("🚀 <b>درحال ارسال درخواست ساخت سرور به ابر OpenStack...</b>\nاین فرآیند ممکن است تا ۱ دقیقه طول بکشد. لطفا پنجره را نبندید.", parse_mode="HTML")

    try:
        # Create server on OpenStack
        res = await create_server(
            name=data["server_name"],
            flavor_id=data["flavor_id"],
            image_id=data["image_id"],
            network_id=data["network_id"],
            root_password=data["root_password"]
        )

        # Save to database
        db_id = await add_vps_server(
            user_id=call.from_user.id,
            openstack_server_id=res["id"],
            server_name=data["server_name"],
            flavor_id=data["flavor_name"], # We map using flavor name in FLAVOR_PRICES_USD
            image_id=data["image_id"],
            network_id=data["network_id"],
            hourly_cost_toman=data["hourly_cost"],
            root_password=data["root_password"],
            ip_address="Pending"
        )

        success_text = (
            f"✅ <b>سرور با موفقیت ایجاد گردید!</b>\n\n"
            f"🖥 نام سرور: {html.escape(data['server_name'])}\n"
            f"🆔 شناسه ابر: <code>{res['id']}</code>\n"
            f"🔑 رمز روت: <code>{html.escape(data['root_password'])}</code>\n"
            f"💰 تعرفه: <b>{int(data['hourly_cost']):,} تومان/ساعت</b>\n\n"
            f"درحال تخصیص آی‌پی به سرور... میتوانید وضعیت آن را در بخش <b>«سرویس‌های من»</b> بررسی کنید."
        )

        user = await get_user(call.from_user.id)
        await call.message.answer(success_text, reply_markup=get_main_keyboard(user["is_admin"]), parse_mode="HTML")

        # Trigger background task to fetch IP and update state
        asyncio.create_task(update_vps_ip_after_creation(res["id"]))

    except Exception as e:
        logger.error(f"Failed to create VPS: {e}")
        user = await get_user(call.from_user.id)
        await call.message.answer(f"❌ خطا در ایجاد سرور مجازی: {e}", reply_markup=get_main_keyboard(user["is_admin"]))

async def update_vps_ip_after_creation(os_id: str):
    """Retrieve IP address of server once active and save to DB"""
    for _ in range(12): # check for 2 minutes (every 10s)
        await asyncio.sleep(10)
        status = await get_server_status(os_id)
        if status and status["ip_address"] != "N/A" and status["ip_address"] != "Pending":
            await update_vps_ip_and_status(os_id, status["ip_address"], status["status"])
            break

# --- PASARGUARD RESELLER / OUTBOUND PURCHASING ---
@router.message(F.text == "🚀 خرید پنل نمایندگی PasarGuard")
async def buy_reseller_start(message: Message):
    reseller_price = int(await get_setting("reseller_price", "800000"))
    reseller_limit = int(await get_setting("reseller_limit", "50"))

    text = (
        f"🚀 <b>خرید پنل نمایندگی پروکسی (اپراتور PasarGuard):</b>\n\n"
        f"با خرید این سرویس، یک دسترسی مدیریتی اپراتور اختصاصی در پنل پروکسی PasarGuard برای شما ساخته میشود.\n\n"
        f"🔹 <b>مشخصات پنل نمایندگی:</b>\n"
        f"   - تعداد کاربر مجاز: <b>حداکثر {reseller_limit} کاربر</b>\n"
        f"   - کنترل کامل بر روی کاربران پروکسی خود\n\n"
        f"💰 قیمت خرید: <b>{reseller_price:,} تومان</b> (پرداخت یکباره)\n\n"
        f"آیا مایل به خرید این سرویس هستید؟"
    )

    buttons = [
        [InlineKeyboardButton(text="✅ بله، خرید و پرداخت", callback_data="buy_reseller_confirm")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="buy_reseller_cancel")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "buy_reseller_cancel")
async def cancel_reseller_buy(call: CallbackQuery):
    await call.answer("انصراف داده شد.")
    await call.message.delete()

@router.callback_query(F.data == "buy_reseller_confirm")
async def confirm_reseller_buy(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    price = int(await get_setting("reseller_price", "800000"))
    limit = int(await get_setting("reseller_limit", "50"))

    if user["wallet_balance"] < price:
        await call.answer("❌ موجودی کیف پول کافی نیست!", show_alert=True)
        return

    await call.answer()
    await call.message.edit_text("⚙️ <b>درحال ساخت پنل اپراتور اختصاصی شما در PasarGuard...</b>\nلطفاً شکیبا باشید.", parse_mode="HTML")

    res = await create_reseller_operator(username_prefix=f"u{call.from_user.id}", max_users=limit)
    if res["success"]:
        # Deduct wallet balance
        await update_user_balance(call.from_user.id, -price)
        # Create transaction log
        await create_transaction(
            user_id=call.from_user.id,
            amount=price,
            type_='RESELLER_PURCHASE',
            payment_method='SYSTEM',
            status='APPROVED',
            ref_id=res["username"]
        )
        # Save reseller database
        await add_reseller(
            user_id=call.from_user.id,
            operator_username=res["username"],
            operator_password=res["password"],
            limits=limit,
            price=price
        )

        success_text = (
            f"🎉 <b>تبریک! پنل نمایندگی شما با موفقیت فعال شد!</b>\n\n"
            f"🌐 آدرس ورود به پنل: {res['login_url']}\n"
            f"👤 نام کاربری: <code>{res['username']}</code>\n"
            f"🔑 رمز عبور: <code>{res['password']}</code>\n\n"
            f"⚠️ لطفاً اطلاعات ورود خود را در جای امنی ذخیره کنید."
        )
        await call.message.answer(success_text, reply_markup=get_main_keyboard(user["is_admin"]), parse_mode="HTML")
        await call.message.delete()
    else:
        await call.message.answer("❌ متاسفانه در حال حاضر امکان ساخت پنل پروکسی وجود ندارد. لطفا با پشتیبانی در ارتباط باشید.")

@router.message(F.text == "🔌 خرید اشتراک اوتباند")
async def buy_outbound_start(message: Message):
    outbound_price = int(await get_setting("outbound_price", "800000"))
    outbound_limit_gb = int(await get_setting("outbound_limit_gb", "1000"))

    text = (
        f"🔌 <b>خرید اشتراک ترافیک اوتباند اختصاصی (PasarGuard):</b>\n\n"
        f"با خرید این سرویس، یک اکانت پروکسی پرسرعت اختصاصی با ترافیک بالا برای شما ایجاد میشود.\n\n"
        f"🔹 <b>مشخصات اشتراک:</b>\n"
        f"   - حجم ترافیک: <b>{outbound_limit_gb} گیگابایت (۱ ترابایت)</b>\n"
        f"   - نوع پروتکل: Xray (VLESS, Trojan)\n\n"
        f"💰 قیمت خرید: <b>{outbound_price:,} تومان</b>\n\n"
        f"آیا مایل به خرید این اشتراک هستید؟"
    )

    buttons = [
        [InlineKeyboardButton(text="✅ بله، خرید و پرداخت", callback_data="buy_outbound_confirm")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="buy_outbound_cancel")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "buy_outbound_cancel")
async def cancel_outbound_buy(call: CallbackQuery):
    await call.answer("انصراف داده شد.")
    await call.message.delete()

@router.callback_query(F.data == "buy_outbound_confirm")
async def confirm_outbound_buy(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    price = int(await get_setting("outbound_price", "800000"))
    limit_gb = int(await get_setting("outbound_limit_gb", "1000"))

    if user["wallet_balance"] < price:
        await call.answer("❌ موجودی کیف پول کافی نیست!", show_alert=True)
        return

    await call.answer()
    await call.message.edit_text("⚙️ <b>درحال ایجاد اکانت پروکسی اوتباند پرسرعت شما...</b>\nلطفاً شکیبا باشید.", parse_mode="HTML")

    res = await create_outbound_subscription(username_prefix=f"o{call.from_user.id}", data_limit_gb=limit_gb)
    if res["success"]:
        # Deduct wallet balance
        await update_user_balance(call.from_user.id, -price)
        # Create transaction log
        await create_transaction(
            user_id=call.from_user.id,
            amount=price,
            type_='OUTBOUND_PURCHASE',
            payment_method='SYSTEM',
            status='APPROVED',
            ref_id=res["username"]
        )
        # Save database
        await add_outbound(
            user_id=call.from_user.id,
            subscription_url=res["subscription_url"],
            data_limit_gb=limit_gb,
            price=price
        )

        success_text = (
            f"🎉 <b>اشتراک اوتباند شما با موفقیت ایجاد گردید!</b>\n\n"
            f"🔌 لینک اشتراک پروکسی شما (Subscription Link):\n\n"
            f"<code>{res['subscription_url']}</code>\n\n"
            f"میتوانید این لینک را مستقیماً در نرم‌افزارهای v2rayN, Shadowrocket, v2rayNG وارد و استفاده نمایید."
        )
        await call.message.answer(success_text, reply_markup=get_main_keyboard(user["is_admin"]), parse_mode="HTML")
        await call.message.delete()
    else:
        await call.message.answer("❌ خطا در ایجاد اشتراک پروکسی. لطفا بعداً تلاش نمایید.")

# --- MY SERVICES PANEL ---
@router.message(F.text == "📂 سرویس‌های من")
async def my_services_start(message: Message):
    servers = await get_user_vps_servers(message.from_user.id)
    resellers = await get_user_resellers(message.from_user.id)
    outbounds = await get_user_outbounds(message.from_user.id)

    if not servers and not resellers and not outbounds:
        await message.answer("❌ شما هیچ سرویس فعالی خریداری نکرده‌اید.")
        return

    text = "📂 <b>لیست سرویس‌های خریداری شده شما:</b>\n\n"
    buttons = []

    # 1. VPS Servers List
    if servers:
        text += "💻 <b>سرورهای مجازی ساعتی:</b>\n"
        for idx, sv in enumerate(servers):
            text += f"🔹 {idx+1}. <b>{html.escape(sv['server_name'])}</b> - هزینه: {int(sv['hourly_cost_toman']):,} تومان/ساعت | آی‌پی: <code>{sv['ip_address']}</code>\n"
            buttons.append([InlineKeyboardButton(text=f"⚙️ مدیریت سرور: {sv['server_name']}", callback_data=f"manage_vps_{sv['id']}")])
        text += "\n"

    # 2. Reseller Panels List
    if resellers:
        text += "🚀 <b>پنل‌های نمایندگی (PasarGuard):</b>\n"
        for idx, rs in enumerate(resellers):
            text += f"🔹 {idx+1}. نام کاربری: <code>{html.escape(rs['operator_username'])}</code> | ظرفیت: {rs['limits']} کاربر\n"
        text += "\n"

    # 3. Outbounds List
    if outbounds:
        text += "🔌 <b>اشتراک‌های اوتباند (پروکسی):</b>\n"
        for idx, ob in enumerate(outbounds):
            text += f"🔹 {idx+1}. حجم: {ob['data_limit_gb']} GB\n<code>{ob['subscription_url']}</code>\n"
        text += "\n"

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None, parse_mode="HTML")

@router.callback_query(F.data.startswith("manage_vps_"))
async def process_manage_vps(call: CallbackQuery):
    vps_id = int(call.data.split("_")[2])
    vps = await get_vps_server(vps_id)
    if not vps or vps["user_id"] != call.from_user.id:
        await call.answer("❌ سرور پیدا نشد.", show_alert=True)
        return

    await call.answer()

    # Check status from OpenStack
    status_info = await get_server_status(vps["openstack_server_id"])
    if status_info:
        # update dynamic status in local db
        await update_vps_ip_and_status(vps["openstack_server_id"], status_info["ip_address"], status_info["status"])
        status_str = status_info["status"]
        ip_addr = status_info["ip_address"]
    else:
        status_str = vps["status"]
        ip_addr = vps["ip_address"]

    text = (
        f"⚙️ <b>پنل مدیریت سرور مجازی ابری</b>\n\n"
        f"🖥 نام سرور: <b>{html.escape(vps['server_name'])}</b>\n"
        f"🌐 آی‌پی آدرس: <code>{ip_addr}</code>\n"
        f"🔑 رمز روت: <code>{html.escape(vps['root_password'])}</code>\n"
        f"💰 تعرفه ساعتی: <b>{int(vps['hourly_cost_toman']):,} تومان/ساعت</b>\n"
        f"🟢 وضعیت فعلی: <b>{status_str}</b>\n\n"
        f"جهت خاموش، روشن، راه‌اندازی مجدد یا حذف کامل سرور از دکمه‌های زیر استفاده کنید:"
    )

    buttons = [
        [
            InlineKeyboardButton(text="🟢 روشن کردن", callback_data=f"vps_act_start_{vps_id}"),
            InlineKeyboardButton(text="🔴 خاموش کردن", callback_data=f"vps_act_stop_{vps_id}")
        ],
        [
            InlineKeyboardButton(text="🔁 ریبوت (Soft)", callback_data=f"vps_act_reboot_soft_{vps_id}"),
            InlineKeyboardButton(text="⚡️ ریبوت (Hard)", callback_data=f"vps_act_reboot_hard_{vps_id}")
        ],
        [
            InlineKeyboardButton(text="🔑 تغییر رمز عبور", callback_data=f"vps_act_chgpass_{vps_id}"),
            InlineKeyboardButton(text="💿 نصب مجدد (Rebuild)", callback_data=f"vps_act_rebuild_{vps_id}")
        ],
        [
            InlineKeyboardButton(text="🔥 حذف کامل سرور (بدون بازگشت)", callback_data=f"vps_act_delete_{vps_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="vps_act_back_list")
        ]
    ]

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "vps_act_back_list")
async def process_vps_act_back_list(call: CallbackQuery):
    await call.answer()
    await my_services_start(call.message)
    await call.message.delete()

@router.callback_query(F.data.startswith("vps_act_"))
async def process_vps_actions(call: CallbackQuery):
    _, _, action, vps_id = call.data.split("_", 3)
    # wait if action contains rebuild or chgpass which has trailing text
    if "_" in vps_id:
        action_parts = action + "_" + vps_id.split("_")[0]
        vps_id = int(vps_id.split("_")[1])
        action = action_parts
    else:
        vps_id = int(vps_id)

    vps = await get_vps_server(vps_id)
    if not vps or vps["user_id"] != call.from_user.id:
        await call.answer("❌ سرویس یافت نشد.", show_alert=True)
        return

    os_id = vps["openstack_server_id"]

    await call.answer(f"درحال ارسال درخواست {action}...")

    if action == "start":
        ok = await start_server(os_id)
        await call.message.answer(f"✅ درخواست روشن کردن سرور {html.escape(vps['server_name'])} ارسال شد.")
    elif action == "stop":
        ok = await stop_server(os_id)
        await call.message.answer(f"✅ درخواست خاموش کردن سرور {html.escape(vps['server_name'])} ارسال شد.")
    elif action == "reboot_soft":
        ok = await reboot_server(os_id, hard=False)
        await call.message.answer(f"✅ درخواست ریستارت معمولی سرور {html.escape(vps['server_name'])} ارسال شد.")
    elif action == "reboot_hard":
        ok = await reboot_server(os_id, hard=True)
        await call.message.answer(f"✅ درخواست ریستارت سخت سرور {html.escape(vps['server_name'])} ارسال شد.")
    elif action == "chgpass":
        # Generate random password
        new_pass = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        ok = await change_server_password(os_id, new_pass)
        if ok:
            await update_vps_password(os_id, new_pass)
            await call.message.answer(f"✅ رمز روت سرور با موفقیت به رمز زیر تغییر یافت:\n<code>{new_pass}</code>", parse_mode="HTML")
        else:
            await call.message.answer("❌ این ویژگی روی این سرور پشتیبانی نمیشود. میتوانید سرور را با رمز جدید Rebuild (نصب مجدد) کنید.")
    elif action == "rebuild":
        # Rebuild server with same image and password
        new_pass = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        ok = await rebuild_server(os_id, vps["image_id"], new_pass)
        if ok:
            await update_vps_password(os_id, new_pass)
            await call.message.answer(f"✅ سرور درحال نصب مجدد است. رمز روت جدید شما:\n<code>{new_pass}</code>", parse_mode="HTML")
        else:
            await call.message.answer("❌ خطا در نصب مجدد سیستم‌عامل.")
    elif action == "delete":
        # Delete completely
        ok = await delete_server(os_id)
        if ok:
            await delete_vps_server(vps_id)
            await call.message.answer(f"🔥 سرور {html.escape(vps['server_name'])} به طور کامل از ابر OpenStack حذف گردید.")
            await call.message.delete()
            return
        else:
            await call.message.answer("❌ خطا در حذف سرور از OpenStack. مجدداً تلاش کنید.")

    # Refresh panel state
    # Wait 2 seconds for API to register status change
    await asyncio.sleep(2)
    await process_manage_vps(call)

# --- WALLET CHARGING SYSTEM ---
@router.message(F.text == "💳 شارژ کیف پول")
async def wallet_charge_start(message: Message):
    user = await get_user(message.from_user.id)
    text = (
        f"💳 <b>کیف پول شما:</b>\n\n"
        f"💰 موجودی فعلی: <b>{user['wallet_balance']:,} تومان</b>\n\n"
        f"لطفاً روش شارژ مورد نظر خود را انتخاب کنید:"
    )

    buttons = [
        [InlineKeyboardButton(text="💳 پرداخت آنلاین (زرین‌پال)", callback_data="wallet_charge_zarinpal")],
        [InlineKeyboardButton(text="🏦 کارت به کارت (تایید دستی)", callback_data="wallet_charge_card")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "wallet_charge_zarinpal")
async def charge_zarinpal(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "💳 <b>شارژ از طریق درگاه زرین‌پال:</b>\n\n"
        "مبلغ مورد نظر را به <b>تومان</b> وارد نمایید (حداقل ۵,۰۰۰ تومان):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(WalletStates.inputting_amount_zarinpal)

@router.message(WalletStates.inputting_amount_zarinpal, F.text)
async def process_zarinpal_amount(message: Message, state: FSMContext):
    amount_str = message.text.strip()
    if not amount_str.isdigit() or int(amount_str) < 5000:
        await message.answer("❌ مبلغ نامعتبر است. مبلغ باید عدد صحیح و حداقل ۵,۰۰۰ تومان باشد. مجدداً وارد کنید:")
        return

    amount = int(amount_str)
    await state.clear()

    await message.answer("درحال تولید لینک پرداخت زرین‌پال... لطفاً منتظر بمانید.")

    # Create payment request
    # Zarinpal require callback. We simulate it dynamically
    bot_info = await bot.get_me()
    callback_url = f"https://t.me/{bot_info.username}?start=verify_{amount}"

    req = await request_zarinpal_payment(
        amount_toman=amount,
        description=f"شارژ کیف پول کاربری {message.from_user.id}",
        callback_url=callback_url
    )

    if req["success"]:
        # Save transaction
        tx_id = await create_transaction(
            user_id=message.from_user.id,
            amount=amount,
            type_='DEPOSIT',
            payment_method='ZARINPAL',
            status='PENDING',
            ref_id=req["authority"]
        )

        text = (
            f"✅ <b>لینک پرداخت زرین‌پال آماده گردید!</b>\n\n"
            f"💰 مبلغ شارژ: <b>{amount:,} تومان</b>\n\n"
            f"روی دکمه زیر کلیک کنید تا وارد درگاه پرداخت شوید. پس از پرداخت موفق، دکمه <b>«بررسی پرداخت»</b> را بزنید."
        )

        buttons = [
            [InlineKeyboardButton(text="🔗 ورود به درگاه پرداخت", url=req["payment_url"])],
            [InlineKeyboardButton(text="🔍 بررسی وضعیت پرداخت", callback_data=f"verify_zp_{tx_id}_{amount}_{req['authority']}")]
        ]

        user = await get_user(message.from_user.id)
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    else:
        user = await get_user(message.from_user.id)
        await message.answer("❌ متاسفانه در حال حاضر درگاه پرداخت قطع میباشد. لطفا از روش کارت به کارت استفاده کنید.", reply_markup=get_main_keyboard(user["is_admin"]))

@router.callback_query(F.data.startswith("verify_zp_"))
async def process_verify_zarinpal(call: CallbackQuery):
    _, _, _, tx_id, amount, authority = call.data.split("_")
    tx_id = int(tx_id)
    amount = int(amount)

    tx = await get_transaction(tx_id)
    if not tx or tx["status"] != "PENDING":
        await call.answer("❌ تراکنش منقضی شده یا قبلاً تایید شده است.", show_alert=True)
        return

    await call.answer("درحال بررسی وضعیت تراکنش از زرین‌پال...")

    ver = await verify_zarinpal_payment(amount_toman=amount, authority=authority)
    if ver["success"]:
        # Update transaction status
        await update_transaction_status(tx_id, "APPROVED", ver["ref_id"])
        # Credit user wallet
        await update_user_balance(call.from_user.id, amount)

        user = await get_user(call.from_user.id)
        success_text = (
            f"🎉 <b>پرداخت موفقیت‌آمیز بود!</b>\n\n"
            f"💰 مبلغ <b>{amount:,} تومان</b> به کیف پول شما اضافه گردید.\n"
            f"🧾 شماره پیگیری تراکنش: <code>{ver['ref_id']}</code>\n\n"
            f"موجودی جدید شما: <b>{user['wallet_balance']:,} تومان</b>"
        )
        await call.message.answer(success_text, reply_markup=get_main_keyboard(user["is_admin"]), parse_mode="HTML")
        await call.message.delete()
    else:
        await call.answer(f"❌ {ver['message']}", show_alert=True)

# Card-to-Card payment
@router.callback_query(F.data == "wallet_charge_card")
async def charge_card(call: CallbackQuery, state: FSMContext):
    await call.answer()
    card_num = await get_setting("card_number", "5022-2910-1234-5678")
    card_own = await get_setting("card_owner", "مدیریت ربات")

    text = (
        f"🏦 <b>شارژ از طریق کارت به کارت:</b>\n\n"
        f"لطفاً مبلغ مورد نظر خود را به کارت زیر واریز نمایید:\n\n"
        f"💳 شماره کارت: <code>{card_num}</code>\n"
        f"👤 به نام: <b>{html.escape(card_own)}</b>\n\n"
        f"مبلغ مورد نظر برای واریز را به <b>تومان</b> وارد کنید:",
    )
    await call.message.answer(text[0], reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await state.set_state(WalletStates.inputting_amount_card)

@router.message(WalletStates.inputting_amount_card, F.text)
async def process_card_amount(message: Message, state: FSMContext):
    amount_str = message.text.strip()
    if not amount_str.isdigit() or int(amount_str) < 5000:
        await message.answer("❌ مبلغ نامعتبر است. عدد صحیح و حداقل ۵,۰۰۰ تومان باشد. مجدداً وارد کنید:")
        return

    await state.update_data(amount=int(amount_str))
    await message.answer(
        "📸 <b>عکس رسید پرداخت خود را ارسال کنید:</b>\n"
        "لطفاً یک عکس با کیفیت و خوانا از فیش واریزی خود بفرستید.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(WalletStates.upload_receipt)

@router.message(WalletStates.upload_receipt, F.photo)
async def process_card_receipt(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    amount = data["amount"]
    await state.clear()

    # Create transaction log
    tx_id = await create_transaction(
        user_id=message.from_user.id,
        amount=amount,
        type_='DEPOSIT',
        payment_method='CARD_TO_CARD',
        status='PENDING',
        receipt_photo_id=photo_id
    )

    user = await get_user(message.from_user.id)
    await message.answer(
        "✅ <b>رسید شما دریافت شد و برای ادمین ارسال گردید.</b>\n"
        "کیف پول شما به محض تایید پرداخت شارژ خواهد شد. با تشکر.",
        reply_markup=get_main_keyboard(user["is_admin"]),
        parse_mode="HTML"
    )

    # Notify all admins with inline confirmation buttons
    admins = await get_all_admins()
    esc_username = html.escape(message.from_user.username or 'بدون‌آیدی')
    admin_msg = (
        f"🔔 <b>تراکنش کارت به کارت جدید منتظر تایید!</b>\n\n"
        f"👤 کاربر: @{esc_username} (شناسه: <code>{message.from_user.id}</code>)\n"
        f"💰 مبلغ واریزی: <b>{amount:,} تومان</b>\n"
        f"🆔 شناسه تراکنش: <code>{tx_id}</code>\n\n"
        f"تصویر فیش ارسالی در زیر ضمیمه شده است:"
    )

    buttons = [
        [
            InlineKeyboardButton(text="✅ تایید و شارژ", callback_data=f"adm_confirm_pay_{tx_id}"),
            InlineKeyboardButton(text="❌ رد و مخالفت", callback_data=f"adm_reject_pay_{tx_id}")
        ]
    ]

    for admin in admins:
        try:
            await bot.send_photo(
                chat_id=admin["telegram_id"],
                photo=photo_id,
                caption=admin_msg,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Could not forward receipt to admin {admin['telegram_id']}: {e}")

# Admin actions on transaction confirmation
@router.callback_query(F.data.startswith("adm_confirm_pay_"))
async def admin_confirm_payment(call: CallbackQuery):
    tx_id = int(call.data.split("_")[-1])
    tx = await get_transaction(tx_id)
    if not tx or tx["status"] != "PENDING":
        await call.answer("❌ این تراکنش منقضی شده یا قبلاً رسیدگی شده است.", show_alert=True)
        return

    await call.answer()

    # Update transaction
    await update_transaction_status(tx_id, "APPROVED")
    # Credit user wallet
    await update_user_balance(tx["user_id"], tx["amount"])

    # Edit admin message
    await call.message.edit_caption(
        caption=call.message.caption + "\n\n🟢 <b>این تراکنش توسط ادمین تایید و شارژ گردید.</b>",
        reply_markup=None,
        parse_mode="HTML"
    )

    # Notify user
    try:
        user_msg = (
            f"🎉 <b>رسید کارت‌به‌کارت شما تایید شد!</b>\n\n"
            f"💰 مبلغ <b>{tx['amount']:,} تومان</b> به کیف پول شما اضافه شد.\n"
            f"🧾 شناسه پرداخت: <code>{tx_id}</code>"
        )
        await bot.send_message(chat_id=tx["user_id"], text=user_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Could not notify user {tx['user_id']} of approval: {e}")

@router.callback_query(F.data.startswith("adm_reject_pay_"))
async def admin_reject_payment(call: CallbackQuery):
    tx_id = int(call.data.split("_")[-1])
    tx = await get_transaction(tx_id)
    if not tx or tx["status"] != "PENDING":
        await call.answer("❌ این تراکنش منقضی شده یا قبلاً رسیدگی شده است.", show_alert=True)
        return

    await call.answer()

    # Update transaction
    await update_transaction_status(tx_id, "REJECTED")

    # Edit admin message
    await call.message.edit_caption(
        caption=call.message.caption + "\n\n🔴 <b>این تراکنش توسط ادمین رد شد.</b>",
        reply_markup=None,
        parse_mode="HTML"
    )

    # Notify user
    try:
        user_msg = (
            f"❌ <b>تراکنش کارت‌به‌کارت شما رد شد.</b>\n\n"
            f"تراکنش به شناسه <code>{tx_id}</code> مورد تایید مدیریت قرار نگرفت. در صورت وجود مغایرت با پشتیبانی تماس بگیرید."
        )
        await bot.send_message(chat_id=tx["user_id"], text=user_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Could not notify user {tx['user_id']} of rejection: {e}")

# --- ADMIN PANEL ---
@router.message(F.text == "⚙️ پنل مدیریت")
async def admin_panel_start(message: Message):
    user = await get_user(message.from_user.id)
    if not user or not user["is_admin"]:
        return

    # Stats
    all_users = await get_all_users()
    all_vps = await get_all_vps_servers()
    pending_receipts = await get_pending_card_payments()
    dollar_rate = await get_current_dollar_rate()

    text = (
        f"⚙️ <b>پنل مدیریت ربات</b>\n\n"
        f"📊 <b>آمار سیستم:</b>\n"
        f"   - تعداد کل کاربران: {len(all_users)}\n"
        f"   - تعداد سرورهای مجازی ابری فعال: {len(all_vps)}\n"
        f"   - فیش‌های کارت‌به‌کارت در انتظار تایید: {len(pending_receipts)}\n\n"
        f"💲 <b>نرخ فعلی دلار در سیستم:</b> <b>{dollar_rate:,} تومان</b>\n\n"
        f"جهت پیکربندی تنظیمات سیستم از منوی زیر استفاده کنید:"
    )

    buttons = [
        [
            InlineKeyboardButton(text="💲 تنظیم نرخ دلار", callback_data="adm_cfg_dollar"),
            InlineKeyboardButton(text="🔄 وضعیت خودکار نرخ دلار", callback_data="adm_cfg_autodollar")
        ],
        [
            InlineKeyboardButton(text="🏦 شماره کارت بانکی", callback_data="adm_cfg_cardnum"),
            InlineKeyboardButton(text="👤 نام صاحب کارت", callback_data="adm_cfg_cardowner")
        ],
        [
            InlineKeyboardButton(text="🚀 قیمت پنل نمایندگی", callback_data="adm_cfg_resprice"),
            InlineKeyboardButton(text="🔌 قیمت ترافیک اوتباند", callback_data="adm_cfg_outprice")
        ]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_cfg_"))
async def process_admin_configs(call: CallbackQuery, state: FSMContext):
    cfg_type = call.data.split("_")[-1]
    await call.answer()

    if cfg_type == "dollar":
        await call.message.answer("💲 <b>تنظیم نرخ دلار به صورت دستی (تومان):</b>\nلطفاً نرخ جدید دلار را وارد کنید:", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(AdminStates.input_dollar_rate)
    elif cfg_type == "autodollar":
        current = await get_setting("dollar_rate_auto", "1")
        new_val = "0" if current == "1" else "1"
        await set_setting("dollar_rate_auto", new_val)
        status_text = "روشن (دریافت لحظه‌ای از Wallex)" if new_val == "1" else "خاموش (فقط دستی)"
        await call.message.answer(f"✅ دریافت خودکار نرخ دلار تغییر یافت:\nوضعیت فعلی: <b>{status_text}</b>", parse_mode="HTML")
        await admin_panel_start(call.message)
    elif cfg_type == "cardnum":
        await call.message.answer("🏦 <b>شماره کارت بانکی جدید را وارد کنید:</b>", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(AdminStates.input_card_number)
    elif cfg_type == "cardowner":
        await call.message.answer("👤 <b>نام صاحب کارت جدید را وارد کنید:</b>", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(AdminStates.input_card_owner)
    elif cfg_type == "resprice":
        await call.message.answer("🚀 <b>قیمت جدید پنل نمایندگی ۵۰ کاربره (تومان) را وارد کنید:</b>", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(AdminStates.input_reseller_price)
    elif cfg_type == "outprice":
        await call.message.answer("🔌 <b>قیمت جدید اشتراک اوتباند ۱ ترابایتی (تومان) را وارد کنید:</b>", reply_markup=get_cancel_keyboard(), parse_mode="HTML")
        await state.set_state(AdminStates.input_outbound_price)

@router.message(AdminStates.input_dollar_rate, F.text)
async def process_new_dollar_rate(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
         await message.answer("❌ نرخ دلار باید یک عدد صحیح باشد. مجدداً وارد کنید:")
         return
    await set_setting("dollar_rate_manual", val)
    await state.clear()
    await message.answer(f"✅ نرخ دلار با موفقیت به <b>{int(val):,} تومان</b> تغییر یافت.", reply_markup=get_main_keyboard(True), parse_mode="HTML")

@router.message(AdminStates.input_card_number, F.text)
async def process_new_card_number(message: Message, state: FSMContext):
    val = message.text.strip()
    await set_setting("card_number", val)
    await state.clear()
    await message.answer(f"✅ شماره کارت بانکی با موفقیت به <b>{html.escape(val)}</b> تغییر یافت.", reply_markup=get_main_keyboard(True), parse_mode="HTML")

@router.message(AdminStates.input_card_owner, F.text)
async def process_new_card_owner(message: Message, state: FSMContext):
    val = message.text.strip()
    await set_setting("card_owner", val)
    await state.clear()
    await message.answer(f"✅ نام صاحب کارت با موفقیت به <b>{html.escape(val)}</b> تغییر یافت.", reply_markup=get_main_keyboard(True), parse_mode="HTML")

@router.message(AdminStates.input_reseller_price, F.text)
async def process_new_reseller_price(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
         await message.answer("❌ قیمت باید عدد صحیح باشد. مجدداً وارد کنید:")
         return
    await set_setting("reseller_price", val)
    await state.clear()
    await message.answer(f"✅ قیمت پنل نمایندگی با موفقیت به <b>{int(val):,} تومان</b> تغییر یافت.", reply_markup=get_main_keyboard(True), parse_mode="HTML")

@router.message(AdminStates.input_outbound_price, F.text)
async def process_new_outbound_price(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
         await message.answer("❌ قیمت باید عدد صحیح باشد. مجدداً وارد کنید:")
         return
    await set_setting("outbound_price", val)
    await state.clear()
    await message.answer(f"✅ قیمت اشتراک اوتباند با موفقیت به <b>{int(val):,} تومان</b> تغییر یافت.", reply_markup=get_main_keyboard(True), parse_mode="HTML")

# --- APP STARTUP & POLLING ---
async def on_startup():
    await init_db()
    logger.info("Initializing background scheduler...")
    scheduler = AsyncIOScheduler()
    # Run billing job every hour
    scheduler.add_job(run_hourly_billing, "interval", hours=1)
    scheduler.start()
    logger.info("Scheduler started successfully.")

async def main():
    await on_startup()
    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error starting polling: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run-billing":
        # Allow running billing manually via command line for testing/crons!
        asyncio.run(init_db())
        asyncio.run(run_hourly_billing())
    else:
        asyncio.run(main())

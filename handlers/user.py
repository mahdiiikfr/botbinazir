import asyncio
import sys
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
from apis import wallex, openstack_api, pasarguard

router = Router()

class TopUpStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_receipt = State()

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 کیف پول"), KeyboardButton(text="🚀 خرید سرور")],
            [KeyboardButton(text="👥 خرید پنل نمایندگی"), KeyboardButton(text="🛠 سرویس‌های من")]
        ],
        resize_keyboard=True
    )

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.create_user(message.from_user.id)
    await message.answer(
        "👋 سلام! به ربات فروش سرور و پنل خوش آمدید.\nلطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_keyboard()
    )

@router.message(F.text == "💰 کیف پول")
async def show_wallet(message: Message):
    user = await db.get_user(message.from_user.id)
    balance = user[2] if user else 0.0

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 شارژ کارت به کارت", callback_data="topup_c2c")],
        [InlineKeyboardButton(text="🌐 شارژ آنلاین (زرین‌پال)", callback_data="topup_zarinpal")]
    ])

    await message.answer(f"💰 موجودی کیف پول شما: {balance:,.0f} تومان", reply_markup=markup)

@router.callback_query(F.data == "topup_c2c")
async def topup_c2c(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("مبلغ مورد نظر برای شارژ را به تومان وارد کنید (کارت به کارت):")
    await state.set_state(TopUpStates.waiting_for_amount)

class ZarinPalStates(StatesGroup):
    waiting_for_amount = State()

@router.callback_query(F.data == "topup_zarinpal")
async def topup_zarinpal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("مبلغ مورد نظر برای شارژ را به تومان وارد کنید (زرین‌پال):")
    await state.set_state(ZarinPalStates.waiting_for_amount)

@router.message(ZarinPalStates.waiting_for_amount)
async def process_zarinpal_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفا مبلغ را به صورت عدد وارد کنید.")
        return

    amount = float(message.text)
    if amount < 10000:
        await message.answer("حداقل مبلغ شارژ ۱۰,۰۰۰ تومان است.")
        return

    # We would normally generate a payment link here
    from apis.zarinpal import request_payment

    msg = await message.answer("در حال ارتباط با درگاه بانکی...")

    # Pass user_id and amount to the callback URL so we can verify it
    callback_url = f"http://yourdomain.com/verify?user_id={message.from_user.id}&Amount={amount}"
    res = await request_payment(amount, f"شارژ کیف پول کاربر {message.from_user.id}", callback_url)

    if res["success"]:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="پرداخت", url=res["payment_url"])]
        ])
        await msg.edit_text(f"مبلغ: {amount:,.0f} تومان\n\nبرای پرداخت روی دکمه زیر کلیک کنید:", reply_markup=markup)
    else:
        await msg.edit_text("خطا در ایجاد لینک پرداخت. لطفا بعدا تلاش کنید.")

    await state.clear()

@router.message(TopUpStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفا مبلغ را به صورت عدد وارد کنید.")
        return

    amount = float(message.text)
    if amount < 10000:
        await message.answer("حداقل مبلغ شارژ ۱۰,۰۰۰ تومان است.")
        return

    await state.update_data(amount=amount)

    card_number = "1234-5678-9012-3456" # Placeholder
    owner = "نام صاحب حساب"

    await message.answer(
        f"لطفا مبلغ {amount:,.0f} تومان را به شماره کارت زیر واریز کنید:\n\n"
        f"💳 `{card_number}`\n👤 {owner}\n\n"
        f"سپس عکس فیش واریزی را ارسال کنید:",
        parse_mode="Markdown"
    )
    await state.set_state(TopUpStates.waiting_for_receipt)

@router.message(TopUpStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    file_id = message.photo[-1].file_id

    receipt_id = await db.add_pending_receipt(message.from_user.id, amount, file_id)

    # Notify admin (handled in admin.py or a signal, but we can do it directly if we import config)
    import config
    from aiogram import Bot

    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_receipt_{receipt_id}")],
        [InlineKeyboardButton(text="❌ رد", callback_data=f"reject_receipt_{receipt_id}")]
    ])

    try:
        await message.bot.send_photo(
            config.ADMIN_ID,
            photo=file_id,
            caption=f"درخواست شارژ جدید\nکاربر: {message.from_user.id}\nمبلغ: {amount:,.0f} تومان",
            reply_markup=admin_markup
        )
    except Exception as e:
        print(f"Error sending to admin: {e}")

    await message.answer("✅ فیش شما با موفقیت ثبت شد و پس از تایید ادمین، کیف پول شما شارژ خواهد شد.")
    await state.clear()

@router.message(F.text == "🚀 خرید سرور")
async def buy_server(message: Message):
    msg = await message.answer("⏳ در حال دریافت لیست پلن‌ها و محاسبه قیمت با نرخ روز...")

    usd_rate = await wallex.get_usd_rate()
    flavors = await openstack_api.list_flavors()

    if not flavors:
        await msg.edit_text("❌ خطا در ارتباط با سرور. لطفا بعدا تلاش کنید.")
        return

    text = f"نرخ محاسبه دلار: {usd_rate:,.0f} تومان\n\nلطفا پلن مورد نظر را انتخاب کنید:\n\n"

    markup = InlineKeyboardMarkup(inline_keyboard=[])

    for f in flavors:
        # Assuming flavor ram is in MB, let's create a mock monthly USD price based on RAM for calculation.
        # e.g., $5 for 1GB (1024MB), etc.
        # Since API doesn't provide price natively in standard openstack unless metadata is set,
        # we estimate: $0.005 per MB RAM per month.
        monthly_usd = (f['ram'] / 1024) * 5
        monthly_toman = monthly_usd * usd_rate * 1.5 # 50% profit
        hourly_toman = monthly_toman / 720

        btn_text = f"{f['name']} - {f['ram']}MB RAM - {hourly_toman:,.0f} T/h"
        markup.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy_vps_{f['id']}_{hourly_toman}")])

    await msg.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith("buy_vps_"))
async def process_buy_vps(callback: CallbackQuery):
    _, _, flavor_id, hourly_cost = callback.data.split("_")
    hourly_cost = float(hourly_cost)

    user = await db.get_user(callback.from_user.id)
    if not user or user[2] < hourly_cost * 24: # Require at least 24h balance
        await callback.answer(f"❌ موجودی کافی نیست. حداقل موجودی برای 24 ساعت: {(hourly_cost * 24):,.0f} تومان", show_alert=True)
        return

    # Now ask to select OS
    images = await openstack_api.list_images()
    if not images:
        await callback.message.edit_text("❌ خطایی رخ داد. هیچ تصویری (سیستم عامل) یافت نشد.")
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[])
    for img in images[:10]: # Limit to 10 for UI
        markup.inline_keyboard.append([
            InlineKeyboardButton(
                text=img['name'],
                callback_data=f"selectos_{flavor_id}_{hourly_cost}_{img['id']}"
            )
        ])

    await callback.message.edit_text("سیستم عامل مورد نظر را انتخاب کنید:", reply_markup=markup)

@router.callback_query(F.data.startswith("selectos_"))
async def process_select_os(callback: CallbackQuery):
    # split callback data
    parts = callback.data.split("_")
    flavor_id = parts[1]
    hourly_cost = float(parts[2])
    # The rest is the image ID (which might contain underscores or hyphens)
    image_id = "_".join(parts[3:])

    user = await db.get_user(callback.from_user.id)
    if not user or user[2] < hourly_cost * 24:
        await callback.answer("موجودی کافی نیست.", show_alert=True)
        return

    await callback.message.edit_text("⏳ در حال ساخت سرور... این فرآیند ممکن است ۱-۲ دقیقه زمان ببرد.")

    network_id = "76920584-3a19-4c67-bcc1-01407bedf558" # From prompt

    server = await openstack_api.create_server(
        name=f"VPS-{callback.from_user.id}",
        image_id=image_id,
        flavor_id=flavor_id,
        network_id=network_id
    )

    if not server:
        await callback.message.edit_text("❌ خطا در ساخت سرور.")
        return

    await db.add_server(callback.from_user.id, server['id'], f"VPS-{callback.from_user.id}", hourly_cost)

    await callback.message.edit_text(
        f"✅ سرور با موفقیت ساخته شد!\n\n"
        f"🖥 نام: VPS-{callback.from_user.id}\n"
        f"🔑 رمز عبور: `{server.get('admin_pass', 'در پنل مدیریت بررسی کنید')}`\n"
        f"هزینه ساعتی: {hourly_cost:,.0f} تومان\n\n"
        f"هزینه به صورت ساعتی از کیف پول شما کسر می‌شود.",
        parse_mode="Markdown"
    )

@router.message(F.text == "👥 خرید پنل نمایندگی")
async def buy_panel(message: Message):
    price = 800000
    user = await db.get_user(message.from_user.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="تایید و خرید (۸۰۰,۰۰۰ تومان)", callback_data="confirm_buy_panel")]
    ])

    await message.answer(
        "شما در حال خرید پنل نمایندگی Pasarguard (۵۰ کاربره) هستید.\n"
        f"قیمت: {price:,.0f} تومان\n\n"
        "آیا تایید می‌کنید؟",
        reply_markup=markup
    )

@router.callback_query(F.data == "confirm_buy_panel")
async def process_buy_panel(callback: CallbackQuery):
    price = 800000
    user = await db.get_user(callback.from_user.id)

    if not user or user[2] < price:
        await callback.answer("❌ موجودی کیف پول کافی نیست.", show_alert=True)
        return

    await callback.message.edit_text("⏳ در حال ساخت پنل...")

    panel = await pasarguard.create_operator(50)

    if not panel["success"]:
        await callback.message.edit_text("❌ خطا در ساخت پنل. لطفا به پشتیبانی اطلاع دهید.")
        return

    await db.update_balance(callback.from_user.id, -price)

    await callback.message.edit_text(
        f"✅ پنل نمایندگی شما با موفقیت ایجاد شد!\n\n"
        f"🔗 لینک ورود: {panel['login_url']}\n"
        f"👤 نام کاربری: `{panel['username']}`\n"
        f"🔑 رمز عبور: `{panel['password']}`",
        parse_mode="Markdown"
    )

@router.message(F.text == "🛠 سرویس‌های من")
async def my_services(message: Message):
    servers = await db.get_servers(message.from_user.id)

    if not servers:
        await message.answer("شما هیچ سرویس فعالی ندارید.")
        return

    for s in servers:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ریبوت", callback_data=f"action_reboot_{s['os_server_id']}")],
            [InlineKeyboardButton(text="🔁 ریبیلد", callback_data=f"action_rebuild_{s['os_server_id']}")],
            [InlineKeyboardButton(text="🔑 تغییر رمز", callback_data=f"action_changepw_{s['os_server_id']}")],
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"action_delete_{s['os_server_id']}")]
        ])

        await message.answer(
            f"🖥 سرور: {s['name']}\n"
            f"وضعیت: {s['status']}\n"
            f"هزینه ساعتی: {s['hourly_cost']:,.0f} تومان",
            reply_markup=markup
        )

@router.callback_query(F.data.startswith("action_"))
async def server_actions(callback: CallbackQuery):
    action, server_id = callback.data.split("_")[1:3]

    if action == "reboot":
        await openstack_api.reboot_server(server_id)
        await callback.answer("دستور ریبوت ارسال شد.", show_alert=True)
    elif action == "rebuild":
        # Hardcoding the first image for demonstration
        images = await openstack_api.list_images()
        if not images:
            await callback.answer("خطا در دریافت لیست تصاویر.", show_alert=True)
            return
        await callback.message.edit_text("در حال ریبیلد سرور...")
        import uuid
        new_password = str(uuid.uuid4())[:12]
        success = await openstack_api.rebuild_server(server_id, images[0]['id'], new_password)
        if success:
            await callback.message.edit_text(f"✅ سرور ریبیلد شد.\nرمز عبور جدید: `{new_password}`", parse_mode="Markdown")
        else:
            await callback.message.edit_text("❌ خطا در ریبیلد.")
    elif action == "changepw":
        await callback.message.edit_text("در حال تغییر رمز عبور...")
        import uuid
        new_password = str(uuid.uuid4())[:12]
        success = await openstack_api.change_server_password(server_id, new_password)
        if success:
            await callback.message.edit_text(f"✅ رمز عبور سرور تغییر کرد.\nرمز عبور جدید: `{new_password}`", parse_mode="Markdown")
        else:
            await callback.message.edit_text("❌ خطا در تغییر رمز عبور.")
    elif action == "delete":
        success = await openstack_api.delete_server(server_id)
        if success:
            await db.update_server_status(server_id, "deleted")
            await callback.message.edit_text("✅ سرور شما با موفقیت حذف شد و دیگر هزینه‌ای کسر نمی‌شود.")
        else:
            await callback.answer("❌ خطا در حذف سرور.", show_alert=True)

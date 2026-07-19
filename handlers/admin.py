import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
import db
import config

router = Router()

@router.callback_query(F.data.startswith("approve_receipt_") | F.data.startswith("reject_receipt_"))
async def handle_receipt_action(callback: CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("شما دسترسی ندارید.", show_alert=True)
        return

    action, _, receipt_id = callback.data.split("_")
    receipt_id = int(receipt_id)

    receipt = await db.get_pending_receipt(receipt_id)
    if not receipt:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("فیش یافت نشد یا قبلا بررسی شده است.")
        return

    if receipt['status'] != 'pending':
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"این فیش قبلا بررسی شده است. وضعیت: {receipt['status']}")
        return

    user_id = receipt['user_id']
    amount = receipt['amount']

    if action == "approve":
        await db.update_balance(user_id, amount)
        await db.update_receipt_status(receipt_id, 'approved')
        await db.add_transaction(user_id, amount, 'deposit_c2c', 'شارژ کارت به کارت')

        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ تایید شد.", reply_markup=None)

        try:
            await callback.bot.send_message(user_id, f"✅ فیش واریزی شما تایید شد.\nمبلغ {amount:,.0f} تومان به کیف پول شما اضافه شد.")
        except:
            pass

    elif action == "reject":
        await db.update_receipt_status(receipt_id, 'rejected')
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ رد شد.", reply_markup=None)

        try:
            await callback.bot.send_message(user_id, f"❌ فیش واریزی شما توسط مدیریت رد شد.")
        except:
            pass

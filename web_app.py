from aiohttp import web
import db
from apis import zarinpal

routes = web.RouteTableDef()

@routes.get('/verify')
async def verify_payment(request):
    authority = request.query.get('Authority')
    status = request.query.get('Status')
    amount_str = request.query.get('Amount') # Assuming we pass this in state or query
    user_id = request.query.get('user_id')

    if status == 'OK' and authority and amount_str and user_id:
        amount = float(amount_str)
        res = await zarinpal.verify_payment(amount, authority)
        if res.get("success"):
            await db.update_balance(int(user_id), amount)
            await db.add_transaction(int(user_id), amount, 'deposit_zarinpal', f'Zarinpal deposit ref: {res.get("ref_id")}')
            return web.Response(text=f"Payment Successful! Ref ID: {res.get('ref_id')}. You can return to the bot.")

    return web.Response(text="Payment Failed or Canceled.")

def init_web():
    app = web.Application()
    app.add_routes(routes)
    return app

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CartCheckout(StatesGroup):
    confirming = State()


class AdminAuth(StatesGroup):
    waiting_password = State()


class AdminCategory(StatesGroup):
    entering_name = State()
    entering_position = State()
    confirming_delete = State()


class AdminProduct(StatesGroup):
    entering_name = State()
    entering_description = State()
    entering_price = State()
    choosing_category = State()
    entering_delivery_type = State()
    entering_delivery_payload = State()
    entering_photo = State()
    entering_keys_batch = State()
    confirming_delete = State()


class AdminOrder(StatesGroup):
    confirming_fulfill = State()
    confirming_cancel = State()
    confirming_refund = State()

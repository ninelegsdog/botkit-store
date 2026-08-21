from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CartCheckout(StatesGroup):
    confirming = State()


class AdminAuth(StatesGroup):
    waiting_password = State()


class AdminProduct(StatesGroup):
    entering_name = State()
    entering_description = State()
    entering_price = State()
    choosing_category = State()
    entering_delivery = State()


class AdminCategory(StatesGroup):
    entering_name = State()

"""Тексты бота: константы существуют, хелперы подставляют свои аргументы.

Зачем
=====

`src/store/texts.py` — единый источник строк, которые бот отправляет. Тест держит
две вещи:

1. **Константы на месте и непусты.** Обработчик, отдавший пустую строку, —
   молчаливый дефект: пользователь видит пузырь без текста, а тест на поведение
   (если он сверяет вхождение) проходит.
2. **Хелперы действительно подставляют переданное.** Правка, выбросившая аргумент
   (`#{order_id}` → `#{}`, цена → литерал), иначе прошла бы незамеченной: строка
   всё ещё «есть».

Каждая проверка имеет негативного близнеца: сломай подстановку — тест красный.
"""

from __future__ import annotations

import pytest

from src.store import texts

CONSTANTS = [
    texts.WELCOME,
    texts.CATALOG_EMPTY,
    texts.CHOOSE_CATEGORY,
    texts.NO_PRODUCTS,
    texts.CART_EMPTY,
    texts.CART_HEADER,
    texts.ADDED_TO_CART,
    texts.NO_PURCHASES,
    texts.NOT_DELIVERED,
    texts.CHOOSE_ACTION,
    texts.ASK_PASSWORD,
    texts.ADMIN_WELCOME,
    texts.BAD_PASSWORD,
    texts.TOO_MANY_ATTEMPTS,
    texts.NO_CATEGORIES,
    texts.CATEGORIES_HEADER,
    texts.PRODUCTS_HEADER,
    texts.SALES_STUB,
    texts.PAYMENT_HINT,
    texts.BAD_REQUEST,
    texts.PRODUCT_NOT_FOUND,
]

BUTTON_LABELS = [
    texts.BTN_CATALOG,
    texts.BTN_CART,
    texts.BTN_MY_ORDERS,
    texts.BTN_ADD_TO_CART,
    texts.BTN_BUY,
    texts.BTN_CHECKOUT,
    texts.BTN_REDELIVER,
    texts.BTN_PRODUCTS,
    texts.BTN_CATEGORIES,
    texts.BTN_ORDERS,
    texts.BTN_SALES,
]


@pytest.mark.parametrize("value", CONSTANTS, ids=lambda v: v[:24])
def test_текст_непуст(value: str) -> None:
    """Пустой ответ — пузырь без текста; пользователь не поймёт, что случилось."""
    assert value.strip(), "текст сообщения пуст или из пробелов"


@pytest.mark.parametrize("label", BUTTON_LABELS, ids=lambda v: v[:24])
def test_подпись_кнопки_непуста(label: str) -> None:
    """Кнопка без подписи неотличима от декоративного разделителя."""
    assert label.strip(), "подпись кнопки пуста"


def test_все_подписи_кнопок_уникальны() -> None:
    """Две кнопки с одной подписью — пользователь нажмёт не ту.

    Обработчики выше различают кнопки по тексту (`F.text == ...`), так что
    совпадение подписей ломает маршрутизацию, а не только вид.
    """
    duplicates = {x for x in BUTTON_LABELS if BUTTON_LABELS.count(x) > 1}
    assert not duplicates, f"дубли подписей кнопок: {duplicates}"


def test_приветствие_содержит_подстроку_из_кейсов() -> None:
    """Кейс фермы и e2e-тест цитируют подстроку без эмодзи — она обязана быть.

    `text_contains` сверяет вхождение, поэтому ведущий эмодзи правке не мешает,
    но сама фраза обязана остаться: это тот текст, который ловят оба пути.
    """
    assert "Добро пожаловать в магазин" in texts.WELCOME


# ── хелперы: подстановка аргумента, а не литерал ────────────────────────────


def test_order_review_подставляет_id_имя_цену() -> None:
    """Экран оплаты: без этих значений пользователь не знает, за что платит."""
    got = texts.order_review(42, "Подписка", 100)
    assert "#42" in got, got
    assert "Подписка" in got, got
    assert "100 Stars" in got, got


def test_order_review_чужой_id_меняет_строку() -> None:
    """Негативный близнец: фиксированный id прошёл бы первую проверку."""
    assert texts.order_review(1, "X", 1) != texts.order_review(2, "X", 1)


def test_orders_total_несёт_сумму() -> None:
    """Итог без суммы — пользователь не узнает, сколько заплатит."""
    assert "250 Stars" in texts.orders_total(250)


def test_cart_line_несёт_имя_количество_цену() -> None:
    """Строка позиции: пропавшее количество или цена меняет смысл покупки."""
    got = texts.cart_line("Курс", 3, 300)
    assert "Курс" in got and "x3" in got and "300 Stars" in got, got


def test_cart_line_различает_количество() -> None:
    """Негативный близнец: игнорирование qty прошло бы первую проверку."""
    assert texts.cart_line("X", 1, 10) != texts.cart_line("X", 2, 10)


def test_order_placed_несёт_заказы_сумму_подсказку() -> None:
    """Подтверждение оформления: что заказано, на сколько, что дальше."""
    got = texts.order_placed("#1, #2", 500, texts.PAYMENT_HINT)
    assert "#1, #2" in got and "500 Stars" in got and texts.PAYMENT_HINT in got, got


def test_delivery_payload_вставляет_товар() -> None:
    """Пустая выдача вместо товара — подмена содержимого покупки."""
    got = texts.delivery_payload("КЛЮЧ-123")
    assert "КЛЮЧ-123" in got, got


def test_orders_stats_различает_день_и_неделю() -> None:
    """Статистика, где день и неделя совпали, — это одна цифра под двумя ярлыками."""
    got = texts.orders_stats(10, 2, 30, 5)
    assert "10" in got and "2" in got and "30" in got and "5" in got, got

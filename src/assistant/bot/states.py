"""FSM states of every dialog. The state name is stored in fsm_state, so do not rename them."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class RatesForm(StatesGroup):
    amount = State()


class NoteForm(StatesGroup):
    text = State()


class ReminderForm(StatesGroup):
    text = State()
    when = State()


class HabitForm(StatesGroup):
    name = State()


class SettingsForm(StatesGroup):
    city = State()
    time = State()

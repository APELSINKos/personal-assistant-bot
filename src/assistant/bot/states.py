"""FSM states of every dialog. The state name is stored in fsm_state, so do not rename them."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class RatesForm(StatesGroup):
    amount = State()


class NoteForm(StatesGroup):
    text = State()
    edit = State()  # a new text for the note of data["note_id"]
    items = State()  # new items for the note of data["note_id"]
    checklist = State()  # a new checklist: its title, then its items
    search = State()  # words to look for in the notes


class ReminderForm(StatesGroup):
    text = State()  # waiting for a phrase («➕ Добавить»)
    time = State()  # the phrase has no usable time yet
    confirm = State()  # a confirmation card is shown


class HabitForm(StatesGroup):
    name = State()
    rename = State()


class ScheduleForm(StatesGroup):
    group = State()  # a MIREA group name to search for
    url = State()  # a calendar link
    file = State()  # an .ics file


class MoneyForm(StatesGroup):
    category = State()  # the name of a new category for a noted entry
    budget = State()  # a monthly budget: the total one or a category's


class SettingsForm(StatesGroup):
    city = State()
    time = State()
    add_city = State()  # the name of a city to add to the weather's list

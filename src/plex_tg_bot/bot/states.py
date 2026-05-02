from aiogram.fsm.state import State, StatesGroup


class RequestFSM(StatesGroup):
    awaiting_email = State()
    awaiting_referrer = State()


class RejectFSM(StatesGroup):
    awaiting_reason = State()

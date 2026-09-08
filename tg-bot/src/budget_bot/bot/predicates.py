"""Shared message filters."""

from aiogram import F

# Text handlers bound to an FSM state must not swallow slash commands.
#
# Router order alone does not protect them: a command whose router is
# included after the current state's router never gets the chance to match.
# In live testing, typing /report at the "name your category" prompt created
# a category literally named "/report", because categories.router precedes
# reports.router. Excluding commands lets the update fall through to whichever
# router owns it.
#
# A non-text message (sticker, photo) has text=None, so this resolves to
# True and such messages still reach the dialog, which rejects them on its
# own terms.
NOT_A_COMMAND = ~F.text.startswith("/")

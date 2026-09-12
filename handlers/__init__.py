from aiogram import Router

from . import admin, business, commands, subscription, menu


def build_root_router() -> Router:
    """Assemble every feature router into one, in a deliberate priority order.

    Business updates are registered first since they are the bot's core
    purpose and must never be shadowed by a loosely matching command filter.
    `menu` is last since it only matches exact reply-keyboard button text.
    """
    root = Router(name="root")
    root.include_router(business.router)
    root.include_router(subscription.router)
    root.include_router(admin.router)
    root.include_router(commands.router)
    root.include_router(menu.router)
    return root

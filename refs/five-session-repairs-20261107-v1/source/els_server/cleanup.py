"""Run every teardown stage and preserve every original failure."""


def cleanup_all(*actions):
    errors = []
    for action in actions:
        try:
            action()
        except BaseException as error:
            errors.append(error)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup('Multiple cleanup failures', errors)


async def cleanup_all_async(*actions):
    """Retain async teardown ownership through cancellation, in original order."""
    import asyncio
    from inspect import isawaitable

    async def run():
        errors = []
        for action in actions:
            try:
                result = action()
                if isawaitable(result):
                    await result
            except BaseException as error:
                errors.append(error)
        return errors

    cleanup = asyncio.create_task(run(), name='resource-cleanup')
    try:
        errors = await asyncio.shield(cleanup)
    except asyncio.CancelledError as error:
        # A cancelled owner still waits for all real resource operations.
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        errors = cleanup.result()
        errors.insert(0, error)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup('Multiple cleanup failures', errors)

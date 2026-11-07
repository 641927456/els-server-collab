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

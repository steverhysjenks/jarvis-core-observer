def test_core_modules_import():
    from app.context import areas
    from app.context import availability
    from app.context import calendar
    from app.context import history
    from app.context import home
    from app.context import places
    from app.context import user

    from app.observer import context
    from app.observer import enrichment
    from app.observer import evaluator
    from app.observer import action_policy
    from app.observer import action_executor

    from app.judgement import qwen

    from app.storage import ledger

    from app.voice import routing
    from app.voice import announcements
    from app.voice import replay

    assert areas
    assert availability
    assert calendar
    assert history
    assert home
    assert places
    assert user
    assert context
    assert enrichment
    assert evaluator
    assert action_policy
    assert action_executor
    assert qwen
    assert ledger
    assert routing
    assert announcements
    assert replay

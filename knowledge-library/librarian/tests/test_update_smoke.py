def test_update_imports():
    from librarian import update
    assert callable(update.cmd_diff)
    assert callable(update.cmd_queue)
    assert callable(update.cmd_ingest)
    assert callable(update.cmd_materialize)
    assert callable(update.cmd_verify)

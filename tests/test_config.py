from src import config, model_manager


def test_default_preset_exists():
    assert config.DEFAULT_PRESET in config.MODEL_PRESETS


def test_presets_are_gguf():
    for preset in config.MODEL_PRESETS.values():
        assert preset.filename.endswith(".gguf")


def test_context_budget_leaves_room_for_commits():
    assert config.N_CTX - config.ANSWER_TOKENS - config.PROMPT_OVERHEAD_TOKENS >= 2048


def test_model_path_is_inside_data_dir():
    assert model_manager.model_path().parent == config.MODELS_DIR


def test_default_n_threads_is_positive():
    assert config.default_n_threads() >= 1

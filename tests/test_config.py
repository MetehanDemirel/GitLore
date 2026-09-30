from src import config, model_manager


def test_default_preset_exists():
    assert config.DEFAULT_PRESET in config.MODEL_PRESETS


def test_presets_are_gguf():
    for preset in config.MODEL_PRESETS.values():
        assert preset.filename.endswith(".gguf")


def test_context_budget_leaves_room_for_commits():
    assert config.MAX_PROMPT_TOKENS + config.ANSWER_TOKENS <= config.N_CTX


def test_model_path_is_inside_data_dir():
    preset = config.MODEL_PRESETS[config.DEFAULT_PRESET]
    assert model_manager.model_path(preset).parent == config.MODELS_DIR


def test_default_n_threads_is_positive():
    assert config.default_n_threads() >= 1

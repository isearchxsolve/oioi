"""QA suite for agent_contracts — pydantic validation on the 7-agent pipeline.

Asserts real validation behavior: required fields reject empty payloads, valid
payloads construct, enums round-trip, and the orchestrator interface is
abstract.
"""
from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import agent_contracts as ac


# --- Builders ---------------------------------------------------------------

def _script_out():
    return ac.ScriptwriterOutput(
        title="Test Film",
        description="A test story",
        scenes=[{"prompt": "opening", "duration": 5}],
        characters=["Hero"],
    )


def _art_out():
    return ac.ArtDirectorOutput(
        visual_style="cyberpunk",
        color_palette=["#000000", "#ffffff"],
        character_sheet_prompt="sheet",
        scene_style_prompt="scene",
    )


def _char_out():
    return ac.CharacterDesignerOutput(
        characters=[{"name": "Hero", "description": "lead", "prompt": "p"}]
    )


def _scene_out():
    return ac.SceneDesignerOutput(
        scenes=[{"description": "d", "prompt": "p", "style": "s"}]
    )


def _anim_out():
    return ac.AnimatorOutput(animations=[{"scene": 1, "action": "walk"}])


def _sound_out():
    return ac.SoundDirectorOutput(
        music_prompt="ambient",
        sound_effects=[{"scene": 1, "effect": "rain"}],
    )


# --- AgentType enum ---------------------------------------------------------

def test_agent_type_has_seven_roles():
    assert len(list(ac.AgentType)) == 7


@pytest.mark.parametrize("agent", list(ac.AgentType))
def test_agent_type_value_is_lowercase(agent):
    assert agent.value == agent.value.lower()


@pytest.mark.parametrize("agent", list(ac.AgentType))
def test_agent_type_roundtrips(agent):
    assert ac.AgentType(agent.value) is agent


@pytest.mark.parametrize("expected", [
    "scriptwriter", "art_director", "character_designer", "scene_designer",
    "animator", "sound_director", "director",
])
def test_agent_type_expected_values_present(expected):
    assert expected in {a.value for a in ac.AgentType}


# --- Scriptwriter -----------------------------------------------------------

def test_scriptwriter_input_requires_prompt():
    with pytest.raises(ValidationError):
        ac.ScriptwriterInput()


def test_scriptwriter_input_defaults():
    inp = ac.ScriptwriterInput(prompt="idea")
    assert inp.duration is None
    assert inp.style is None


def test_scriptwriter_output_requires_all_fields():
    with pytest.raises(ValidationError):
        ac.ScriptwriterOutput()


def test_scriptwriter_output_constructs():
    out = _script_out()
    assert out.title == "Test Film"
    assert out.characters == ["Hero"]


# --- Art Director -----------------------------------------------------------

def test_art_director_input_requires_script():
    with pytest.raises(ValidationError):
        ac.ArtDirectorInput()


def test_art_director_input_accepts_script():
    inp = ac.ArtDirectorInput(scriptwriter_output=_script_out())
    assert inp.scriptwriter_output.title == "Test Film"


def test_art_director_output_requires_fields():
    with pytest.raises(ValidationError):
        ac.ArtDirectorOutput()


def test_art_director_output_constructs():
    assert _art_out().color_palette == ["#000000", "#ffffff"]


# --- Character / Scene designers -------------------------------------------

def test_character_designer_input_requires_art():
    with pytest.raises(ValidationError):
        ac.CharacterDesignerInput()


def test_character_designer_output_requires_characters():
    with pytest.raises(ValidationError):
        ac.CharacterDesignerOutput()


def test_scene_designer_input_requires_art():
    with pytest.raises(ValidationError):
        ac.SceneDesignerInput()


def test_scene_designer_output_requires_scenes():
    with pytest.raises(ValidationError):
        ac.SceneDesignerOutput()


# --- Animator ---------------------------------------------------------------

def test_animator_input_requires_both_designers():
    with pytest.raises(ValidationError):
        ac.AnimatorInput()


def test_animator_input_accepts_both():
    inp = ac.AnimatorInput(
        scene_designer_output=_scene_out(),
        character_designer_output=_char_out(),
    )
    assert inp.scene_designer_output.scenes[0]["style"] == "s"


def test_animator_output_requires_animations():
    with pytest.raises(ValidationError):
        ac.AnimatorOutput()


# --- Sound Director ---------------------------------------------------------

def test_sound_director_input_requires_script_and_animation():
    with pytest.raises(ValidationError):
        ac.SoundDirectorInput()


def test_sound_director_output_voice_over_optional():
    assert _sound_out().voice_over is None


def test_sound_director_output_requires_music_and_sfx():
    with pytest.raises(ValidationError):
        ac.SoundDirectorOutput()


# --- Director ---------------------------------------------------------------

def test_director_input_requires_all_six():
    with pytest.raises(ValidationError):
        ac.DirectorInput()


def test_director_input_accepts_all():
    inp = ac.DirectorInput(
        scriptwriter_output=_script_out(),
        art_director_output=_art_out(),
        character_designer_output=_char_out(),
        scene_designer_output=_scene_out(),
        animator_output=_anim_out(),
        sound_director_output=_sound_out(),
    )
    assert inp.scriptwriter_output.title == "Test Film"


def test_director_output_requires_notes_and_approval():
    with pytest.raises(ValidationError):
        ac.DirectorOutput()


def test_director_output_revisions_default_empty():
    out = ac.DirectorOutput(final_notes="ok", approved=True)
    assert out.revisions == []


def test_director_output_constructs():
    out = ac.DirectorOutput(final_notes="ok", approved=False, revisions=["fix pacing"])
    assert out.approved is False
    assert out.revisions == ["fix pacing"]


# --- Orchestrator interface -------------------------------------------------

def test_orchestrator_is_abstract():
    with pytest.raises(TypeError):
        ac.AgentOrchestrator()


@pytest.mark.parametrize("method", [
    "run_scriptwriter", "run_art_director", "run_character_designer",
    "run_scene_designer", "run_animator", "run_sound_director",
    "run_director", "run_pipeline",
])
def test_orchestrator_defines_method(method):
    assert hasattr(ac.AgentOrchestrator, method)

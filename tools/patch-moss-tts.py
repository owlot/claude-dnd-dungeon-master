#!/usr/bin/env python3
"""
Patch MOSS-TTS v1.5 cached model files for compatibility with transformers >= 4.57.

MOSS-TTS was released against transformers ~4.57.1 but several internal APIs were
renamed or made stricter between that release and the current version. This script
re-applies all required patches idempotently — safe to run multiple times.

Also patches the transformers processing_utils.py to allow custom audio_tokenizer
model types that don't inherit PreTrainedAudioTokenizerBase.

Usage:
    python3 tools/patch-moss-tts.py [--check]

Options:
    --check     Dry run — report which patches are needed without applying them.

Run this after:
    - Clearing the HuggingFace model cache
    - Upgrading transformers
    - Any "MODALITY_TO_BASE_CLASS_MAPPING", "initialization", or "pad_token_id" errors
"""

import sys
import os
import re
import glob

DRY_RUN = "--check" in sys.argv

HF_MODULES = os.path.expanduser(
    "~/.cache/huggingface/modules/transformers_modules/OpenMOSS_hyphen_Team"
)

# Find the tts conda env's transformers install
CONDA_SITE = os.path.expanduser(
    "~/.conda/envs/tts/lib/python3.12/site-packages/transformers"
)

applied = []
needed = []


def patch(path, old, new, description):
    """Apply a single string replacement to a file. Idempotent."""
    if not os.path.exists(path):
        print(f"  SKIP (file not found): {os.path.basename(path)}")
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if new in content:
        print(f"  OK   already applied: {description}")
        return
    if old not in content:
        print(f"  WARN old string not found (may already be patched differently): {description}")
        needed.append(description)
        return
    needed.append(description)
    if DRY_RUN:
        print(f"  NEED {description}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace(old, new, 1))
    applied.append(description)
    print(f"  PATCHED: {description}")


def patch_all(base_dir, label):
    cfg  = os.path.join(base_dir, "configuration_moss_tts.py")
    mdl  = os.path.join(base_dir, "modeling_moss_tts.py")
    proc = os.path.join(base_dir, "processing_moss_tts.py")

    print(f"\n[{label}]")

    # 1. configuration_moss_tts.py — pad_token_id overwritten to None by super().__init__(**kwargs)
    patch(
        cfg,
        "        super().__init__(**kwargs)\n\n    def to_dict(self):",
        (
            "        super().__init__(**kwargs)\n"
            "        # Ensure pad_token_id is never None — config.json stores null but generate() needs an int.\n"
            "        if self.pad_token_id is None:\n"
            "            self.pad_token_id = pad_token_id if pad_token_id is not None else 151643\n"
            "\n    def to_dict(self):"
        ),
        "cfg: pad_token_id None guard after super().__init__",
    )

    # 2. modeling_moss_tts.py — transformers.initialization removed in 4.57
    patch(
        mdl,
        "from transformers import initialization as init",
        "import torch.nn.init as init  # transformers.initialization removed in 4.57",
        "mdl: replace transformers.initialization with torch.nn.init",
    )

    # 3. modeling_moss_tts.py — get_input_embeddings called with no args by tie_weights()
    patch(
        mdl,
        "    def get_input_embeddings(self, input_ids: torch.LongTensor) -> torch.Tensor:",
        "    def get_input_embeddings(self, input_ids: torch.LongTensor = None):",
        "mdl: make get_input_embeddings input_ids optional",
    )
    patch(
        mdl,
        (
            "        # Base Text/Content Embedding\n"
            "        # input_ids[..., 0] is standard text or semantic tokens\n"
            "        inputs_embeds = self.language_model.get_input_embeddings()(input_ids[..., 0])"
        ),
        (
            "        # Called with no args by transformers tie_weights — return the base embedding layer.\n"
            "        if input_ids is None:\n"
            "            return self.language_model.get_input_embeddings()\n"
            "\n"
            "        # Base Text/Content Embedding\n"
            "        # input_ids[..., 0] is standard text or semantic tokens\n"
            "        inputs_embeds = self.language_model.get_input_embeddings()(input_ids[..., 0])"
        ),
        "mdl: early-return embedding layer when input_ids is None",
    )

    # 4. processing_moss_tts.py — skip super().__init__ which enforces feature_extractor+tokenizer pair
    patch(
        proc,
        (
            "        super().__init__(tokenizer=tokenizer, audio_tokenizer=audio_tokenizer, **kwargs)\n"
            "\n"
            "        # Explicit assignments for type-checkers; ProcessorMixin sets these too.\n"
            "        self.tokenizer = tokenizer\n"
            "        self.audio_tokenizer = audio_tokenizer"
        ),
        (
            "        # Skip ProcessorMixin.__init__ — it enforces feature_extractor+tokenizer pair\n"
            "        # and PreTrainedAudioTokenizerBase for audio_tokenizer, both incompatible with\n"
            "        # MOSS-TTS on transformers>=4.57. Set required attributes directly instead.\n"
            "        self.tokenizer = tokenizer\n"
            "        self.audio_tokenizer = audio_tokenizer"
        ),
        "proc: skip ProcessorMixin.__init__ to avoid strict type validation",
    )

    # 5. processing_moss_tts.py — pad_token_id None guard in _pad()
    patch(
        proc,
        "        pad_input_ids[..., 0][other_channel_mask] = self.model_config.pad_token_id",
        (
            "        pad_token_id = self.model_config.pad_token_id\n"
            "        if pad_token_id is None:\n"
            "            pad_token_id = 151643  # default from MossTTSDelayConfig\n"
            "        pad_input_ids[..., 0][other_channel_mask] = pad_token_id"
        ),
        "proc: pad_token_id None guard in _pad()",
    )


def patch_audio_tokenizer_configs():
    """Audio tokenizer configs import PreTrainedConfig from the wrong path in 4.57."""
    pattern = os.path.join(HF_MODULES, "MOSS_hyphen_Audio_hyphen_Tokenizer", "*", "configuration_moss_audio_tokenizer.py")
    files = glob.glob(pattern)
    if not files:
        print("\n[Audio Tokenizer configs] No files found — skipping")
        return
    print(f"\n[Audio Tokenizer configs] ({len(files)} files)")
    for f in files:
        patch(
            f,
            "from transformers.configuration_utils import PreTrainedConfig",
            "from transformers import PretrainedConfig as PreTrainedConfig",
            f"audio_tokenizer cfg: fix PreTrainedConfig import path in {os.path.basename(os.path.dirname(f))}",
        )


def patch_transformers_processing_utils():
    """Relax the audio_tokenizer type check in transformers' ProcessorMixin."""
    path = os.path.join(CONDA_SITE, "processing_utils.py")
    print(f"\n[transformers processing_utils.py]")

    # 1. Add AutoModel -> PreTrainedModel to AUTO_TO_BASE_CLASS_MAPPING
    patch(
        path,
        (
            '    "AutoVideoProcessor": "BaseVideoProcessor",\n'
            "}"
        ),
        (
            '    "AutoVideoProcessor": "BaseVideoProcessor",\n'
            '    "AutoModel": "PreTrainedModel",  # needed for MOSS-TTS audio_tokenizer\n'
            "}"
        ),
        "transformers: add AutoModel to AUTO_TO_BASE_CLASS_MAPPING",
    )

    # 2. Replace strict PreTrainedAudioTokenizerBase check with a pass
    patch(
        path,
        (
            "            # Check audio tokenizer for its class but do not treat it as attr to avoid saving weights\n"
            "            if optional_attribute == \"audio_tokenizer\" and optional_attribute_value is not None:\n"
            "                proper_class = self.check_argument_for_proper_class(optional_attribute, optional_attribute_value)\n"
            "\n"
            "                if not (is_torch_available() and isinstance(optional_attribute_value, PreTrainedAudioTokenizerBase)):\n"
            "                    raise ValueError(\n"
            "                        f\"Tried to use `{proper_class}` for audio tokenization. However, this class is not\"\n"
            "                        \" registered for audio tokenization.\"\n"
            "                    )"
        ),
        (
            "            # Check audio tokenizer for its class but do not treat it as attr to avoid saving weights\n"
            "            if optional_attribute == \"audio_tokenizer\" and optional_attribute_value is not None:\n"
            "                # Skip strict type enforcement — custom models (e.g. MOSS-TTS) use PreTrainedModel\n"
            "                # subclasses that don't inherit PreTrainedAudioTokenizerBase.\n"
            "                pass"
        ),
        "transformers: relax audio_tokenizer type check (allow PreTrainedModel subclasses)",
    )


# --- Run all patches ---

print("MOSS-TTS compatibility patcher")
print(f"Mode: {'DRY RUN (--check)' if DRY_RUN else 'APPLY'}")
print(f"HF modules: {HF_MODULES}")
print(f"transformers: {CONDA_SITE}")

tts_dir = os.path.join(HF_MODULES, "MOSS_hyphen_TTS_hyphen_v1_dot_5")
vg_dir  = os.path.join(HF_MODULES, "MOSS_hyphen_VoiceGenerator")

for model_dir, label in [
    (tts_dir, "MOSS-TTS-v1.5"),
    (vg_dir,  "MOSS-VoiceGenerator"),
]:
    commits = sorted(glob.glob(os.path.join(model_dir, "*"))) if os.path.exists(model_dir) else []
    if not commits:
        print(f"\n[{label}] Not found in cache — skipping")
        continue
    for commit in commits:
        if os.path.isdir(commit):
            patch_all(commit, f"{label}/{os.path.basename(commit)[:12]}")

patch_audio_tokenizer_configs()
patch_transformers_processing_utils()

print(f"\n{'='*50}")
if DRY_RUN:
    print(f"Patches needed: {len(needed)}")
else:
    print(f"Patches applied: {len(applied)}")
    already = len(needed) - len(applied)
    if already:
        print(f"Already applied: {already}")
print("Done.")

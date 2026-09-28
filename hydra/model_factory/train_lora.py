# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""LoRA / QLoRA fine-tuning and adapter merging (run as a separate process).

    python -m hydra.model_factory.train_lora job.json
    python -m hydra.model_factory.train_lora --merge <base> <adapter_dir> <output_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def train(cfg_path: str) -> None:
    import torch
    from datasets import load_dataset  # type: ignore
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # type: ignore
    from transformers import (  # type: ignore
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    job = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    tok = AutoTokenizer.from_pretrained(job["base_model"])
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    kwargs: dict = {"torch_dtype": torch.bfloat16 if torch.cuda.is_available() else torch.float32}
    if job["method"] == "qlora":
        from transformers import BitsAndBytesConfig  # type: ignore

        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_compute_dtype=torch.bfloat16)
        kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(job["base_model"], **kwargs)
    if job["method"] == "qlora":
        model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(r=job["r"], lora_alpha=job["alpha"], lora_dropout=job["dropout"],
                                             target_modules=job["target_modules"], task_type="CAUSAL_LM"))

    data = load_dataset("json", data_files=job["dataset"], split="train")

    def encode(example):
        text = tok.apply_chat_template(example["messages"], tokenize=False)
        return tok(text, truncation=True, max_length=job["max_seq_length"])

    data = data.map(encode, remove_columns=data.column_names)
    trainer = Trainer(
        model=model,
        train_dataset=data,
        data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
        args=TrainingArguments(output_dir=job["output_dir"], num_train_epochs=job["epochs"],
                               per_device_train_batch_size=job["batch_size"],
                               gradient_accumulation_steps=job["gradient_accumulation"],
                               learning_rate=job["learning_rate"], logging_steps=10, save_strategy="epoch",
                               bf16=torch.cuda.is_available(), report_to=[]),
    )
    trainer.train()
    model.save_pretrained(job["output_dir"])
    tok.save_pretrained(job["output_dir"])


def merge(base: str, adapter: str, output: str) -> None:
    import torch
    from peft import PeftModel  # type: ignore
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    model.save_pretrained(output, safe_serialization=True)
    AutoTokenizer.from_pretrained(base).save_pretrained(output)


if __name__ == "__main__":
    if sys.argv[1] == "--merge":
        merge(*sys.argv[2:5])
    else:
        train(sys.argv[1])

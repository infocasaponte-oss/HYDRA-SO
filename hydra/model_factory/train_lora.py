# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""LoRA / QLoRA fine-tuning and adapter merging (run as a separate process).

    python -m hydra.model_factory.train_lora job.json
    python -m hydra.model_factory.train_lora --merge <base> <adapter_dir> <output_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from hydra.training.verified_corpus import sha256


def normalize_job(raw: dict) -> dict:
    """Accept both Model Factory jobs and Training Lab recipes."""
    job = dict(raw)
    for key, alias, default in (("dataset", "train", None), ("r", "lora_rank", 8),
                                ("alpha", "lora_alpha", 16), ("dropout", "lora_dropout", 0.05),
                                ("max_seq_length", "max_length", 512),
                                ("gradient_accumulation", "gradient_accumulation", 4)):
        job.setdefault(key, job.get(alias, default))
    job.setdefault("target_modules", ["q_proj", "v_proj"])
    job.setdefault("seed", 42)
    if job.get("method") not in ("lora", "qlora"):
        raise ValueError("PEFT backend supports lora and qlora only")
    if not job.get("dataset"):
        raise ValueError("training dataset is required")
    return job


def message_rows(path: str, content_hash: str = ""):
    """Exclude heterogeneous verification metadata before Arrow schema inference."""
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield {"messages": json.loads(line)["messages"]}


def train(cfg_path: str) -> None:
    import torch
    from datasets import Dataset  # type: ignore
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # type: ignore
    from transformers import (  # type: ignore
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    job = normalize_job(json.loads(Path(cfg_path).read_text(encoding="utf-8")))
    set_seed(job["seed"])
    tok = AutoTokenizer.from_pretrained(job["base_model"])
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    kwargs: dict = {"torch_dtype": torch.bfloat16 if bf16 else torch.float32}
    if job["method"] == "qlora":
        from transformers import BitsAndBytesConfig  # type: ignore

        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float32)
        kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(job["base_model"], **kwargs)
    if job["method"] == "qlora":
        model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(r=job["r"], lora_alpha=job["alpha"], lora_dropout=job["dropout"],
                                             target_modules=job["target_modules"], task_type="CAUSAL_LM"))
    model.config.use_cache = False
    model.enable_input_require_grads()

    data = Dataset.from_generator(message_rows, gen_kwargs={"path": job["dataset"],
                                  "content_hash": sha256(Path(job["dataset"]))})

    def encode(example):
        messages = example["messages"]
        if messages[-1]["role"] != "assistant":
            raise ValueError("SFT examples must end with an assistant answer")
        prompt = tok.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True, return_dict=False)
        ids = tok.apply_chat_template(messages, tokenize=True, return_dict=False)[:job["max_seq_length"]]
        if len(prompt) >= len(ids):
            raise ValueError("sequence length truncates the entire assistant answer")
        return {"input_ids": ids, "attention_mask": [1] * len(ids),
                "labels": [-100] * len(prompt) + ids[len(prompt):]}

    data = data.map(encode, remove_columns=data.column_names)
    valid = None
    if job.get("validation"):
        valid = Dataset.from_generator(message_rows, gen_kwargs={"path": job["validation"],
                                       "content_hash": sha256(Path(job["validation"]))})
        valid = valid.map(encode, remove_columns=valid.column_names)
    trainer = Trainer(
        model=model,
        train_dataset=data,
        eval_dataset=valid,
        data_collator=DataCollatorForSeq2Seq(tok, label_pad_token_id=-100),
        args=TrainingArguments(output_dir=job["output_dir"], num_train_epochs=job["epochs"],
                               per_device_train_batch_size=job["batch_size"],
                               gradient_accumulation_steps=job["gradient_accumulation"],
                               learning_rate=job["learning_rate"], logging_steps=10, save_strategy="epoch",
                               bf16=bf16, seed=job["seed"], gradient_checkpointing=True,
                               report_to=[]),
    )
    result = trainer.train()
    metrics = dict(result.metrics)
    if valid is not None:
        metrics.update(trainer.evaluate())
    Path(job["output_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(job["output_dir"]) / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
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

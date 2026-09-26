# train.py
# Fine-tunes a transformer encoder to classify SQL errors.
#
#   python -m training.train                                  # defaults from configs/training_config.yaml
#   python -m training.train --model microsoft/codebert-base --output-dir models/checkpoints/codebert
#   python -m training.train --resume                         # continue an interrupted run
#   python -m training.train --init-from models/checkpoints/codeberta-small/best \
#       --output-dir models/checkpoints/codeberta-small-ft --epochs 2 --lr 2e-5   # further fine-tuning
#
# Works on CPU (dynamic padding + length-grouped batches keep it tractable) and on CUDA (AMP).

import argparse
import csv
import json
import math
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
import yaml
from sklearn.metrics import accuracy_score, f1_score
from transformers import get_linear_schedule_with_warmup

from analysis.schema import DatabaseSchema
from models.classifier import SQLErrorClassifier, schema_text
from models.domain.labels import MODEL_CLASSES
from training.losses import get_loss_function
from training.optimizer import configure_optimizers
from utils.seed_manager import set_seed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "training_config.yaml"


# ---------------------------------------------------------------------- data
def load_split(data_dir: Path, name: str) -> List[Dict]:
    with open(data_dir / f"{name}.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_schemas(data_dir: Path) -> Dict[str, DatabaseSchema]:
    raw = json.loads((data_dir / "schemas.json").read_text())
    return {db: DatabaseSchema.from_dict(d, db) for db, d in raw.items()}


class EncodedSplit:
    def __init__(self, rows: List[Dict], schemas: Dict[str, DatabaseSchema], tokenizer, max_length: int):
        label_ids = {l: i for i, l in enumerate(MODEL_CLASSES)}
        pairs = [schema_text(r["sql"], schemas.get(r["db_id"])) for r in rows]
        enc = tokenizer([r["sql"] for r in rows], pairs, truncation="only_second", max_length=max_length)
        self.input_ids: List[List[int]] = enc["input_ids"]
        self.labels = [label_ids[r["label"]] for r in rows]

    def __len__(self):
        return len(self.labels)

    def batches(self, batch_size: int, shuffle: bool, rng: Optional[random.Random] = None) -> List[List[int]]:
        """Length-grouped batches: sort within shuffled mega-batches so padding stays small."""
        idx = list(range(len(self)))
        if not shuffle:
            idx.sort(key=lambda i: len(self.input_ids[i]))
            return [idx[i:i + batch_size] for i in range(0, len(idx), batch_size)]
        rng.shuffle(idx)
        mega = batch_size * 50
        batches = []
        for m in range(0, len(idx), mega):
            chunk = sorted(idx[m:m + mega], key=lambda i: len(self.input_ids[i]))
            batches.extend(chunk[i:i + batch_size] for i in range(0, len(chunk), batch_size))
        rng.shuffle(batches)
        return batches

    def collate(self, batch: List[int], pad_id: int, device) -> Dict[str, torch.Tensor]:
        width = max(len(self.input_ids[i]) for i in batch)
        ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        for row, i in enumerate(batch):
            seq = self.input_ids[i]
            ids[row, :len(seq)] = torch.tensor(seq)
            mask[row, :len(seq)] = 1
        labels = torch.tensor([self.labels[i] for i in batch])
        return {"input_ids": ids.to(device), "attention_mask": mask.to(device), "labels": labels.to(device)}


# ---------------------------------------------------------------------- evaluation
@torch.no_grad()
def evaluate(model, split: EncodedSplit, pad_id: int, device, batch_size: int = 64) -> Dict[str, float]:
    model.eval()
    preds, gold, losses = [], [], []
    for b in split.batches(batch_size, shuffle=False):
        batch = split.collate(b, pad_id, device)
        out = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"], labels=batch["labels"])
        losses.append(out.loss.item() * len(b))
        preds.extend(out.logits.argmax(-1).cpu().tolist())
        gold.extend(batch["labels"].cpu().tolist())
    model.train()
    return {"loss": sum(losses) / len(gold), "accuracy": accuracy_score(gold, preds),
            "macro_f1": f1_score(gold, preds, average="macro")}


# ---------------------------------------------------------------------- training
def parse_args():
    cfg = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    t = cfg.get("training", {})
    ap = argparse.ArgumentParser(description="Fine-tune the SQL error classifier.")
    ap.add_argument("--model", default=t.get("backbone", "huggingface/CodeBERTa-small-v1"))
    ap.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / t.get("data_dir", "data/processed"))
    ap.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / t.get("output_dir", "models/checkpoints/codeberta-small"))
    ap.add_argument("--epochs", type=float, default=t.get("epochs", 3))
    ap.add_argument("--batch-size", type=int, default=t.get("batch_size", 16))
    ap.add_argument("--grad-accum", type=int, default=t.get("gradient_accumulation_steps", 1))
    ap.add_argument("--lr", type=float, default=float(t.get("learning_rate", 5e-5)))
    ap.add_argument("--weight-decay", type=float, default=t.get("weight_decay", 0.01))
    ap.add_argument("--warmup-ratio", type=float, default=t.get("warmup_ratio", 0.06))
    ap.add_argument("--max-grad-norm", type=float, default=t.get("max_grad_norm", 1.0))
    ap.add_argument("--max-length", type=int, default=t.get("max_length", 256))
    ap.add_argument("--loss", default=t.get("loss", "cross_entropy"), choices=["cross_entropy", "focal"])
    ap.add_argument("--label-smoothing", type=float, default=t.get("label_smoothing", 0.0))
    ap.add_argument("--eval-steps", type=int, default=t.get("eval_steps", 150))
    ap.add_argument("--patience", type=int, default=t.get("early_stopping_patience", 4),
                    help="evaluations without macro-F1 improvement before stopping")
    ap.add_argument("--max-train-samples", type=int, default=t.get("max_train_samples"))
    ap.add_argument("--max-val-samples", type=int, default=t.get("max_val_samples"))
    ap.add_argument("--seed", type=int, default=t.get("seed", 42))
    ap.add_argument("--threads", type=int, default=t.get("cpu_threads", 0), help="CPU threads (0 = torch default)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--resume", action="store_true", help="resume from <output-dir>/last")
    ap.add_argument("--init-from", type=Path, default=None,
                    help="start from the weights of a fine-tuned checkpoint (new optimizer and schedule)")
    return ap.parse_args()


def main():
    args = parse_args()
    set_seed(args.seed)
    if args.threads:
        torch.set_num_threads(args.threads)
    device = torch.device(args.device)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    last_dir, best_dir = out / "last", out / "best"

    resume_state = None
    if args.resume and (last_dir / "trainer_state.pt").exists():
        clf = SQLErrorClassifier.from_pretrained(str(last_dir), device=args.device)
        resume_state = torch.load(last_dir / "trainer_state.pt", map_location="cpu", weights_only=False)
        print(f"Resuming from step {resume_state['step']}")
    elif args.init_from:
        clf = SQLErrorClassifier.from_pretrained(str(args.init_from), device=args.device)
        meta = json.loads((args.init_from / "sqldiagnose_labels.json").read_text())
        args.model = meta.get("backbone", args.model)
        print(f"Initialised from {args.init_from} ({args.model})")
    else:
        clf = SQLErrorClassifier.from_base(args.model, MODEL_CLASSES, args.max_length, args.device)
    model, tok = clf.model, clf.tokenizer
    model.train()

    schemas = load_schemas(args.data_dir)
    train_rows = load_split(args.data_dir, "train")
    if args.max_train_samples:
        random.Random(args.seed).shuffle(train_rows)
        train_rows = train_rows[:args.max_train_samples]
    train = EncodedSplit(train_rows, schemas, tok, args.max_length)
    val_rows = load_split(args.data_dir, "validation")
    if args.max_val_samples:
        random.Random(args.seed).shuffle(val_rows)
        val_rows = val_rows[:args.max_val_samples]
    val = EncodedSplit(val_rows, schemas, tok, args.max_length)
    lengths = [len(x) for x in train.input_ids]
    print(f"train={len(train)} validation={len(val)} | tokens mean={np.mean(lengths):.0f} "
          f"p95={np.percentile(lengths, 95):.0f} max={max(lengths)} | device={device} | model={args.model}")

    steps_per_epoch = max(1, math.ceil(len(train) / args.batch_size) // args.grad_accum)
    total_steps = int(steps_per_epoch * args.epochs)
    optimizer = configure_optimizers(model, args.lr, args.weight_decay)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * args.warmup_ratio), total_steps)
    loss_fn = get_loss_function(args.loss, label_smoothing=args.label_smoothing)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    step, best_f1, stale, epoch_start, last_eval = 0, -1.0, 0, 0, 0
    rng = random.Random(args.seed)
    if resume_state:
        optimizer.load_state_dict(resume_state["optimizer"])
        scheduler.load_state_dict(resume_state["scheduler"])
        step, best_f1, stale = resume_state["step"], resume_state["best_f1"], resume_state["stale"]
        epoch_start = resume_state["epoch"]
        rng.setstate(resume_state["rng"])

    log_path = out / "train_log.csv"
    log_new = not log_path.exists() or not resume_state
    log_f = open(log_path, "w" if log_new else "a", newline="")
    log = csv.writer(log_f)
    if log_new:
        log.writerow(["step", "epoch", "train_loss", "val_loss", "val_accuracy", "val_macro_f1", "lr", "elapsed_s"])

    def checkpoint(epoch: int, batches_done: int):
        clf.save_pretrained(str(last_dir), {"backbone": args.model})
        torch.save({"optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "step": step,
                    "best_f1": best_f1, "stale": stale, "epoch": epoch, "batches_done": batches_done,
                    "rng": rng.getstate()}, last_dir / "trainer_state.pt")

    t0 = time.time()
    running, running_n = 0.0, 0
    stop = False
    n_epochs = math.ceil(args.epochs)
    for epoch in range(epoch_start, n_epochs):
        batches = train.batches(args.batch_size, shuffle=True, rng=rng)
        skip = resume_state["batches_done"] if (resume_state and epoch == epoch_start) else 0
        for bi, b in enumerate(batches):
            if bi < skip:
                continue
            batch = train.collate(b, tok.pad_token_id, device)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).logits
                loss = loss_fn(logits.float(), batch["labels"]) / args.grad_accum
            scaler.scale(loss).backward()
            running += loss.item() * args.grad_accum
            running_n += 1
            if (bi + 1) % args.grad_accum:
                continue
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            scheduler.step()
            step += 1

            if step % 10 == 0:
                el = time.time() - t0
                done = step - (resume_state["step"] if resume_state else 0)
                eta = el / max(done, 1) * (total_steps - step)
                print(f"step {step}/{total_steps} epoch {epoch + 1} loss {running / running_n:.4f} "
                      f"lr {scheduler.get_last_lr()[0]:.2e} elapsed {el / 60:.1f}m eta {eta / 60:.1f}m", flush=True)

            if step % args.eval_steps == 0 or step == total_steps:
                last_eval = step
                metrics = evaluate(model, val, tok.pad_token_id, device)
                train_loss = running / max(running_n, 1)
                running, running_n = 0.0, 0
                log.writerow([step, epoch + 1, f"{train_loss:.4f}", f"{metrics['loss']:.4f}",
                              f"{metrics['accuracy']:.4f}", f"{metrics['macro_f1']:.4f}",
                              f"{scheduler.get_last_lr()[0]:.2e}", f"{time.time() - t0:.0f}"])
                log_f.flush()
                print(f"  [eval] step {step}: val_loss {metrics['loss']:.4f} acc {metrics['accuracy']:.4f} "
                      f"macro_f1 {metrics['macro_f1']:.4f}", flush=True)
                if metrics["macro_f1"] > best_f1 + 1e-4:
                    best_f1, stale = metrics["macro_f1"], 0
                    clf.save_pretrained(str(best_dir), {"backbone": args.model, "step": step,
                                                        "validation": metrics})
                    print(f"  [eval] new best -> {best_dir}", flush=True)
                else:
                    stale += 1
                checkpoint(epoch, bi + 1)
                if stale >= args.patience:
                    print(f"Early stopping: no improvement in {args.patience} evaluations.")
                    stop = True
            if step >= total_steps or stop:
                break
        if step >= total_steps or stop:
            break

    if step != last_eval and not stop:
        # the final steps were never evaluated (e.g. total_steps not reached exactly): do it now
        metrics = evaluate(model, val, tok.pad_token_id, device)
        log.writerow([step, epoch + 1, f"{running / max(running_n, 1):.4f}", f"{metrics['loss']:.4f}",
                      f"{metrics['accuracy']:.4f}", f"{metrics['macro_f1']:.4f}",
                      f"{scheduler.get_last_lr()[0]:.2e}", f"{time.time() - t0:.0f}"])
        print(f"  [eval] final step {step}: macro_f1 {metrics['macro_f1']:.4f}", flush=True)
        if metrics["macro_f1"] > best_f1 + 1e-4:
            best_f1 = metrics["macro_f1"]
            clf.save_pretrained(str(best_dir), {"backbone": args.model, "step": step, "validation": metrics})
        checkpoint(epoch, len(batches))
    log_f.close()
    summary = {"backbone": args.model, "best_validation_macro_f1": best_f1, "steps": step,
               "train_samples": len(train), "epochs": args.epochs, "batch_size": args.batch_size,
               "learning_rate": args.lr, "max_length": args.max_length, "device": str(device),
               "training_minutes": round((time.time() - t0) / 60, 1)}
    (out / "training_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

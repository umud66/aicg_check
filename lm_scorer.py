from __future__ import annotations

import math
import os


class LocalPerplexityScorer:
    """Optional local causal-LM perplexity scorer.

    This module is intentionally optional so the core service stays lightweight.
    Enable with AICG_LM_ENABLE=1 after installing requirements-lm.txt.
    """

    def __init__(self, model_name: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        self.model.eval()
        self.device = "cpu"
        if torch.cuda.is_available():
            self.device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self.device = "mps"
        self.model.to(self.device)
        self.max_length = min(int(getattr(self.model.config, "n_positions", 512) or 512), 1024)
        self.stride = min(256, self.max_length // 2)
        self.risk_low = float(os.getenv("AICG_LM_PPL_LOW", "18"))
        self.risk_high = float(os.getenv("AICG_LM_PPL_HIGH", "90"))

    def perplexity(self, text: str) -> float:
        torch = self.torch
        enc = self.tokenizer(text, return_tensors="pt", add_special_tokens=True)
        input_ids = enc.input_ids.to(self.device)
        seq_len = input_ids.size(1)
        if seq_len < 3:
            return 999.0

        nlls = []
        prev_end = 0
        for begin in range(0, seq_len, self.stride):
            end = min(begin + self.max_length, seq_len)
            trg_len = end - prev_end
            ids = input_ids[:, begin:end]
            target = ids.clone()
            target[:, :-trg_len] = -100
            with torch.no_grad():
                out = self.model(ids, labels=target)
                nlls.append(out.loss * trg_len)
            prev_end = end
            if end == seq_len:
                break
        ppl = torch.exp(torch.stack(nlls).sum() / max(1, prev_end)).item()
        return float(ppl)

    def risk_score(self, text: str) -> float:
        """Map lower perplexity to higher predictability risk, 0-100.

        The mapping is deliberately configurable because absolute perplexity values
        are model-specific and must be calibrated on a labeled corpus.
        """
        ppl = max(1.0001, self.perplexity(text))
        lo = max(1.0001, self.risk_low)
        hi = max(lo + 0.01, self.risk_high)
        x = (math.log(ppl) - math.log(lo)) / (math.log(hi) - math.log(lo))
        return round(max(0.0, min(100.0, (1.0 - x) * 100.0)), 1)

"""
download_raw.py

Downloads the MBPP (sanitized) dataset from Hugging Face and saves a raw,
untouched copy to disk for later cleaning/preprocessing (see clean_generation.py)

Source: https://huggingface.co/datasets/claudios/google-research-datasets__mbpp
License: CC-BY-4.0

Important note: Some private/gated datasets require authentication via
`huggingface-cli login` before they can be downloaded. This one is public,
so login isn't required, but the command is here in case that changes.

We use the "sanitized" subset (427 rows) rather than "full" (974 rows)
because it has been hand-verified by the original authors for clarity
and correctness — fewer ambiguous prompts or broken test cases.
"""

from datasets import load_dataset

#Step 1: Load the dataset from Hugging Face
# "sanitized" = the cleaned/verified subset of MBPP (see note above)
ds = load_dataset("claudios/google-research-datasets__mbpp", "sanitized")

#Step 2: Inspect the dataset structure (run once, then comment out)
# Useful the first time to confirm splits and column names before writing
# a cleaning script that depends on them.
print(ds)                # shows available splits (train/test/validation/etc.)
print(ds["train"][0])    # shows one example row and its fields

# Step 3: Save a raw, untouched copy to disk 
# This becomes our permanent "raw" version — never edit this directly.
# All cleaning/preprocessing happens in a separate script that reads from here.
ds.save_to_disk("data/raw/mbpp")


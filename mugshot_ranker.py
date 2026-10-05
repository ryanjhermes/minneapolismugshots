"""Rank mugshots by how visually distinctive they are, using CLIP zero-shot scoring.

Free and local: the model (openai/clip-vit-base-patch32, ~600 MB) downloads from
Hugging Face and runs on the GitHub Actions CPU in a few seconds for 100 images.
"""
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

MODEL_NAME = "openai/clip-vit-base-patch32"

# Edit these to change what counts as "stands out"
DISTINCTIVE_PROMPTS = [
    "a mugshot of a person with face tattoos",
    "a mugshot of a person with neck or head tattoos",
    "a mugshot of a person with brightly dyed hair",
    "a mugshot of a person with a wild, unusual hairstyle",
    "a mugshot of a person making a funny or exaggerated facial expression",
    "a mugshot of a person with many facial piercings",
    "a mugshot of a person with an unusual beard or facial hair",
    "a mugshot of a person wearing an unusual outfit or costume",
    "a mugshot of a strikingly attractive, model-like person",
    "a mugshot of a very good-looking person",
]
PLAIN_PROMPTS = [
    "a plain, ordinary mugshot of a person with a neutral expression",
    "a normal mugshot of a person with ordinary hair and no tattoos",
]


def score_mugshots(paths):
    """Return {path: score in 0..1}, higher = more distinctive. Unreadable images score 0."""
    model = CLIPModel.from_pretrained(MODEL_NAME).eval()
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    prompts = DISTINCTIVE_PROMPTS + PLAIN_PROMPTS

    scores = {}
    for path in paths:
        try:
            image = Image.open(path).convert("RGB")
            inputs = processor(text=prompts, images=image, return_tensors="pt", padding=True)
            with torch.no_grad():
                probs = model(**inputs).logits_per_image.softmax(dim=1)[0]
            scores[path] = float(probs[:len(DISTINCTIVE_PROMPTS)].sum())
        except Exception as e:
            print(f"⚠️  Could not score {path}: {e}")
            scores[path] = 0.0
    return scores

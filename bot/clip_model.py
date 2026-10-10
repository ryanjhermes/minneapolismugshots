"""CLIP zero-shot image scoring: how distinctive a mugshot is, and whether an image is a mugshot at all.

Free and local: the model (openai/clip-vit-base-patch32, ~600 MB) downloads from Hugging Face
and runs on the GitHub Actions CPU in a few seconds for 100 images.
Needs torch, transformers and pillow, which only the scrape and bmtn workflows install.
"""
from functools import lru_cache

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_NAME = "openai/clip-vit-base-patch32"

# Used by ranking.py. Edit these to change what counts as "stands out"
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
# Keep this list about as long as DISTINCTIVE_PROMPTS so ordinary photos don't score high by default
PLAIN_PROMPTS = [
    "a plain, ordinary mugshot of a person with a neutral expression",
    "a normal mugshot of a person with ordinary hair and no tattoos",
    "a boring, unremarkable police booking photo",
    "a mugshot of an average-looking person",
    "a mugshot of a person with short, plain hair",
    "a mugshot of a person with a tired, blank expression",
    "a mugshot of a person wearing a plain t-shirt",
    "a typical booking photo of a person against a gray wall",
    "a mugshot of a person with no visible tattoos or piercings",
    "a forgettable, everyday mugshot",
]

# Used by bmtn.py to tell a booking photo from a victim/family photo, scene shot, or stock image
MUGSHOT_PROMPTS = [
    "a police booking mugshot",
    "a jail booking photo of a person against a plain wall",
    "a sheriff's office mugshot of a person in an orange jumpsuit",
]
NOT_MUGSHOT_PROMPTS = [
    "a candid snapshot of a person",
    "a smiling family photo or selfie",
    "a photo of a crime scene, police tape, or police cars",
    "a photo of a building, street, or vehicle",
    "a screenshot of a document or video",
    "a school or yearbook portrait",
]


@lru_cache(maxsize=1)
def _model():
    return CLIPModel.from_pretrained(MODEL_NAME).eval(), CLIPProcessor.from_pretrained(MODEL_NAME)


def _share(path, positive, negative):
    """Probability mass CLIP puts on the positive prompts, out of positive + negative."""
    model, processor = _model()
    image = Image.open(path).convert("RGB")
    inputs = processor(text=positive + negative, images=image, return_tensors="pt", padding=True)
    with torch.no_grad():
        probs = model(**inputs).logits_per_image.softmax(dim=1)[0]
    return float(probs[:len(positive)].sum())


def score_mugshots(paths):
    """Return {path: score in 0..1}, higher = more distinctive. Unreadable images score 0."""
    _model()  # A model download failure raises here, before any image is scored
    scores = {}
    for path in paths:
        try:
            scores[path] = _share(path, DISTINCTIVE_PROMPTS, PLAIN_PROMPTS)
        except Exception as e:
            print(f"⚠️  Could not score {path}: {e}")
            scores[path] = 0.0
    return scores


def mugshot_probability(path):
    """0..1, how much the image looks like a booking photo rather than anything else."""
    return _share(path, MUGSHOT_PROMPTS, NOT_MUGSHOT_PROMPTS)

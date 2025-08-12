import os
import base64
import json
from PIL import Image
from dotenv import load_dotenv
from transformers import pipeline, AutoProcessor, AutoModelForVisualQuestionAnswering

# Load environment variables
load_dotenv()

class BLIPImageFilter:
    """Filter mugshots using BLIP VQA model before posting"""
    
    def __init__(self):
        # Initialize BLIP VQA pipeline
        self.pipe = pipeline("visual-question-answering", model="Salesforce/blip-vqa-base")
        self.processor = AutoProcessor.from_pretrained("Salesforce/blip-vqa-base")
        self.model = AutoModelForVisualQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
        
        # Canonical forced-choice answers we will map to
        self.valid_answers = {
            "strong yes": "strong_yes",
            "strong": "strong_yes",
            "yes": "yes",
            "y": "yes",
            "no": "no",
            "n": "no"
        }

        # Core questions (asked sequentially)
        self.question_disheveled = (
            "Does the person look like they have a history of violence or extreme drug usage? "
            "Think of a disheveled appearance, missing teeth, etc. Answer only one of: strong yes, yes, or no."
        )
        self.question_attractive = (
            "Is the person conventionally attractive? This is important, think of it like a dating profile. "
            "Answer only one of: strong yes, yes, or no."
        )
    
    def load_image(self, image_path):
        """Load and prepare image for BLIP model"""
        try:
            if not os.path.exists(image_path):
                print(f"❌ Image file not found: {image_path}")
                return None
            
            # Load image with PIL
            image = Image.open(image_path).convert('RGB')
            return image
        except Exception as e:
            print(f"❌ Error loading image {image_path}: {e}")
            return None
    
    def _canonicalize_answer(self, raw_answer: str) -> str:
        """Map a raw BLIP answer to a canonical label: strong_yes | yes | no."""
        if not raw_answer:
            return "no"
        answer = raw_answer.strip().lower()
        # Prefer exact matches
        if answer in self.valid_answers:
            return self.valid_answers[answer]
        # Handle answers that include extra words (e.g., "strong yes, definitely")
        for key, label in self.valid_answers.items():
            if key in answer:
                return label
        return "no"

    def _ask_vqa(self, image, question: str):
        """Ask BLIP a question, return (canonical_label, confidence, raw_answer)."""
        result = self.pipe(image, question)
        raw_answer = str(result[0].get('answer', '')).lower()
        confidence = float(result[0].get('score', 0.5))
        label = self._canonicalize_answer(raw_answer)
        return label, confidence, raw_answer

    def analyze_mugshot(self, image_path):
        """Analyze a mugshot using BLIP VQA model with a simple two-step decision tree."""
        try:
            print(f"🤖 Analyzing mugshot: {image_path}")
            
            # Load image
            image = self.load_image(image_path)
            if image is None:
                return {
                    "approved": False,
                    "reason": "Image file not found or invalid",
                    "quality_score": 0,
                    "issues": ["File not found or invalid"]
                }
            
            # Step 1: Disheveled / violence / extreme drug usage
            dis_label, dis_conf, dis_raw = self._ask_vqa(image, self.question_disheveled)
            print(f"   Q: disheveled/violence/extreme drugs\n   A: {dis_raw} (canonical: {dis_label}, confidence: {dis_conf:.3f})")

            # Since BLIP always returns 0.5 confidence, ignore confidence and focus on labels
            # Step 1: Check disheveled/violent appearance
            if dis_label in ["strong_yes", "yes"]:
                result = {
                    "approved": True,
                    "reason": "Approved - notably disheveled/violent/extreme drug use appearance",
                    "quality_score": 10 if dis_label == "strong_yes" else 8,
                    "issues": [],
                    "responses": {
                        "disheveled": {"answer": dis_raw, "label": dis_label, "score": dis_conf}
                    }
                }
                print(f"✅ Analysis complete - Approved: True, Score: {result['quality_score']}/10")
                return result

            # Step 2: Conventional attractiveness
            att_label, att_conf, att_raw = self._ask_vqa(image, self.question_attractive)
            print(f"   Q: conventionally attractive\n   A: {att_raw} (canonical: {att_label}, confidence: {att_conf:.3f})")

            if att_label in ["strong_yes", "yes"]:
                result = {
                    "approved": True,
                    "reason": "Approved - conventionally attractive",
                    "quality_score": 10 if att_label == "strong_yes" else 8,
                    "issues": [],
                    "responses": {
                        "disheveled": {"answer": dis_raw, "label": dis_label, "score": dis_conf},
                        "attractive": {"answer": att_raw, "label": att_label, "score": att_conf}
                    }
                }
                print(f"✅ Analysis complete - Approved: True, Score: {result['quality_score']}/10")
                return result

            # Final rejection - neither condition met
            result = {
                "approved": False,
                "reason": "Rejected - does not meet minimum thresholds for either criteria",
                "quality_score": 0,
                "issues": ["Low social media interest"],
                "responses": {
                    "disheveled": {"answer": dis_raw, "label": dis_label, "score": dis_conf},
                    "attractive": {"answer": att_raw, "label": att_label, "score": att_conf}
                }
            }
            print(f"✅ Analysis complete - Approved: False, Score: 0/10")
            return result
                
        except Exception as e:
            print(f"❌ Error analyzing mugshot: {e}")
            return {
                "approved": True,  # Approve in fallback mode
                "reason": "Approved (analysis error - fallback mode)",
                "quality_score": 5,
                "issues": ["Analysis error"]
            }
    
    def filter_inmates_by_ai(self, inmates_list):
        """Filter a list of inmates using BLIP analysis of their mugshots"""
        print(f"\n🤖 Starting BLIP filtering of {len(inmates_list)} inmates...")
        
        approved_inmates = []
        rejected_inmates = []
        
        for i, inmate in enumerate(inmates_list, 1):
            inmate_data = inmate['data']
            mugshot_path = inmate_data.get('Mugshot_File', '')
            name = inmate_data.get('Full Name', 'Unknown')
            
            print(f"\n{'='*50}")
            print(f"🤖 Analyzing inmate {i}/{len(inmates_list)}: {name}")
            print(f"{'='*50}")
            
            # Analyze the mugshot
            analysis = self.analyze_mugshot(mugshot_path)
            
            # Add analysis results to inmate data
            inmate_data['ai_analysis'] = analysis
            
            if analysis.get('approved', False):
                approved_inmates.append(inmate)
                print(f"✅ APPROVED: {name} (Score: {analysis.get('quality_score', 0)})")
                print(f"   Reason: {analysis.get('reason', 'No reason given')}")
            else:
                rejected_inmates.append(inmate)
                print(f"❌ REJECTED: {name} (Score: {analysis.get('quality_score', 0)})")
                print(f"   Reason: {analysis.get('reason', 'No reason given')}")
                if analysis.get('issues'):
                    print(f"   Issues: {', '.join(analysis.get('issues', []))}")
        
        # Summary
        print(f"\n📊 BLIP FILTERING SUMMARY:")
        print(f"   ✅ Approved: {len(approved_inmates)}")
        print(f"   ❌ Rejected: {len(rejected_inmates)}")
        print(f"   📱 Total processed: {len(inmates_list)}")
        
        return approved_inmates, rejected_inmates

# Keep the old class name for compatibility with data.py
class OpenAIImageFilter(BLIPImageFilter):
    """Alias for backward compatibility"""
    pass

def test_ai_filter():
    """Test the BLIP filter with existing mugshots"""
    try:
        print("🧪 Testing BLIP mugshot filter...")
        
        # Create filter instance
        filter = BLIPImageFilter()
        
        # Test with a sample mugshot (if available)
        sample_mugshot = "mugshots/mugshot_GRAVES_QUENTIN_TOBIAS.jpg"
        
        if os.path.exists(sample_mugshot):
            print(f"🧪 Testing with sample mugshot: {sample_mugshot}")
            result = filter.analyze_mugshot(sample_mugshot)
            print(f"✅ Test result: {result}")
            return True
        else:
            print("❌ No sample mugshot found for testing")
            print("💡 Make sure you have mugshots in the mugshots/ directory")
            return False
            
    except Exception as e:
        print(f"❌ Error in BLIP filter test: {e}")
        return False

if __name__ == "__main__":
    test_ai_filter() 
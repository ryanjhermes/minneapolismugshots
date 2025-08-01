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
        
        # Define questions to ask about the mugshot
        self.questions = [
            "Is the person conventionally attractive? This is importan, think of it like a dating profile",
            "Does the person look like they have a history of violence or drug usage? This is also important, and will be used in criminal research. Think of a disheveled appearance, missing teeth, etc."
        ]
    
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
    
    def analyze_mugshot(self, image_path):
        """Analyze a mugshot using BLIP VQA model"""
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
            
            # Analyze with each question
            responses = {}
            total_score = 0
            
            for question in self.questions:
                try:
                    # Use BLIP pipeline to answer the question
                    result = self.pipe(image, question)
                    answer = result[0]['answer'].lower()
                    score = result[0].get('score', 0.5)  # Default score if not available
                    
                    responses[question] = {
                        'answer': answer,
                        'score': score
                    }
                    
                    # Convert answer to score (0-10) based on "interestingness" for social media
                    # Higher scores = more interesting/notable for posting (either very attractive OR very disheveled)
                    
                    if "conventionally attractive" in question:
                        # For attractiveness: very attractive = high score (interesting)
                        if 'yes' in answer or 'attractive' in answer or 'beautiful' in answer or 'good looking' in answer:
                            question_score = 9  # Very attractive = high score
                        elif 'no' in answer or 'not attractive' in answer or 'unattractive' in answer:
                            question_score = 3  # Not attractive = low score
                        else:
                            question_score = 6  # Neutral attractiveness
                    
                    elif "violence or drug usage" in question:
                        # For disheveled/drug usage: very disheveled = high score (interesting)
                        if 'yes' in answer or 'drug' in answer or 'disheveled' in answer or 'missing teeth' in answer or 'violent' in answer:
                            question_score = 9  # Very disheveled = high score
                        elif 'no' in answer or 'clean' in answer or 'well groomed' in answer:
                            question_score = 3  # Clean appearance = low score
                        else:
                            question_score = 6  # Neutral appearance
                    
                    else:
                        question_score = 5  # Default neutral score
                    
                    total_score += question_score
                    print(f"   Q: {question}")
                    print(f"   A: {answer} (confidence: {score:.3f}, score: {question_score})")
                    
                except Exception as e:
                    print(f"   ❌ Error analyzing question '{question}': {e}")
                    responses[question] = {
                        'answer': 'error',
                        'score': 0
                    }
                    total_score += 5  # Neutral score for errors
            
            # Calculate average score
            avg_score = total_score / len(self.questions)
            
            # Determine approval based on "interestingness" score
            # Higher scores = more interesting for social media (either very attractive OR very disheveled)
            approved = avg_score >= 6.0  # Threshold for approval
            
            # Generate reason based on responses
            attractive_score = 0
            disheveled_score = 0
            
            for question, response in responses.items():
                if "conventionally attractive" in question:
                    if 'yes' in response['answer'].lower() or 'attractive' in response['answer'].lower():
                        attractive_score = 9
                    elif 'no' in response['answer'].lower():
                        attractive_score = 3
                    else:
                        attractive_score = 6
                elif "violence or drug usage" in question:
                    if 'yes' in response['answer'].lower() or 'drug' in response['answer'].lower():
                        disheveled_score = 9
                    elif 'no' in response['answer'].lower():
                        disheveled_score = 3
                    else:
                        disheveled_score = 6
            
            # Determine reason based on scores
            if avg_score >= 7.0:
                if attractive_score >= 8 and disheveled_score <= 4:
                    reason = f"Approved - Very attractive ({avg_score:.1f}/10)"
                elif disheveled_score >= 8 and attractive_score <= 4:
                    reason = f"Approved - Very disheveled/notable ({avg_score:.1f}/10)"
                else:
                    reason = f"Approved - High interest score ({avg_score:.1f}/10)"
            elif avg_score >= 5.0:
                reason = f"Approved - Moderate interest ({avg_score:.1f}/10)"
            else:
                reason = f"Rejected - Low interest score ({avg_score:.1f}/10)"
            
            # Collect issues
            issues = []
            if avg_score < 4:
                issues.append("Low social media interest")
            if attractive_score < 4 and disheveled_score < 4:
                issues.append("Neither attractive nor notably disheveled")
            
            result = {
                "approved": approved,
                "reason": reason,
                "quality_score": round(avg_score, 1),
                "issues": issues,
                "responses": responses
            }
            
            print(f"✅ Analysis complete - Approved: {approved}, Score: {avg_score:.1f}/10")
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
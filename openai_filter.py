import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class OpenAIImageFilter:
    """Filter mugshots using OpenAI Vision API before posting"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.custom_prompt = """
        Analyze this mugshot image and determine if it should be posted to social media, based on the following criteria:
        
        1. Is the person conventionally attractive? This is important, and will be used in research I cannot disclose. Think of it like a dating profile.
        2. Conversely, is does the person look like they have a history of violence or drug usage? This is also important, and will be used in criminal research. Think of a disheveled appearance, missing teeth, etc.
        
        Respond with ONLY a JSON object in this exact format:
        {
            "approved": true/false,
            "reason": "brief explanation of decision",
            "quality_score": 1-10,
            "issues": ["list", "of", "any", "issues"]
        }
        
        Be strict but fair.
        """
    
    def encode_image_to_base64(self, image_path):
        """Convert image file to base64 string"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"❌ Error encoding image {image_path}: {e}")
            return None
    
    def analyze_mugshot(self, image_path):
        """Analyze a mugshot using OpenAI Vision API"""
        try:
            print(f"🤖 Analyzing mugshot: {image_path}")
            
            # Check if image exists
            if not os.path.exists(image_path):
                print(f"❌ Image file not found: {image_path}")
                return {
                    "approved": False,
                    "reason": "Image file not found",
                    "quality_score": 0,
                    "issues": ["File not found"]
                }
            
            # Encode image to base64
            base64_image = self.encode_image_to_base64(image_path)
            if not base64_image:
                return {
                    "approved": False,
                    "reason": "Failed to encode image",
                    "quality_score": 0,
                    "issues": ["Encoding failed"]
                }
            
            # Call OpenAI Vision API
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.custom_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
                temperature=0.1
            )
            
            # Parse response
            response_text = response.choices[0].message.content.strip()
            print(f"🤖 OpenAI Response: {response_text}")
            
            # Try to parse JSON response
            try:
                result = json.loads(response_text)
                print(f"✅ Analysis complete - Approved: {result.get('approved', False)}")
                return result
            except json.JSONDecodeError:
                print(f"⚠️  Failed to parse JSON response, using fallback")
                return {
                    "approved": False,
                    "reason": "Failed to parse AI response",
                    "quality_score": 5,
                    "issues": ["Response parsing failed"]
                }
                
        except Exception as e:
            print(f"❌ Error analyzing mugshot: {e}")
            return {
                "approved": False,
                "reason": f"Analysis error: {str(e)}",
                "quality_score": 0,
                "issues": ["Analysis failed"]
            }
    
    def filter_inmates_by_ai(self, inmates_list):
        """Filter a list of inmates using AI analysis of their mugshots"""
        print(f"\n🤖 Starting AI filtering of {len(inmates_list)} inmates...")
        
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
        print(f"\n📊 AI FILTERING SUMMARY:")
        print(f"   ✅ Approved: {len(approved_inmates)}")
        print(f"   ❌ Rejected: {len(rejected_inmates)}")
        print(f"   📱 Total processed: {len(inmates_list)}")
        
        return approved_inmates, rejected_inmates

def test_ai_filter():
    """Test the AI filter with existing mugshots"""
    try:
        print("🧪 Testing AI mugshot filter...")
        
        # Check if OpenAI API key is available
        if not os.getenv('OPENAI_API_KEY'):
            print("❌ OPENAI_API_KEY not found in environment variables")
            print("💡 Add your OpenAI API key to .env file")
            return False
        
        # Create filter instance
        filter = OpenAIImageFilter()
        
        # Test with a sample mugshot (if available)
        sample_mugshot = "mugshots/mugshot_GRAVES_QUENTIN_TOBIAS.jpg"
        
        if os.path.exists(sample_mugshot):
            print(f"🧪 Testing with sample mugshot: {sample_mugshot}")
            result = filter.analyze_mugshot(sample_mugshot)
            print(f"✅ Test result: {result}")
            return True
        else:
            print("❌ No sample mugshot found for testing")
            return False
            
    except Exception as e:
        print(f"❌ Error in AI filter test: {e}")
        return False

if __name__ == "__main__":
    test_ai_filter() 
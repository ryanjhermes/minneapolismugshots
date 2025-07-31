#!/usr/bin/env python3
"""
Test script for OpenAI mugshot filtering
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_ai_filter_setup():
    """Test if AI filter is properly set up"""
    print("🧪 Testing AI Filter Setup")
    print("=" * 50)
    
    # Check OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        print("✅ OPENAI_API_KEY found")
        print(f"   Key starts with: {api_key[:10]}...")
    else:
        print("❌ OPENAI_API_KEY not found")
        print("💡 Add your OpenAI API key to .env file:")
        print("   OPENAI_API_KEY=your_api_key_here")
        return False
    
    # Check if openai package is installed
    try:
        import openai
        print("✅ OpenAI package installed")
    except ImportError:
        print("❌ OpenAI package not installed")
        print("💡 Install with: pip install openai")
        return False
    
    # Check if mugshots directory exists
    if os.path.exists("mugshots"):
        print("✅ Mugshots directory found")
        mugshot_files = [f for f in os.listdir("mugshots") if f.endswith(('.jpg', '.jpeg', '.png'))]
        print(f"   Found {len(mugshot_files)} mugshot files")
        if mugshot_files:
            print(f"   Sample files: {mugshot_files[:3]}")
    else:
        print("❌ Mugshots directory not found")
        return False
    
    # Test AI filter import
    try:
        from openai_filter import OpenAIImageFilter
        print("✅ AI filter module imported successfully")
        
        # Test filter initialization
        filter = OpenAIImageFilter()
        print("✅ AI filter initialized successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing AI filter: {e}")
        return False

def test_single_mugshot():
    """Test AI analysis on a single mugshot"""
    print("\n🧪 Testing Single Mugshot Analysis")
    print("=" * 50)
    
    try:
        from openai_filter import OpenAIImageFilter
        
        # Find a sample mugshot
        mugshot_dir = "mugshots"
        if not os.path.exists(mugshot_dir):
            print("❌ Mugshots directory not found")
            return False
        
        mugshot_files = [f for f in os.listdir(mugshot_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if not mugshot_files:
            print("❌ No mugshot files found")
            return False
        
        # Use the first mugshot file
        sample_mugshot = os.path.join(mugshot_dir, mugshot_files[0])
        print(f"📸 Testing with: {sample_mugshot}")
        
        # Create filter and analyze
        filter = OpenAIImageFilter()
        result = filter.analyze_mugshot(sample_mugshot)
        
        print(f"\n📊 Analysis Result:")
        print(f"   Approved: {result.get('approved', False)}")
        print(f"   Quality Score: {result.get('quality_score', 0)}/10")
        print(f"   Reason: {result.get('reason', 'No reason given')}")
        
        if result.get('issues'):
            print(f"   Issues: {', '.join(result.get('issues', []))}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing single mugshot: {e}")
        return False

def main():
    """Main test function"""
    print("🤖 OpenAI Mugshot Filter Test")
    print("=" * 50)
    
    # Test setup
    if not test_ai_filter_setup():
        print("\n❌ Setup failed - please fix issues above")
        return False
    
    # Test single mugshot
    if not test_single_mugshot():
        print("\n❌ Single mugshot test failed")
        return False
    
    print("\n✅ All tests passed!")
    print("💡 You can now use AI filtering with:")
    print("   python data.py post-next")
    print("   python data.py test-ai-filter")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 
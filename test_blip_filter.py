#!/usr/bin/env python3
"""
Test script for BLIP image filtering
"""

import os
import sys

def test_blip_import():
    """Test if BLIP filter can be imported"""
    try:
        from openai_filter import BLIPImageFilter
        print("✅ BLIPImageFilter imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import BLIPImageFilter: {e}")
        return False

def test_blip_initialization():
    """Test if BLIP filter can be initialized"""
    try:
        from openai_filter import BLIPImageFilter
        filter = BLIPImageFilter()
        print("✅ BLIPImageFilter initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize BLIPImageFilter: {e}")
        return False

def test_image_analysis():
    """Test image analysis with a sample mugshot"""
    try:
        from openai_filter import BLIPImageFilter
        
        # Check if we have any mugshots to test with
        mugshots_dir = "mugshots"
        if not os.path.exists(mugshots_dir):
            print("❌ No mugshots directory found")
            return False
        
        # Find first available mugshot
        mugshot_files = [f for f in os.listdir(mugshots_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if not mugshot_files:
            print("❌ No mugshot files found in mugshots directory")
            return False
        
        sample_mugshot = os.path.join(mugshots_dir, mugshot_files[0])
        print(f"🧪 Testing with mugshot: {sample_mugshot}")
        
        # Initialize filter and test analysis
        filter = BLIPImageFilter()
        result = filter.analyze_mugshot(sample_mugshot)
        
        print(f"✅ Analysis completed successfully")
        print(f"   Approved: {result.get('approved', False)}")
        print(f"   Score: {result.get('quality_score', 0)}/10")
        print(f"   Reason: {result.get('reason', 'No reason')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing image analysis: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing BLIP Filter Integration")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_blip_import),
        ("Initialization Test", test_blip_initialization),
        ("Image Analysis Test", test_image_analysis)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! BLIP filter is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 
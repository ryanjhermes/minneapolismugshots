#!/usr/bin/env python3
"""
Test BLIP availability and diagnose issues
"""

import sys
import os

def test_dependencies():
    """Test if required dependencies are installed"""
    print("🔍 Testing dependencies...")
    
    dependencies = [
        ('transformers', 'transformers'),
        ('torch', 'torch'),
        ('PIL', 'pillow'),
        ('numpy', 'numpy')
    ]
    
    missing = []
    for import_name, package_name in dependencies:
        try:
            __import__(import_name)
            print(f"✅ {package_name} - OK")
        except ImportError:
            print(f"❌ {package_name} - MISSING")
            missing.append(package_name)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print("💡 Install with: pip install " + " ".join(missing))
        return False
    else:
        print("✅ All dependencies installed")
        return True

def test_blip_import():
    """Test BLIP import"""
    print("\n🔍 Testing BLIP import...")
    
    try:
        from openai_filter import BLIPImageFilter
        print("✅ BLIPImageFilter imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_blip_initialization():
    """Test BLIP model initialization"""
    print("\n🔍 Testing BLIP initialization...")
    
    try:
        from openai_filter import BLIPImageFilter
        print("🔄 Initializing BLIP model...")
        filter = BLIPImageFilter()
        print("✅ BLIP model initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return False

def test_blip_analysis():
    """Test BLIP analysis with a sample image"""
    print("\n🔍 Testing BLIP analysis...")
    
    try:
        from openai_filter import BLIPImageFilter
        
        # Check if we have any mugshots
        mugshots_dir = "mugshots"
        if not os.path.exists(mugshots_dir):
            print("❌ No mugshots directory found")
            return False
        
        mugshot_files = [f for f in os.listdir(mugshots_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
        if not mugshot_files:
            print("❌ No mugshot files found")
            return False
        
        sample_mugshot = os.path.join(mugshots_dir, mugshot_files[0])
        print(f"🧪 Testing with: {sample_mugshot}")
        
        filter = BLIPImageFilter()
        result = filter.analyze_mugshot(sample_mugshot)
        
        print(f"✅ Analysis completed: {result.get('approved', False)}")
        print(f"📊 Score: {result.get('quality_score', 0)}/10")
        return True
        
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 BLIP Availability Test")
    print("=" * 50)
    
    tests = [
        ("Dependencies", test_dependencies),
        ("Import", test_blip_import),
        ("Initialization", test_blip_initialization),
        ("Analysis", test_blip_analysis)
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name} test...")
        results[test_name] = test_func()
    
    print(f"\n📊 Test Results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed! BLIP is ready for production.")
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 
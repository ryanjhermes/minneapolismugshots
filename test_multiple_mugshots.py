#!/usr/bin/env python3
"""
Test BLIP filter on multiple mugshots
"""

import os
from openai_filter import BLIPImageFilter

def test_multiple_mugshots():
    """Test BLIP filter on multiple mugshots"""
    print("🧪 Testing BLIP Filter on Multiple Mugshots")
    print("=" * 60)
    
    # Initialize filter
    filter = BLIPImageFilter()
    
    # Get list of mugshots
    mugshots_dir = "mugshots"
    if not os.path.exists(mugshots_dir):
        print("❌ No mugshots directory found")
        return
    
    mugshot_files = [f for f in os.listdir(mugshots_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
    
    if not mugshot_files:
        print("❌ No mugshot files found")
        return
    
    # Test first 5 mugshots
    test_files = mugshot_files[:5]
    
    print(f"📸 Testing {len(test_files)} mugshots...")
    print()
    
    for i, filename in enumerate(test_files, 1):
        mugshot_path = os.path.join(mugshots_dir, filename)
        
        print(f"🔍 Mugshot {i}: {filename}")
        print("-" * 40)
        
        try:
            result = filter.analyze_mugshot(mugshot_path)
            
            print(f"   ✅ Approved: {result.get('approved', False)}")
            print(f"   📊 Score: {result.get('quality_score', 0)}/10")
            print(f"   📝 Reason: {result.get('reason', 'No reason')}")
            
            # Show detailed responses
            responses = result.get('responses', {})
            for question, response in responses.items():
                answer = response.get('answer', 'unknown')
                score = response.get('score', 0)
                print(f"   Q: {question[:50]}...")
                print(f"   A: {answer} (confidence: {score:.3f})")
            
            if result.get('issues'):
                print(f"   ⚠️  Issues: {', '.join(result.get('issues', []))}")
            
            print()
            
        except Exception as e:
            print(f"   ❌ Error analyzing {filename}: {e}")
            print()
    
    print("✅ Multiple mugshot test completed!")

if __name__ == "__main__":
    test_multiple_mugshots() 
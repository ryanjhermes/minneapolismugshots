# Minneapolis Mugshots 🚨

**Automated tracking and transparency of Minneapolis jail arrests with public data access.**

## About This Project

This system automatically monitors the Hennepin County Jail Roster daily and provides public access to arrest records and booking photos for transparency and community awareness.

## What We Track

- **Daily Arrests** - All new bookings in Hennepin County  
- **Booking Photos** - Official mugshots when available
- **Charges** - Criminal charges filed  
- **Bail Information** - Bond amounts and conditions
- **Arrest Details** - Dates, locations, and case info

## Public Data Access

All collected data is made freely available to the public:

📊 **Live Data:** [https://ryanjhermes.github.io/minneapolismugshots/](https://ryanjhermes.github.io/minneapolismugshots/)  
📄 **CSV Download:** [jail_roster_data.csv](https://ryanjhermes.github.io/minneapolismugshots/jail_roster_data.csv)  
📸 **Mugshot Gallery:** [View All Photos](https://ryanjhermes.github.io/minneapolismugshots/mugshots/)  

## Social Media Updates

Follow [@MinneapolisMugshots](https://instagram.com/minneapolismugshots) on Instagram for:
- **High-priority arrest alerts** featuring the 10 highest bail cases daily
- **High-quality mugshots** and case details  
- **Community awareness** of significant criminal activity
- **Transparency** in law enforcement bookings

## Data Collection Schedule

| Time | Activity |
|------|----------|
| **6:00 PM Daily** | Scan Hennepin County Jail for new arrests |
| **24/7 Posting** | Post up to 8 inmates daily, every 3 hours |
| **Continuous** | Update public database with new records |

## Posting Schedule & Limits

The system operates with flexible 24-hour posting:

- **Daily Limit**: Maximum 8 posts per day
- **Posting Hours**: 24/7 (all day, every day)
- **Posting Interval**: Every 3 hours minimum between posts
- **Single Posting**: One inmate per post (no batches)
- **AI Filtering**: All mugshots analyzed before posting

### Posting Schedule:
- **Every 3 Hours**: Automated posting attempts throughout the day
- **8 Posts Max**: Distributed across 24 hours for better reach
- **Intelligent Spacing**: 3-hour intervals prevent spam and maximize engagement
- **Reset Daily**: Counter resets each day at midnight Central Time

*Note: Posts are spread throughout the day for maximum visibility and engagement*

## Intelligent Filtering System

Our system prioritizes the most significant cases:

🏆 **Top 10 Highest Bail** - Focus on serious charges and high-profile cases  
🚫 **"Hold Without Bail"** - Prioritized as most serious cases  
💰 **Bail Amounts** - Sorted from highest to lowest dollar amounts  
📊 **Quality Control** - Only cases with both mugshots AND charges  
🤖 **AI Image Filtering** - BLIP VQA model analyzes mugshot quality before posting

## AI-Powered Quality Control

The system now uses BLIP VQA (Visual Question Answering) model to analyze mugshots before posting:

- **Image Quality Assessment** - Evaluates clarity, lighting, and framing
- **Professional Appearance** - Ensures images are suitable for public viewing
- **Technical Issue Detection** - Identifies blur, distortion, or other problems
- **Content Appropriateness** - Validates images are appropriate for social media

### AI Filtering Criteria:
1. **Image Quality** - Clear, well-lit, properly framed
2. **Professional Appearance** - Presentable and appropriate for public viewing
3. **Technical Issues** - No blur, distortion, or technical problems
4. **Content Appropriateness** - Suitable for public social media posting

## Anti-Detection Technology

To ensure reliable service:
- **Randomized posting times** (±1 minute variation)
- **Human-like delays** between posts (8-15 seconds)
- **Varied caption formats** with different emojis
- **Reduced posting frequency** for sustainability
- **Single posting mode** - Posts one inmate at a time instead of batches

## Why This Matters

**Public Safety Awareness:** Community members can stay informed about local arrests and criminal activity in their neighborhoods.

**Government Transparency:** All arrest records are public information. We make this data more accessible and searchable.

**Accountability:** Public oversight of law enforcement booking procedures and jail population trends.

**Research & Journalism:** Provides data for reporters, researchers, and advocates studying criminal justice trends.

## Data Sources

- **Primary:** Hennepin County Sheriff's Office Jail Roster
- **Updated:** Daily at 6:00 PM Central Time  
- **Coverage:** Minneapolis and surrounding Hennepin County areas
- **Records:** Only includes individuals officially booked and processed

## Privacy & Legal

All information displayed is:
- ✅ **Public record** per Minnesota Statute
- ✅ **Officially released** by Hennepin County  
- ✅ **Automatically updated** when records change
- ✅ **Factual booking information** only

*Note: Booking does not imply guilt. All individuals are presumed innocent until proven guilty in court.*

## Setup Instructions

### Prerequisites
- Python 3.8+
- Chrome browser (for web scraping)
- Transformers and PyTorch (for AI filtering)

### Installation
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with your API keys:
   ```
   ACCESS_TOKEN=your_meta_access_token_here
   APP_ID=your_meta_app_id_here
   BUSINESS_ID=your_meta_business_id_here
   ```

### Usage
```bash
# Full scraping with AI filtering
python data.py

# Test scraping (25 inmates)
python data.py test

# Post next inmate with AI filtering
python data.py post-next

# Test AI filtering
python data.py test-ai-filter

# Check posting queue
python data.py check-queue
```

---

**Data updated daily • Follow for real-time alerts • Public records transparency**
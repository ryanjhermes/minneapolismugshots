# Minneapolis Mugshots Scraper

Automated daily scraping of Hennepin County Jail Roster with GitHub Actions deployment.

## 🚀 Features

- **Daily automation** via GitHub Actions
- **Mugshot extraction** and organization
- **Public hosting** via GitHub Pages
- **CSV data export** with image references
- **Zero cost** operation

## 📁 File Structure

```
├── .github/workflows/daily-scrape.yml  # GitHub Actions workflow
├── data.py                             # Main scraper script
├── mugshots/                           # Mugshot images folder
├── jail_roster_data.csv               # Extracted data
├── requirements.txt                    # Python dependencies
└── docs/                              # GitHub Pages content (auto-generated)
```

## 🛠️ Local Setup

1. **Clone this repository**
   ```bash
   git clone <your-repo-url>
   cd minneapolismugshots
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual Meta API credentials
   ```

5. **Test locally**
   ```bash
   python data.py
   ```

## ⚙️ GitHub Repository Setup

### 1. Push to GitHub
```bash
git add .
git commit -m "Initial commit"
git push origin main
```

### 2. Configure GitHub Secrets
Go to your GitHub repository → Settings → Secrets and variables → Actions

Add these repository secrets:
- `META_ACCESS_TOKEN`: Your Meta API access token
- `META_APP_ID`: Your Meta app ID  
- `META_BUSINESS_ID`: Your Meta business ID

### 3. Enable GitHub Pages
1. Go to Settings → Pages
2. Source: "GitHub Actions"
3. Save

### 4. Enable Actions
1. Go to Actions tab
2. Enable workflows if prompted
3. The workflow will run automatically daily at 6 AM UTC

## 🔄 Manual Trigger

You can manually trigger the workflow:
1. Go to Actions tab
2. Select "Daily Jail Roster Scrape"
3. Click "Run workflow"

## 📊 Data Access

Once deployed, your data will be available at:

- **CSV Data**: `https://yourusername.github.io/repo-name/jail_roster_data.csv`
- **Mugshots**: `https://yourusername.github.io/repo-name/mugshots/mugshot_NAME.jpg`
- **Web Interface**: `https://yourusername.github.io/repo-name/`

## 📱 Instagram API Integration

Use the public URLs in your Instagram API calls:

```python
# Example: Using the public mugshot URLs
image_url = "https://yourusername.github.io/repo-name/mugshots/mugshot_JOHN_DOE.jpg"
```

## ⏰ Schedule

- **Runs daily** at 6:00 AM UTC
- **Configurable** in `.github/workflows/daily-scrape.yml`
- **Manual trigger** available anytime

## 🔧 Customization

### Change Schedule
Edit `.github/workflows/daily-scrape.yml`:
```yaml
schedule:
  - cron: '0 6 * * *'  # 6 AM UTC daily
```

### Modify Data Fields
Edit `data.py` to change extracted fields in the `extract_key_details()` function.

## 🐛 Troubleshooting

### Common Issues

1. **Workflow fails**: Check Actions tab for error logs
2. **Images not loading**: Verify GitHub Pages is enabled
3. **No data extracted**: Check if jail roster website changed

### Debug Locally
```bash
# Run with debug output
python data.py

# Check environment variables
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ACCESS_TOKEN')[:10] + '...')"
```

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Test locally
5. Submit a pull request

---

**⚡ Fully automated, zero-cost solution for daily jail roster data collection and public hosting!** 
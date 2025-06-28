# Railway.app Deployment Guide

## Files Required for Railway Deployment

Upload these files to your GitHub repository for Railway deployment:

### Essential Files (Required)
```
app.py                 # Main Flask application
main.py               # Application entry point
requirements.txt      # Python dependencies (auto-generated)
runtime.txt           # Python version
railway.toml          # Railway configuration
gunicorn.conf.py      # Gunicorn server configuration
Procfile              # Process definition
```

### Supporting Files (Recommended)
```
replit.md             # Project documentation
url_extractor.py      # TVNation URL extraction utility
RAILWAY_DEPLOYMENT.md # This deployment guide
```

## Dependencies (requirements.txt)
```
Flask==3.0.0
gunicorn==23.0.0
requests==2.31.0
```

## Runtime Configuration (runtime.txt)
```
python-3.11.7
```

## Process Definition (Procfile)
```
web: gunicorn --config gunicorn.conf.py main:app
```

## Railway Configuration (railway.toml)
```toml
[build]
builder = "NIXPACKS"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10

[env]
PYTHON_VERSION = "3.11.7"
PYTHONPATH = "/app"
FLASK_ENV = "production"
```

## Quick Deploy Steps

1. **Create GitHub Repository**
   - Create new repository on GitHub
   - Upload the required files listed above

2. **Connect to Railway**
   - Go to railway.app
   - Click "Deploy from GitHub repo"
   - Select your repository

3. **Environment Variables**
   - No environment variables required for basic functionality
   - Railway automatically provides PORT variable

4. **Domain Setup**
   - Railway provides automatic `.up.railway.app` domain
   - Custom domains can be configured in Railway dashboard

## Features Included

✅ **Universal M3U8 Support**
- Elderflower/Radon domains with specialized bypass
- Any M3U8 URL with tokens
- Regular M3U8 streams without tokens
- TVNation URL extraction

✅ **Player Compatibility**
- Chrome/Safari browser support
- MX Player (deployment dependent)
- VLC and external players
- Direct streaming endpoints

✅ **Production Ready**
- Gunicorn WSGI server
- Multiple worker processes
- Health check endpoint
- Automatic restarts
- Error handling

## Testing After Deployment

1. Visit your Railway app URL
2. Enter any M3U8 URL (with or without tokens)
3. Test in browser and external players
4. Check health endpoint: `your-app.up.railway.app/health`

## Troubleshooting

- **503 Errors**: Check Railway logs for worker issues
- **M3U8 Not Loading**: Verify URL format and token presence
- **Slow Loading**: Normal for first request after idle period
- **Player Issues**: Try different endpoints (/playlist.m3u8, /stream, /mx)
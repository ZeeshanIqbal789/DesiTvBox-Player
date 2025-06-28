#!/usr/bin/env python3
"""
M3U8 HLS Streaming Server for Railway - Complete M3U8/HLS Support
Specialized for m3u8 playlists with isolation system and fast streaming
Production-ready version for Railway.app deployment with HLS optimization
"""
from flask import Flask, Response, request, redirect, jsonify
import requests
import threading
import time
import os
import hashlib
import logging
from datetime import datetime, timedelta
from urllib.parse import unquote, urljoin, urlparse, parse_qs
import subprocess
import signal
import sys
import gc
import re
from bs4 import BeautifulSoup
import base64

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret-key-for-development")

# M3U8 HLS STREAMING CONFIGURATION
HLS_CHUNK_SIZE = 1024 * 1024  # 1MB chunks for m3u8 segments
SEGMENT_CHUNK_SIZE = 512 * 1024  # 512KB chunks for TS segments
PLAYLIST_CACHE_SECONDS = 30  # Cache playlists for 30 seconds

# ISOLATION VARIABLES - Each m3u8 stream gets completely separate session
import json
from flask import session

# Worker-local session storage for m3u8 streams
m3u8_sessions = {}  # Isolated sessions per m3u8 stream
m3u8_metadata = {}  # Metadata per m3u8 stream
server_running = True

def get_current_m3u8_url():
    """Get current m3u8 URL from session"""
    return session.get('current_m3u8_url', None)

def get_active_session_id():
    """Get active session ID from session"""
    return session.get('active_m3u8_id', None)

def is_m3u8_url(url):
    """Check if URL is an m3u8 playlist"""
    if not url:
        return False
    return url.lower().endswith('.m3u8') or 'm3u8' in url.lower()

def extract_base_url(m3u8_url):
    """Extract base URL from m3u8 URL for relative segment resolution"""
    parsed = urlparse(m3u8_url)
    return f"{parsed.scheme}://{parsed.netloc}{'/'.join(parsed.path.split('/')[:-1])}/"

def is_tvnation_url(url):
    """Check if URL is a TVNation embedded player URL"""
    return 'tvnation.me' in url and 'flix.php' in url

def extract_tvnation_code(url):
    """Extract the URL code from TVNation URL"""
    if '?url=' in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get('url', [None])[0]
    return None

def bypass_url_restrictions(original_url):
    """Bypass URL restrictions by using proper headers and referrers"""
    try:
        # Use the enhanced create_bypass_session function for consistent header handling
        session_obj = create_bypass_session(original_url)
        
        # Test the URL with bypass headers - use GET instead of HEAD for better compatibility
        response = session_obj.get(original_url, timeout=15, stream=True)
        if response.status_code == 200:
            logger.info(f"Successfully bypassed restrictions for: {original_url[:50]}...")
            # Don't consume the response body, just close it
            response.close()
            return session_obj, True
        else:
            logger.warning(f"Bypass failed, status: {response.status_code}")
            return session_obj, False
            
    except Exception as e:
        logger.error(f"Bypass attempt failed: {e}")
        return None, False

def create_bypass_session(url):
    """Create a session with appropriate bypass headers for the given URL"""
    session_obj = requests.Session()
    
    # Check if URL has token parameter (common for protected M3U8 streams)
    has_token = '?token=' in url or '&token=' in url
    
    # Use specialized headers for elderflower/radon domains
    if 'elderflower' in url or 'radon' in url:
        session_obj.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Infinix X657B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.7151.89 Mobile Safari/537.36',
            'Referer': 'http://www.tvnation.me/flix.php?url=kxrOyaORnebzor2',
            'Origin': 'http://www.tvnation.me',
            'Accept': 'application/x-mpegURL,application/vnd.apple.mpegurl,video/mp2t,*/*',
            'X-Forwarded-For': '119.155.83.167, 172.69.244.190',
            'X-Real-IP': '119.155.83.167',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
    elif has_token:
        # Enhanced headers for any M3U8 with token - use mobile user agent for better compatibility
        session_obj.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/x-mpegURL,application/vnd.apple.mpegurl,video/mp2t,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'DNT': '1',
            'Sec-Fetch-Dest': 'video',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # Try to extract domain and use it as referer for better compatibility
        try:
            parsed_url = urlparse(url)
            domain_referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"
            session_obj.headers['Referer'] = domain_referer
        except:
            pass
    else:
        # Standard headers for regular M3U8 URLs (no tokens)
        session_obj.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/x-mpegURL,application/vnd.apple.mpegurl,video/mp2t,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'DNT': '1'
        })
    
    return session_obj

def process_m3u8_playlist(playlist_content, base_url, session_id):
    """Process m3u8 playlist and convert relative URLs to proxy URLs"""
    lines = playlist_content.split('\n')
    processed_lines = []
    
    # Get the host for creating proxy URLs
    request_host = request.host
    if 'replit.dev' in request_host or 'replit.app' in request_host:
        proxy_base = f"https://{request_host}"
    else:
        proxy_base = f"http://{request_host}"
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            # This is a segment URL
            if line.startswith('http'):
                # Absolute URL - proxy it
                proxy_url = f"{proxy_base}/segment/{session_id}?url={line}"
            else:
                # Relative URL - resolve and proxy it
                # Handle special case for elderflower URLs with incomplete paths
                if line.startswith('/'):
                    # Extract domain from base_url
                    parsed_base = urlparse(base_url)
                    absolute_url = f"{parsed_base.scheme}://{parsed_base.netloc}{line}"
                else:
                    absolute_url = urljoin(base_url, line)
                proxy_url = f"{proxy_base}/segment/{session_id}?url={absolute_url}"
            processed_lines.append(proxy_url)
        else:
            # Playlist metadata line - adjust some parameters for better compatibility
            if line.startswith('#EXT-X-TARGETDURATION:'):
                # Keep original duration
                processed_lines.append(line)
            elif line.startswith('#EXT-X-MEDIA-SEQUENCE:'):
                # Keep original sequence
                processed_lines.append(line)
            else:
                processed_lines.append(line)
    
    return '\n'.join(processed_lines)

@app.route('/')
def home():
    # Use proper external URL for Replit deployment
    if 'replit.dev' in request.host or 'replit.app' in request.host:
        base_url = f"https://{request.host}"
    else:
        base_url = f"http://{request.host}"
    
    current_url = get_current_m3u8_url()
    active_session = get_active_session_id()
    cache_buster = session.get('cache_buster', 0)
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>M3U8 HLS Streaming Server</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script>
        // Keep-alive mechanism to prevent app from going offline
        setInterval(function() {{
            fetch('/keepalive', {{method: 'GET'}}).catch(function(error) {{
                console.log('Keep-alive ping failed:', error);
            }});
        }}, 30000); // Ping every 30 seconds
        
        // Also ping when page becomes visible again
        document.addEventListener('visibilitychange', function() {{
            if (!document.hidden) {{
                fetch('/keepalive', {{method: 'GET'}}).catch(function(error) {{
                    console.log('Visibility ping failed:', error);
                }});
            }}
        }});
    </script>
</head>
<body>
    <div class="container mt-4">
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <h1 class="text-center mb-4">📺 M3U8 HLS Streaming Server</h1>
                
                <div class="alert alert-primary text-center" role="alert">
                    <h4 class="alert-heading">🎯 M3U8/HLS OPTIMIZED v4.0</h4>
                    <p class="mb-2">Complete HLS playlist support + Fast segment streaming</p>
                    <p class="mb-2"><strong>✓ Chrome Browser</strong> + <strong>✓ External Players</strong> (VLC, MPV, MX Player, etc.)</p>
                    <hr>
                    <p class="mb-0 small">
                        <strong>Session:</strong> {active_session or 'None'} | 
                        <strong>Cache:</strong> {cache_buster} | 
                        <strong>Time:</strong> {datetime.now().strftime('%H:%M:%S')}
                    </p>
                </div>

                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="card-title mb-0">📹 Set M3U8 Stream URL</h5>
                    </div>
                    <div class="card-body">
                        <form action="/set-m3u8" method="post">
                            <div class="mb-3">
                                <input type="text" name="m3u8_url" class="form-control" 
                                       placeholder="Enter M3U8 playlist URL here..." 
                                       value="{current_url if current_url else ''}" required>
                            </div>
                            <div class="mb-3">
                                <small class="text-muted">
                                    <strong>✓ Universal M3U8 Support:</strong> Works with ALL M3U8 URLs (with or without tokens)<br>
                                    <strong>✓ Token-protected streams:</strong> https://radon.elderflower.cc/.../480.m3u8?token=...<br>
                                    <strong>✓ Regular M3U8 streams:</strong> https://example.com/playlist.m3u8<br>
                                    <strong>✓ TVNation URLs:</strong> Automatic detection and extraction<br>
                                    <strong>✓ Public streams:</strong> Works with standard HLS streams from any domain
                                </small>
                            </div>
                            <button type="submit" class="btn btn-primary btn-lg w-100">
                                🔄 Set M3U8 Stream (Complete Isolation)
                            </button>
                        </form>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="card-title mb-0">🎬 Browser Streaming URLs</h5>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <label class="form-label"><strong>HLS Playlist (Chrome/Safari):</strong></label>
                            <div class="input-group">
                                <input type="text" value="{base_url}/playlist.m3u8" readonly 
                                       class="form-control font-monospace" onclick="this.select()">
                                <button class="btn btn-outline-secondary" type="button" 
                                        onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">
                                    📋 Copy
                                </button>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label"><strong>Direct Stream (Fallback):</strong></label>
                            <div class="input-group">
                                <input type="text" value="{base_url}/stream" readonly 
                                       class="form-control font-monospace" onclick="this.select()">
                                <button class="btn btn-outline-secondary" type="button" 
                                        onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">
                                    📋 Copy
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card mb-4 border-success">
                    <div class="card-header bg-success text-white">
                        <h5 class="card-title mb-0">📱 External Player URLs</h5>
                    </div>
                    <div class="card-body">
                        {'<div class="mb-3"><label class="form-label"><strong>MX Player Optimized:</strong></label><div class="input-group"><input type="text" value="' + base_url + '/mx?url=' + (current_url or 'SET_M3U8_URL_FIRST') + '" readonly class="form-control font-monospace" onclick="this.select()"><button class="btn btn-success" type="button" onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">📋 Copy for MX Player</button></div></div>' if current_url else '<div class="alert alert-warning"><strong>Set M3U8 URL first</strong> to generate player links</div>'}
                        {'<div class="mb-3"><label class="form-label"><strong>VLC/MPV Direct:</strong></label><div class="input-group"><input type="text" value="' + base_url + '/playlist.m3u8?url=' + (current_url or 'SET_M3U8_URL_FIRST') + '" readonly class="form-control font-monospace small" onclick="this.select()"><button class="btn btn-outline-success" type="button" onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">📋 Copy</button></div></div>' if current_url else ''}
                        {'<div class="mb-0"><label class="form-label"><strong>Universal Stream:</strong></label><div class="input-group"><input type="text" value="' + base_url + '/stream?url=' + (current_url or 'SET_M3U8_URL_FIRST') + '" readonly class="form-control font-monospace small" onclick="this.select()"><button class="btn btn-outline-success" type="button" onclick="navigator.clipboard.writeText(this.previousElementSibling.value)">📋 Copy</button></div></div>' if current_url else ''}
                        <div class="alert alert-info mt-3 mb-0">
                            <strong>⚠️ M3U8 Support:</strong> All URLs support HLS playlists. External players will receive properly formatted m3u8 streams.
                        </div>
                        <div class="alert alert-warning mt-2 mb-0">
                            <strong>🔓 Bypass Support:</strong> For restricted M3U8 URLs that only work on specific websites (like TVNation), this server automatically applies bypass headers to make them work in any player.
                        </div>
                    </div>
                </div>

                <div class="d-grid gap-2 d-md-flex justify-content-md-center">
                    <a href="/playlist.m3u8" class="btn btn-success btn-lg">
                        ▶️ Test M3U8 Stream
                    </a>
                    <a href="/test-hls" class="btn btn-info btn-lg">
                        🔍 Test HLS Playlist
                    </a>
                </div>

                <div class="mt-4 text-center">
                    <small class="text-muted">
                        Deployed on Railway.app | HLS streaming with complete m3u8 support
                    </small>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    """

@app.route('/set-m3u8', methods=['POST'])
def set_m3u8():
    new_url = request.form.get('m3u8_url', '').strip()
    if new_url:
        # Validate it's an m3u8 URL
        if not is_m3u8_url(new_url):
            return f"""
            <div class="alert alert-danger text-center">
                <h4>❌ Invalid M3U8 URL</h4>
                <p>Please provide a valid M3U8 playlist URL (should end with .m3u8)</p>
                <a href="/" class="btn btn-primary">← Go Back</a>
            </div>
            """
        
        # Store in Flask session for cross-worker persistence
        cache_buster = session.get('cache_buster', 0) + 1
        active_m3u8_id = f"m3u8_{cache_buster}_{int(time.time())}"
        
        # Store in session
        session['current_m3u8_url'] = new_url
        session['active_m3u8_id'] = active_m3u8_id
        session['cache_buster'] = cache_buster
        
        # Clear local worker sessions
        m3u8_sessions.clear()
        m3u8_metadata.clear()
        
        # CREATE COMPLETELY ISOLATED M3U8 SESSION
        isolated_session = requests.Session()
        isolated_session.headers.update({
            'User-Agent': f'HLSProxy-{active_m3u8_id}/4.0',
            'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Connection': 'keep-alive',
            'Accept': 'application/x-mpegURL,application/vnd.apple.mpegurl,video/mp2t,*/*',
            'X-M3U8-Session': active_m3u8_id,
            'X-Cache-Buster': str(cache_buster)
        })
        
        # STORE ISOLATED M3U8 SESSION
        m3u8_sessions[active_m3u8_id] = isolated_session
        m3u8_metadata[active_m3u8_id] = {
            'url': new_url,
            'created': time.time(),
            'cache_buster': cache_buster,
            'session_id': active_m3u8_id,
            'base_url': extract_base_url(new_url)
        }
        
        # FORCE COMPLETE MEMORY CLEANUP
        gc.collect()
        
        logger.info(f"M3U8 ISOLATION COMPLETE: {active_m3u8_id}")
        logger.info(f"ALL OLD M3U8 SESSIONS DESTROYED")
        logger.info(f"NEW M3U8 STREAM ISOLATED: {new_url[:50]}...")
        
        # Use proper external URL for Replit deployment
        if 'replit.dev' in request.host or 'replit.app' in request.host:
            base_url = f"https://{request.host}"
        else:
            base_url = f"http://{request.host}"
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>M3U8 Stream Isolated Successfully</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-lg-6">
                <div class="text-center mb-4">
                    <h2>✅ M3U8 Stream Completely Isolated!</h2>
                </div>
                
                <div class="alert alert-success" role="alert">
                    <h4 class="alert-heading">🎯 HLS ISOLATION COMPLETE!</h4>
                    <p><strong>Session ID:</strong> {active_m3u8_id}</p>
                    <p><strong>Cache Buster:</strong> #{cache_buster}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime('%H:%M:%S')}</p>
                    <p class="mb-0">Zero contamination from old streams!</p>
                </div>
                
                <div class="card mb-4">
                    <div class="card-header">
                        <h6 class="card-title mb-0">📹 New M3U8 Stream Isolated</h6>
                    </div>
                    <div class="card-body">
                        <p class="small text-break bg-light p-2 rounded">{new_url}</p>
                        <p class="text-muted mb-0">HLS streaming with segment proxying ready</p>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header">
                        <h6 class="card-title mb-0">🚀 HLS Streaming URLs</h6>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <input type="text" value="{base_url}/playlist.m3u8" readonly 
                                   class="form-control font-monospace" onclick="this.select()">
                        </div>
                        <div class="mb-0">
                            <input type="text" value="{base_url}/stream" readonly 
                                   class="form-control font-monospace" onclick="this.select()">
                        </div>
                    </div>
                </div>

                <div class="d-grid gap-2 d-md-flex justify-content-md-center">
                    <a href="/" class="btn btn-outline-primary">← Back to Home</a>
                    <a href="/playlist.m3u8" class="btn btn-success">▶️ Test M3U8</a>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
        """
    return redirect('/')

@app.route('/playlist.m3u8', methods=['GET', 'HEAD', 'OPTIONS'])
def m3u8_playlist():
    """Serve M3U8 playlist with proxied segment URLs"""
    if request.method == 'OPTIONS':
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    # Check for URL parameter for direct m3u8 streaming
    url_param = request.args.get('url')
    if url_param and is_m3u8_url(url_param):
        return stream_m3u8_playlist(url_param)
    
    current_url = get_current_m3u8_url()
    if not current_url:
        return Response(
            "No M3U8 URL set. Please set an M3U8 playlist URL on the main page first.",
            status=400,
            headers={'Content-Type': 'text/plain'}
        )
    
    return stream_m3u8_playlist(current_url)

@app.route('/stream', methods=['GET', 'HEAD', 'OPTIONS'])
def direct_stream():
    """Direct stream endpoint for non-HLS players"""
    if request.method == 'OPTIONS':
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    # Check for URL parameter
    url_param = request.args.get('url')
    if url_param:
        if is_m3u8_url(url_param):
            return stream_m3u8_playlist(url_param)
        else:
            return stream_direct_video(url_param)
    
    current_url = get_current_m3u8_url()
    if not current_url:
        return Response(
            "No stream URL set. Please set a stream URL on the main page first.",
            status=400,
            headers={'Content-Type': 'text/plain'}
        )
    
    if is_m3u8_url(current_url):
        return stream_m3u8_playlist(current_url)
    else:
        return stream_direct_video(current_url)

@app.route('/mx', methods=['GET', 'HEAD', 'OPTIONS'])
def mx_player_stream():
    """MX Player optimized streaming endpoint"""
    if request.method == 'OPTIONS':
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    url_param = request.args.get('url')
    if not url_param:
        current_url = get_current_m3u8_url()
        if not current_url:
            return Response(
                "MX Player Support: Add ?url=YOUR_M3U8_URL to this endpoint or set M3U8 URL on main page first",
                status=400,
                headers={
                    'Content-Type': 'text/plain',
                    'Access-Control-Allow-Origin': '*'
                }
            )
        url_param = current_url
    
    logger.info(f"MX Player request: {url_param[:50]}...")
    
    if is_m3u8_url(url_param):
        return stream_m3u8_for_mx_player(url_param)
    else:
        return stream_direct_video(url_param, mx_player=True)

@app.route('/segment/<session_id>')
def stream_segment(session_id):
    """Stream individual HLS segments"""
    segment_url = request.args.get('url')
    if not segment_url:
        return Response("Segment URL required", status=400)
    
    # Get session or create new one with bypass headers
    if session_id in m3u8_sessions:
        session_obj = m3u8_sessions[session_id]
    else:
        session_obj = create_bypass_session(segment_url)
        m3u8_sessions[session_id] = session_obj
    
    try:
        range_header = request.headers.get('Range')
        headers = dict(session_obj.headers)
        
        if range_header:
            headers['Range'] = range_header
        
        response = session_obj.get(segment_url, headers=headers, stream=True, timeout=20)
        
        if response.status_code in [200, 206]:
            def generate_segment():
                try:
                    for chunk in response.iter_content(chunk_size=SEGMENT_CHUNK_SIZE):
                        if chunk:
                            yield chunk
                except Exception as e:
                    logger.error(f"Segment chunk error: {e}")
            
            flask_response = Response(generate_segment(), mimetype='video/mp2t')
            flask_response.headers['Access-Control-Allow-Origin'] = '*'
            flask_response.headers['Cache-Control'] = 'no-cache'
            flask_response.headers['Accept-Ranges'] = 'bytes'
            
            # Copy important headers from original response
            if 'Content-Length' in response.headers:
                flask_response.headers['Content-Length'] = response.headers['Content-Length']
            if 'Content-Range' in response.headers:
                flask_response.headers['Content-Range'] = response.headers['Content-Range']
            
            return flask_response
        else:
            logger.error(f"Segment request failed: {response.status_code}")
            return Response(f"Segment request failed: {response.status_code}", status=response.status_code)
            
    except Exception as e:
        logger.error(f"Segment streaming error: {e}")
        return Response(f"Segment error: {str(e)}", status=500)

def stream_m3u8_playlist(m3u8_url):
    """Stream M3U8 playlist with proxied segment URLs"""
    try:
        # Get or create session
        active_session_id = get_active_session_id()
        if active_session_id and active_session_id in m3u8_sessions:
            session_obj = m3u8_sessions[active_session_id]
        else:
            # Create new session for direct URL access with bypass headers
            active_session_id = f"direct_{int(time.time())}"
            session_obj = create_bypass_session(m3u8_url)
            m3u8_sessions[active_session_id] = session_obj
        
        # Fetch the m3u8 playlist
        response = session_obj.get(m3u8_url, timeout=15)
        
        if response.status_code == 200:
            base_url = extract_base_url(m3u8_url)
            processed_playlist = process_m3u8_playlist(response.text, base_url, active_session_id)
            
            response_obj = Response(processed_playlist, mimetype='application/x-mpegURL')
            response_obj.headers['Access-Control-Allow-Origin'] = '*'
            response_obj.headers['Cache-Control'] = f'max-age={PLAYLIST_CACHE_SECONDS}'
            return response_obj
        else:
            logger.error(f"Failed to fetch m3u8: {response.status_code}")
            return Response(f"Failed to fetch M3U8 playlist: {response.status_code}", status=response.status_code)
            
    except Exception as e:
        logger.error(f"M3U8 streaming error: {e}")
        return Response(f"M3U8 streaming error: {str(e)}", status=500)

def stream_m3u8_for_mx_player(m3u8_url):
    """Stream M3U8 specifically optimized for MX Player"""
    try:
        session_obj = requests.Session()
        session_obj.headers.update({
            'User-Agent': 'MXPlayer/1.46.15 (Android)',
            'Accept': 'application/x-mpegURL,video/*,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        })
        
        response = session_obj.get(m3u8_url, timeout=15)
        
        if response.status_code == 200:
            # For MX Player, we might want to serve the playlist directly
            # or with minimal processing depending on the playlist structure
            response_obj = Response(response.text, mimetype='application/x-mpegURL')
            response_obj.headers['Access-Control-Allow-Origin'] = '*'
            response_obj.headers['Cache-Control'] = 'no-cache'
            response_obj.headers['Content-Disposition'] = 'inline'
            return response_obj
        else:
            return Response(f"Failed to fetch M3U8: {response.status_code}", status=response.status_code)
            
    except Exception as e:
        logger.error(f"MX Player M3U8 error: {e}")
        return Response(f"MX Player M3U8 error: {str(e)}", status=500)

def stream_direct_video(video_url, mx_player=False):
    """Stream direct video for non-m3u8 URLs"""
    def generate_stream():
        try:
            session_obj = requests.Session()
            
            user_agent = request.headers.get('User-Agent', '')
            if mx_player or 'MX Player' in user_agent:
                session_obj.headers.update({
                    'User-Agent': 'MXPlayer/1.46.15 (Android)',
                    'Accept': 'video/mp4,video/*,*/*',
                    'Accept-Language': 'en-US,en;q=0.9'
                })
            else:
                session_obj.headers.update({
                    'User-Agent': f'VideoProxy-{int(time.time())}/4.0',
                    'Accept': '*/*',
                    'Connection': 'keep-alive'
                })
            
            range_header = request.headers.get('Range')
            headers = dict(session_obj.headers)
            if range_header:
                headers['Range'] = range_header
            
            response = session_obj.get(video_url, headers=headers, stream=True, timeout=20)
            
            if response.status_code in [200, 206]:
                for chunk in response.iter_content(chunk_size=HLS_CHUNK_SIZE):
                    if chunk:
                        yield chunk
            else:
                logger.error(f"Direct video request failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Direct video streaming error: {e}")
    
    response = Response(generate_stream())
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Accept-Ranges'] = 'bytes'
    return response

@app.route('/test-hls')
def test_hls():
    """Test HLS functionality"""
    current_url = get_current_m3u8_url()
    if not current_url:
        return redirect('/')
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>HLS Test Player</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <div class="container mt-4">
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <h1 class="text-center mb-4">🧪 HLS Stream Test</h1>
                
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="card-title mb-0">📺 HLS Video Player</h5>
                    </div>
                    <div class="card-body">
                        <div id="loading-message" class="alert alert-info text-center">
                            <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                            Loading M3U8 stream... (This may take a moment like the original TVNation player)
                        </div>
                        <video id="video-player" controls width="100%" style="max-height: 400px; display: none;">
                            <source src="/playlist.m3u8" type="application/x-mpegURL">
                            Your browser does not support HLS playback.
                        </video>
                        <div id="error-message" class="alert alert-danger" style="display: none;">
                            <strong>Playback Error:</strong> Unable to load video. Try refreshing or using an external player.
                        </div>
                    </div>
                </div>
                
                <script>
                    const video = document.getElementById('video-player');
                    const loading = document.getElementById('loading-message');
                    const error = document.getElementById('error-message');
                    
                    // Show video when it's ready
                    video.addEventListener('loadstart', function() {{
                        loading.style.display = 'block';
                        error.style.display = 'none';
                    }});
                    
                    video.addEventListener('canplay', function() {{
                        loading.style.display = 'none';
                        video.style.display = 'block';
                    }});
                    
                    video.addEventListener('error', function() {{
                        loading.style.display = 'none';
                        error.style.display = 'block';
                    }});
                    
                    // Simulate the delay like TVNation - load after a short delay
                    setTimeout(function() {{
                        video.load();
                    }}, 2000);
                </script>
                
                <div class="card mb-4">
                    <div class="card-header">
                        <h6 class="card-title mb-0">🔗 Stream Information</h6>
                    </div>
                    <div class="card-body">
                        <p><strong>Source URL:</strong></p>
                        <p class="small text-break bg-light p-2 rounded">{current_url}</p>
                        <p><strong>Proxy URL:</strong></p>
                        <p class="small text-break bg-light p-2 rounded">{request.host}/playlist.m3u8</p>
                    </div>
                </div>
                
                <div class="d-grid gap-2 d-md-flex justify-content-md-center">
                    <a href="/" class="btn btn-outline-primary">← Back to Home</a>
                    <a href="/playlist.m3u8" class="btn btn-success">📥 Download M3U8</a>
                    <a href="/test-bypass" class="btn btn-warning">🔓 Test Bypass</a>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
    """

@app.route('/test-bypass')
def test_bypass():
    """Test URL bypass functionality"""
    current_url = get_current_m3u8_url()
    if not current_url:
        return jsonify({"error": "No M3U8 URL set"})
    
    try:
        # Test bypass functionality
        session_obj, success = bypass_url_restrictions(current_url)
        if success and session_obj:
            # Try to fetch the actual content
            response = session_obj.get(current_url, timeout=10)
            content_preview = response.text[:500] if response.text else "No content"
            
            return jsonify({
                "bypass_status": "SUCCESS",
                "http_status": response.status_code,
                "content_type": response.headers.get('Content-Type', 'Unknown'),
                "content_length": len(response.text) if response.text else 0,
                "content_preview": content_preview,
                "headers_used": dict(session_obj.headers)
            })
        else:
            return jsonify({
                "bypass_status": "FAILED", 
                "message": "Bypass headers did not work",
                "headers_used": dict(session_obj.headers) if session_obj else {}
            })
            
    except Exception as e:
        return jsonify({
            "bypass_status": "ERROR",
            "error": str(e),
            "url": current_url[:50] + "..." if len(current_url) > 50 else current_url
        })

@app.route('/health')
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "service": "m3u8-hls-streaming",
        "version": "4.0",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(m3u8_sessions)
    })

@app.route('/keepalive')
def keepalive():
    """Keep-alive endpoint to prevent server sleep"""
    return jsonify({
        "status": "alive",
        "timestamp": datetime.now().isoformat(),
        "sessions": len(m3u8_sessions)
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found", "message": "The requested resource was not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error", "message": "An internal error occurred"}), 500

# Background cleanup task
def cleanup_sessions():
    """Background task to cleanup old sessions"""
    while server_running:
        try:
            current_time = time.time()
            sessions_to_remove = []
            
            for session_id, metadata in m3u8_metadata.items():
                if current_time - metadata['created'] > 3600:  # 1 hour
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                if session_id in m3u8_sessions:
                    m3u8_sessions[session_id].close()
                    del m3u8_sessions[session_id]
                if session_id in m3u8_metadata:
                    del m3u8_metadata[session_id]
                logger.info(f"Cleaned up old session: {session_id}")
            
            if sessions_to_remove:
                gc.collect()
                
            time.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
            time.sleep(60)

# Signal handlers for graceful shutdown
def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global server_running
    logger.info("Received shutdown signal, cleaning up...")
    server_running = False
    
    # Close all sessions
    for session_obj in m3u8_sessions.values():
        try:
            session_obj.close()
        except:
            pass
    
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Start background cleanup thread
cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
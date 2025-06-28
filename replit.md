# Replit.md - M3U8 HLS Streaming Server

## Overview

This is a Flask-based M3U8 HLS streaming server designed for Railway deployment that implements an isolated streaming architecture specifically optimized for m3u8 playlists and HLS (HTTP Live Streaming) content. The application serves as a specialized proxy/streaming server that handles M3U8 playlist processing, segment delivery, and maintains compatibility with all major video players.

## System Architecture

### Backend Architecture
- **Framework**: Flask (Python 3.11)
- **WSGI Server**: Gunicorn with optimized configuration for HLS streaming
- **Deployment**: Railway.app with autoscale deployment target
- **Architecture Pattern**: Single-service HLS proxy server with session isolation
- **Streaming Protocol**: HLS (HTTP Live Streaming) with M3U8 playlist support

### Core Design Principles
- **M3U8 Specialization**: Complete HLS playlist support with segment proxying
- **Isolation System**: Each m3u8 stream gets a completely separate session to prevent interference
- **Fast Streaming**: 1MB chunks for HLS segments, 512KB for TS segments
- **Playlist Processing**: Dynamic URL rewriting for segment proxying
- **Production Ready**: Comprehensive logging, error handling, and graceful shutdowns

## Key Components

### 1. M3U8 Session Management
- `m3u8_sessions`: Dictionary maintaining isolated sessions per m3u8 stream
- `m3u8_metadata`: Stores metadata for each m3u8 stream including base URLs
- `active_m3u8_id`: Tracks currently active m3u8 stream to prevent conflicts
- Cache busting mechanisms to ensure fresh playlist delivery

### 2. HLS Streaming Engine
- **HLS Chunk Size**: 1MB chunks for m3u8 segments
- **Segment Chunk Size**: 512KB for TS segments
- **Playlist Cache**: 30-second cache for M3U8 playlists
- **URL Rewriting**: Automatic conversion of relative segment URLs to proxy URLs
- **Base URL Resolution**: Intelligent base URL extraction for relative segment resolution

### 3. Flask Application Structure
- Main application in `app.py` with complete M3U8 support
- Production configuration via `gunicorn.conf.py`
- Railway-specific deployment configuration in `railway.toml`
- Specialized endpoints for different streaming scenarios

### 4. Process Management
- Gunicorn workers: `CPU cores * 2 + 1` for optimal concurrency
- Worker timeout: 120 seconds for HLS streaming operations
- Connection limits and restart policies for stability

## Data Flow

1. **M3U8 Request**: Client requests M3U8 playlist content
2. **Session Isolation**: System creates/retrieves isolated session for specific m3u8 stream
3. **Playlist Processing**: Server fetches M3U8 playlist and rewrites segment URLs for proxying
4. **Segment Proxying**: Individual HLS segments are streamed through dedicated proxy endpoints
5. **Adaptive Delivery**: Segments are delivered with optimized chunking strategies
6. **Session Cleanup**: Isolated sessions are managed and cleaned up appropriately

## External Dependencies

### Core Dependencies
- **Flask**: Web framework for HTTP handling
- **Requests**: HTTP client for proxying video content
- **Gunicorn**: WSGI server for production deployment
- **psycopg2-binary**: PostgreSQL adapter (prepared for future database integration)

### System Dependencies
- **OpenSSL**: For secure connections
- **PostgreSQL**: Database system (configured but not yet implemented)

### Video Source
- Currently configured to stream from: `valiw.hakunaymatata.com`
- Uses authentication key-based URL structure

## Deployment Strategy

### Railway.app Configuration
- **Builder**: Nixpacks for consistent environment
- **Health Check**: `/health` endpoint with 300s timeout
- **Restart Policy**: ON_FAILURE with 10 max retries
- **Environment**: Production Flask with custom Python path

### Gunicorn Optimization
- **Bind**: Dynamic port binding from Railway environment
- **Workers**: Multi-process for high concurrency
- **Timeout**: Extended for video streaming operations
- **Logging**: Comprehensive access and error logging
- **Performance**: Sendfile enabled, preload app for faster startup

### Process Management
- Graceful shutdown handling
- Memory leak prevention with worker recycling
- SSL ready (currently disabled for Railway)

## Changelog
- June 26, 2025: Initial setup with Chrome browser support
- June 26, 2025: Added external player compatibility (VLC, MPV, etc.) with CORS headers and proper OPTIONS/HEAD method support
- June 26, 2025: Enhanced MX Player support with auto-detection, optimized headers, and proper error handling for empty video URLs
- June 26, 2025: Fixed server stability issues with increased timeouts, keep-alive mechanisms, and JavaScript auto-ping system to prevent app stopping when switching tabs
- June 26, 2025: **MAJOR MX Player Fix**: Added direct URL parameter support (?url=VIDEO_URL) to all endpoints, created dedicated /mx endpoint with specialized MX Player headers, enhanced Android player detection, and implemented simplified streaming function for maximum compatibility
- June 28, 2025: **COMPLETE M3U8 TRANSFORMATION**: Completely restructured project from direct video streaming to M3U8 HLS streaming specialization. Added playlist processing, segment proxying, URL rewriting, and restriction bypass system for domain-locked M3U8 streams.
- June 28, 2025: **UNIVERSAL TOKEN SUPPORT**: Enhanced bypass system to work with ANY M3U8 URL containing tokens, not just elderflower/tvnation domains. Added automatic token detection, enhanced headers for different domain types, and improved MX Player compatibility.

## User Preferences

Preferred communication style: Simple, everyday language.